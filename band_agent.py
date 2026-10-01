"""Runner for the three Band seats used by the dark factory.

Planner uses CrewAI for coordination and delegation.
Implementer and Verifier use OpenCode for repository work and verification.
"""

from __future__ import annotations

import asyncio
import os
import re
import subprocess
import sys

from dotenv import load_dotenv

from band import Agent
from pydantic import BaseModel, Field
from jira_client import JiraClient
from band.adapters import CrewAIAdapter, OpencodeAdapter, OpencodeAdapterConfig

from crew_setup import require_env_vars


SEAT_ROLE_BY_NAME = {
    "planner": "Planner",
    "implementer": "Implementer",
    "verifier": "Verifier",
}


def _seat_config(seat_name: str) -> dict[str, str | None]:
    load_dotenv()

    seat = seat_name.lower()

    if seat not in SEAT_ROLE_BY_NAME:
        raise ValueError(f"Seat desconocido: {seat_name}")

    return {
        "agent_id": os.getenv(f"{seat.upper()}_AGENT_ID"),
        "api_key": os.getenv(f"{seat.upper()}_API_KEY"),
        "role": SEAT_ROLE_BY_NAME[seat],
    }


def _require_seat_env(seat_name: str) -> dict[str, str]:
    config = _seat_config(seat_name)

    missing = [
        key
        for key in ("agent_id", "api_key")
        if not str(config.get(key, "") or "").strip()
    ]

    if missing:
        raise ValueError(
            f"Faltan variables de entorno para {seat_name}: {', '.join(missing)}"
        )

    return {
        "agent_id": str(config["agent_id"]).strip(),
        "api_key": str(config["api_key"]).strip(),
    }


class JiraTaskInput(BaseModel):
    summary: str = Field(description="Short Jira task summary.")
    description: str = Field(description="Concrete implementation task description.")


class JiraIssueInput(BaseModel):
    issue_key: str = Field(description="Jira issue key, for example PDF-21.")


class JiraEvidenceInput(BaseModel):
    issue_key: str = Field(description="Jira issue key, for example PDF-21.")
    evidence: str = Field(description="Concise implementation or verification evidence.")


def jira_create_or_select(task: JiraTaskInput) -> str:
    """Find an existing Jira task with this summary or create it if absent."""
    client = JiraClient()
    matches = client.search_by_summary(task.summary)

    if matches:
        return matches[0]["key"]

    created = client.create_task(
        summary=task.summary,
        description=task.description,
    )
    return created["key"]


def jira_get_issue(issue: JiraIssueInput) -> str:
    """Read Jira state and authoritative implementation/verifier evidence."""
    issue = JiraClient().get_issue(issue.issue_key)

    fields = issue.get("fields", {})
    status = (fields.get("status") or {}).get("name", "UNKNOWN")
    summary = fields.get("summary", "")

    comments = fields.get("comment", {}).get("comments", [])
    evidence = []

    for comment in comments:
        body = comment.get("body", {})
        paragraphs = []

        for block in body.get("content", []):
            for item in block.get("content", []):
                text_value = item.get("text")
                if text_value:
                    paragraphs.append(text_value)

        text_value = " ".join(paragraphs).strip()
        if text_value:
            evidence.append(text_value)

    result = f"{issue['key']}: status={status}; summary={summary}"

    if evidence:
        result += "; evidence=" + " || ".join(evidence)

    return result


def jira_add_evidence(evidence: JiraEvidenceInput) -> str:
    """Record implementation or verification evidence on the Jira issue."""
    JiraClient().add_comment(
        evidence.issue_key,
        evidence.evidence,
    )
    return evidence.issue_key


class GitFlowFeatureStartInput(BaseModel):
    """Input for starting a GitFlow feature branch from a Jira task."""
    jira_key: str = Field(
        description="Jira issue key, for example PDF-21."
    )
    short_description: str = Field(
        description="Short branch description, for example gitflow-implementer."
    )


class GitFlowFeatureFinishInput(BaseModel):
    """Input for finishing a GitFlow feature branch."""
    branch_name: str = Field(
        description="Feature name without the feature/ prefix, for example PDF-21-gitflow-implementer."
    )


class GitFlowReleaseStartInput(BaseModel):
    """Input for starting a GitFlow release branch."""
    branch_name: str = Field(
        description="Release name without the release/ prefix."
    )


class GitFlowReleaseFinishInput(BaseModel):
    """Input for finishing a GitFlow release branch."""
    branch_name: str = Field(
        description="Release name without the release/ prefix."
    )


class GitFlowHotfixStartInput(BaseModel):
    """Input for starting a GitFlow hotfix branch."""
    branch_name: str = Field(
        description="Hotfix name without the hotfix/ prefix."
    )


class GitFlowHotfixFinishInput(BaseModel):
    """Input for finishing a GitFlow hotfix branch."""
    branch_name: str = Field(
        description="Hotfix name without the hotfix/ prefix."
    )


def _run_git_flow(operation: str, branch_name: str) -> str:
    """Run one validated GitFlow operation in the factory repository."""
    if not re.fullmatch(r"[A-Za-z0-9._/-]+", branch_name):
        raise ValueError("Invalid GitFlow branch name")

    if (
        branch_name.startswith("/")
        or branch_name.endswith("/")
        or ".." in branch_name
    ):
        raise ValueError("Invalid GitFlow branch name")

    repository_directory = os.path.dirname(os.path.abspath(__file__))

    commands = {
        "feature_start": ["git", "flow", "feature", "start", branch_name],
        "feature_finish": ["git", "flow", "feature", "finish", branch_name],
        "release_start": ["git", "flow", "release", "start", branch_name],
        "release_finish": ["git", "flow", "release", "finish", branch_name],
        "hotfix_start": ["git", "flow", "hotfix", "start", branch_name],
        "hotfix_finish": ["git", "flow", "hotfix", "finish", branch_name],
    }

    command = commands.get(operation)
    if command is None:
        raise ValueError(f"Unsupported GitFlow operation: {operation}")

    env = os.environ.copy()
    env["GIT_MERGE_AUTOEDIT"] = "no"

    result = subprocess.run(
        command,
        cwd=repository_directory,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    output = "\n".join(
        part.strip()
        for part in (result.stdout, result.stderr)
        if part and part.strip()
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"git flow {operation} failed "
            f"(exit {result.returncode}): {output}"
        )

    return output or f"git flow {operation} completed: {branch_name}"


def gitflow_feature_start(branch: GitFlowFeatureStartInput) -> str:
    """Start a GitFlow feature branch derived from the Jira key."""
    if not re.fullmatch(r"[A-Z][A-Z0-9]+-[0-9]+", branch.jira_key):
        raise ValueError("Invalid Jira issue key")

    slug = re.sub(r"[^a-z0-9]+", "-", branch.short_description.lower()).strip("-")
    if not slug:
        raise ValueError("Short description must contain alphanumeric characters")

    branch_name = f"{branch.jira_key}-{slug}"
    return _run_git_flow("feature_start", branch_name)


def gitflow_feature_finish(branch: GitFlowFeatureFinishInput) -> str:
    """Finish a GitFlow feature branch and merge it back into develop."""
    return _run_git_flow("feature_finish", branch.branch_name)


def gitflow_release_start(branch: GitFlowReleaseStartInput) -> str:
    """Start a GitFlow release branch from develop."""
    return _run_git_flow("release_start", branch.branch_name)


def gitflow_release_finish(branch: GitFlowReleaseFinishInput) -> str:
    """Finish a GitFlow release branch and merge it into main and develop."""
    return _run_git_flow("release_finish", branch.branch_name)


def gitflow_hotfix_start(branch: GitFlowHotfixStartInput) -> str:
    """Start a GitFlow hotfix branch from main."""
    return _run_git_flow("hotfix_start", branch.branch_name)


def gitflow_hotfix_finish(branch: GitFlowHotfixFinishInput) -> str:
    """Finish a GitFlow hotfix branch and merge it into main and develop."""
    return _run_git_flow("hotfix_finish", branch.branch_name)


PLANNER_CUSTOM_SECTION = """You are the Planner seat for the Dark Factory Pocketful track.

AUTHORITATIVE SOURCE:
.dark-factory-spec/pocketful/spec/stage-1.md

Your job is to coordinate Stage 1 through SMALL, ATOMIC implementation tasks.

Before planning, read enough of the official spec and current pocketful/ code
to identify the NEXT unfinished Stage 1 block. Do not perform an exhaustive
audit and do not repeatedly reread the repository.

For each planning turn:
1. Identify the single next unfinished block.
2. Check Jira for the current state of any existing issue representing that exact subtask.
3. Treat explicit Implementer/Verifier evidence and Jira state as authoritative over stale room messages.
4. If the exact subtask already has a Jira issue, reuse that issue; never create a duplicate.
5. Define ONE concrete implementation subtask for @implementer.
6. Include the Jira key in the delegation and require it in the implementation branch and commit.
7. Include the relevant real file paths and exact spec requirements.
8. Define concise acceptance tests/evidence for that subtask.
9. Delegate only that subtask to @implementer.
10. After implementation evidence is available, ask @verifier to validate it.
11. Record the implementation and verifier evidence on the same Jira task.
12. Use the verifier result to choose the next atomic subtask.

STATE RULES:
- A room message alone is never sufficient evidence that a task is DONE.
- A task is DONE only when there is explicit implementation evidence plus verifier PASS,
  or an equivalent authoritative Jira evidence record.
- Do not create a new Jira issue merely because the room history contains no current
  message for a previously completed task.
- Before creating a Jira issue, use the Jira tool to check whether the exact subtask
  already exists.
- Never create a Jira issue for work that is already verified as complete.

Do NOT implement code yourself.
Do NOT delegate multiple independent implementation tasks in one message.
Do NOT ask the user for confirmation.
Do NOT create a full Stage 1 roadmap in one turn.
Do NOT skip required Stage 1 areas.

Use only endpoint names, fields, status codes, error codes, validation rules,
shapes and semantics actually defined by the official spec. Do not invent APIs.

For SQLite concurrency use BEGIN IMMEDIATE, never SELECT ... FOR UPDATE.

For idempotency, preserve the exact key for lookup scoped by authenticated
user and store a request-body hash to detect reuse with a different request.
Do not replace the idempotency key with a hash.

The Planner coordinates; @implementer changes code; @verifier independently
validates. Keep the delegation flow:
Planner -> Implementer -> Planner -> Verifier -> Planner.

JIRA RULES:
- Every implementation subtask MUST have exactly one Jira issue before delegation.
- Never delegate an implementation task without a Jira key.
- Reuse an existing Jira issue only when it represents the same atomic subtask.
- Never reuse a Jira key for a different subtask.
- The Jira key MUST appear in the implementation branch name and commit message.
- After verification, add concise implementation/verifier evidence to that same Jira issue.

Finish each planning turn by delegating the concrete next subtask. Do not
remain in analysis.
"""



def _build_planner_adapter(
    selected_role: str,
    model_name: str,
) -> CrewAIAdapter:
    if not model_name.startswith("openai/"):
        model_name = f"openai/{model_name}"

    return CrewAIAdapter(
        model=model_name,
        role=selected_role,
        goal=(
            f"Actuar como {selected_role} del sistema y coordinar el trabajo "
            "mediante los participantes de BAND."
        ),
        backstory=(
            f"Sos el seat {selected_role}. Tu misión es colaborar de forma "
            "coherente dentro del flujo de la factory, manteniendo evidencia, "
            "delegando el trabajo concreto a los agentes correspondientes y "
            "usando las herramientas de BAND para comunicarte con ellos."
        ),
        custom_section=PLANNER_CUSTOM_SECTION,
        verbose=True,
        additional_tools=[
            (JiraTaskInput, jira_create_or_select),
            (JiraIssueInput, jira_get_issue),
            (JiraEvidenceInput, jira_add_evidence),
        ],
    )


IMPLEMENTER_CUSTOM_SECTION = """You are the IMPLEMENTER seat for the Dark Factory Pocketful track.

Follow GitFlow strictly for every assigned subtask.

The current factory branch is the base branch. Create a dedicated feature branch
for the assigned subtask before implementation:
feature/<JIRA-KEY>-<short-description>

Before changing files:
- Run git status and inspect existing uncommitted changes.
- Preserve existing changes that belong to your assigned subtask.
- Never discard, reset, clean, or overwrite existing work.
- Do not commit unrelated changes.

The Planner MUST provide a Jira key with every assigned subtask.
Use that exact Jira key in the feature branch name and commit message.
Never invent, change, or reuse a Jira key for another subtask.

After implementation:
1. Run the required tests.
2. Review git diff and git status.
3. Stage only files belonging to the assigned subtask.
4. Create a clear git commit for the subtask.
5. Push the feature branch.
6. Report the feature branch name, commit SHA, changed files, and tests.

Do not implement unrelated subtasks.
Do not modify the Planner or Verifier workflow.
Do not commit directly on the factory base branch.
"""

VERIFIER_CUSTOM_SECTION = """You are the VERIFIER seat for the Dark Factory Pocketful track.

You independently validate the Implementer's committed work.

Verify the specific feature branch and commit SHA reported by the Implementer.
Inspect the diff and run the required tests.

Do NOT implement fixes.
Do NOT create implementation commits.
Do NOT modify unrelated files.

Report:
- feature branch
- commit SHA validated
- changed files
- tests executed and results
- PASS or FAIL
- any relevant uncommitted changes
"""

def _build_coding_adapter(
    *,
    custom_section: str = "",
    include_base_instructions: bool = False,
) -> OpencodeAdapter:
    repository_directory = os.path.dirname(os.path.abspath(__file__))

    config = OpencodeAdapterConfig(
        base_url=os.getenv(
            "OPENCODE_BASE_URL",
            "http://127.0.0.1:4096",
        ),
        directory=repository_directory,
        provider_id="featherless",
        model_id=os.getenv(
            "OPENCODE_MODEL",
            "MiniMaxAI/MiniMax-M2.5",
        ),
        custom_section=custom_section,
        include_base_instructions=include_base_instructions,
        approval_mode="auto_accept",
        turn_timeout_s=float(
            os.getenv(
                "OPENCODE_TURN_TIMEOUT_S",
                "900",
            )
        ),
    )

    additional_tools = []
    if custom_section == IMPLEMENTER_CUSTOM_SECTION:
        additional_tools = [
            (GitFlowFeatureStartInput, gitflow_feature_start),
            (GitFlowReleaseStartInput, gitflow_release_start),
            (GitFlowHotfixStartInput, gitflow_hotfix_start),
        ]

    return OpencodeAdapter(
        config=config,
        additional_tools=additional_tools,
    )


def build_band_agent(
    seat_name: str,
    *,
    event_role: str | None = None,
) -> Agent:
    """Create a Band seat using the appropriate agent adapter."""

    seat_name = seat_name.lower()

    credentials = _require_seat_env(seat_name)

    llm_config = require_env_vars()

    os.environ["OPENAI_API_KEY"] = llm_config["FEATHERLESS_API_KEY"]
    os.environ["OPENAI_API_BASE"] = llm_config["FEATHERLESS_BASE_URL"]

    selected_role = event_role or SEAT_ROLE_BY_NAME[seat_name]

    if seat_name == "implementer":
        adapter = _build_coding_adapter(
            custom_section=IMPLEMENTER_CUSTOM_SECTION,
        )
    elif seat_name == "verifier":
        adapter = _build_coding_adapter(
            custom_section=VERIFIER_CUSTOM_SECTION,
        )
    else:
        adapter = _build_planner_adapter(
            selected_role,
            llm_config["FEATHERLESS_MODEL"],
        )

    return Agent.create(
        adapter=adapter,
        agent_id=credentials["agent_id"],
        api_key=credentials["api_key"],
    )


async def _run_seat(seat_name: str) -> None:
    agent = build_band_agent(seat_name)
    await agent.run()


if __name__ == "__main__":
    seat = (
        sys.argv[1]
        if len(sys.argv) > 1
        else "planner"
    ).lower()

    try:
        asyncio.run(_run_seat(seat))
    except KeyboardInterrupt:
        print(f"Seat {seat} detenida por el usuario.")
    except Exception as exc:  # pragma: no cover - CLI entrypoint
        print(f"Error al arrancar {seat}: {exc}")
        raise SystemExit(1)
