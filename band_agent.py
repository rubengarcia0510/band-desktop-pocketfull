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

from crew_setup import ensure_agents, require_env_vars


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


class JiraBacklogTaskInput(BaseModel):
    task_id: str = Field(description="Stable task identifier inside the frozen sprint plan.")
    summary: str = Field(description="Exact Jira task summary.")
    description: str = Field(description="Concrete implementation scope and acceptance criteria.")
    dependencies: list[str] = Field(default_factory=list)


class JiraBacklogInput(BaseModel):
    plan_id: str = Field(description="Stable identifier for the complete sprint plan.")
    tasks: list[JiraBacklogTaskInput] = Field(
        description="Complete sprint backlog. All normal implementation work must be present."
    )


class JiraBacklogQueryInput(BaseModel):
    plan_id: str = Field(description="Stable identifier of the sprint plan to inspect.")


class JiraTransitionInput(BaseModel):
    issue_key: str = Field(description="Jira issue key to transition.")
    transition_name: str = Field(
        default="Finalizada",
        description="Jira transition name, normally Finalizada after verifier PASS.",
    )


def jira_create_or_select(task: JiraTaskInput) -> str:
    """Legacy helper retained for compatibility; Planner no longer uses it."""
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


def _validate_backlog(tasks: list[JiraBacklogTaskInput]) -> None:
    if not tasks:
        raise ValueError("El backlog no puede estar vacío.")

    task_ids = [task.task_id.strip() for task in tasks]

    if any(not task_id for task_id in task_ids):
        raise ValueError("Todos los task_id deben ser no vacíos.")

    if len(task_ids) != len(set(task_ids)):
        raise ValueError("Los task_id del backlog deben ser únicos.")

    known = set(task_ids)

    for task in tasks:
        missing = set(task.dependencies) - known

        if missing:
            raise ValueError(
                f"Dependencias inexistentes para {task.task_id}: "
                f"{sorted(missing)}"
            )

    graph = {
        task.task_id: list(task.dependencies)
        for task in tasks
    }

    visiting = set()
    visited = set()

    def visit(node):
        if node in visiting:
            raise ValueError(
                f"Ciclo de dependencias detectado en {node}."
            )

        if node in visited:
            return

        visiting.add(node)

        for dependency in graph[node]:
            visit(dependency)

        visiting.remove(node)
        visited.add(node)

    for task_id in graph:
        visit(task_id)


def jira_create_and_freeze_backlog(backlog: JiraBacklogInput) -> str:
    """Create the complete Jira sprint backlog and freeze it."""
    _validate_backlog(backlog.tasks)

    client = JiraClient()
    existing = client.search_factory_plan(backlog.plan_id)

    frozen = [
        issue
        for issue in existing
        if "DARK_FACTORY_BACKLOG_FROZEN: YES"
        in client._description_text(issue)
    ]

    if frozen:
        return (
            f"BACKLOG_ALREADY_FROZEN plan_id={backlog.plan_id}; "
            f"issues={','.join(issue['key'] for issue in frozen)}"
        )

    existing_by_task = {}

    for issue in existing:
        description = client._description_text(issue)

        match = re.search(
            r"DARK_FACTORY_TASK_ID:\s*([^\n]+)",
            description,
        )

        if match:
            existing_by_task[match.group(1).strip()] = issue

    issue_keys = []

    for task in backlog.tasks:
        task_id = task.task_id.strip()
        dependencies = (
            ",".join(dep.strip() for dep in task.dependencies)
            or "NONE"
        )

        description = (
            f"DARK_FACTORY_PLAN_ID: {backlog.plan_id}\n"
            f"DARK_FACTORY_TASK_ID: {task_id}\n"
            f"DARK_FACTORY_DEPENDENCIES: {dependencies}\n"
            "DARK_FACTORY_BACKLOG_FROZEN: PENDING\n\n"
            f"{task.description}"
        )

        existing_issue = existing_by_task.get(task_id)

        if existing_issue:
            issue_key = existing_issue["key"]
        else:
            created = client.create_task(
                summary=task.summary,
                description=description,
                labels=["dark-factory-plan"],
            )
            issue_key = created["key"]

        issue_keys.append(issue_key)

    for issue_key in issue_keys:
        issue = client.get_issue(issue_key)
        description = client._description_text(issue)

        if "DARK_FACTORY_BACKLOG_FROZEN: YES" not in description:
            description = description.replace(
                "DARK_FACTORY_BACKLOG_FROZEN: PENDING",
                "DARK_FACTORY_BACKLOG_FROZEN: YES",
            )

            client.update_description(
                issue_key,
                description,
            )

        client.add_comment(
            issue_key,
            (
                "DARK_FACTORY_BACKLOG_FROZEN: YES\n"
                f"DARK_FACTORY_PLAN_ID: {backlog.plan_id}\n"
                "This issue belongs to the complete frozen sprint backlog. "
                "Normal execution must not create replacement tasks."
            ),
        )

    return (
        f"BACKLOG_FROZEN plan_id={backlog.plan_id}; "
        f"task_count={len(issue_keys)}; "
        f"issues={','.join(issue_keys)}"
    )


def jira_get_frozen_backlog(query: JiraBacklogQueryInput) -> str:
    """Read the authoritative frozen Jira backlog."""
    client = JiraClient()
    issues = client.search_factory_plan(query.plan_id)

    frozen = []

    for issue in issues:
        description = client._description_text(issue)

        if "DARK_FACTORY_BACKLOG_FROZEN: YES" not in description:
            continue

        task_match = re.search(
            r"DARK_FACTORY_TASK_ID:\s*([^\n]+)",
            description,
        )

        dependency_match = re.search(
            r"DARK_FACTORY_DEPENDENCIES:\s*([^\n]+)",
            description,
        )

        fields = issue.get("fields") or {}
        status = (fields.get("status") or {}).get("name", "UNKNOWN")

        frozen.append(
            {
                "jira_key": issue["key"],
                "task_id": (
                    task_match.group(1).strip()
                    if task_match
                    else issue["key"]
                ),
                "summary": fields.get("summary", ""),
                "dependencies": (
                    []
                    if not dependency_match
                    or dependency_match.group(1).strip() == "NONE"
                    else [
                        item.strip()
                        for item in dependency_match.group(1).split(",")
                        if item.strip()
                    ]
                ),
                "status": status,
            }
        )

    if not frozen:
        return f"NO_FROZEN_BACKLOG plan_id={query.plan_id}"

    return (
        f"FROZEN_BACKLOG plan_id={query.plan_id}; "
        f"tasks={frozen}"
    )


def jira_transition_issue(transition: JiraTransitionInput) -> str:
    """Transition an existing Jira task after authoritative Planner verification."""
    client = JiraClient()

    if transition.transition_name.strip().lower() == "finalizada":
        client.transition_to_finalizada(transition.issue_key)
    else:
        client.transition_issue(
            transition.issue_key,
            transition.transition_name,
        )

    return (
        f"TRANSITIONED issue={transition.issue_key}; "
        f"transition={transition.transition_name}"
    )


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

    repository_directory = os.path.abspath(
        os.getenv(
            "PRODUCT_REPOSITORY_DIRECTORY",
            os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "..",
                "pocketful-product",
            ),
        )
    )

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
        raise ValueError(
            f"Unsupported GitFlow operation: {operation}"
        )

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

    slug = re.sub(
        r"[^a-z0-9]+",
        "-",
        branch.short_description.lower(),
    ).strip("-")

    if not slug:
        raise ValueError(
            "Short description must contain alphanumeric characters"
        )

    branch_name = f"{branch.jira_key}-{slug}"

    return _run_git_flow(
        "feature_start",
        branch_name,
    )


def gitflow_feature_finish(branch: GitFlowFeatureFinishInput) -> str:
    """Finish a GitFlow feature branch and merge it back into develop."""
    return _run_git_flow(
        "feature_finish",
        branch.branch_name,
    )


def gitflow_release_start(branch: GitFlowReleaseStartInput) -> str:
    """Start a GitFlow release branch from develop."""
    return _run_git_flow(
        "release_start",
        branch.branch_name,
    )


def gitflow_release_finish(branch: GitFlowReleaseFinishInput) -> str:
    """Finish a GitFlow release branch and merge it into main and develop."""
    return _run_git_flow(
        "release_finish",
        branch.branch_name,
    )


def gitflow_hotfix_start(branch: GitFlowHotfixStartInput) -> str:
    """Start a GitFlow hotfix branch from main."""
    return _run_git_flow(
        "hotfix_start",
        branch.branch_name,
    )


def gitflow_hotfix_finish(branch: GitFlowHotfixFinishInput) -> str:
    """Finish a GitFlow hotfix branch and merge it into main and develop."""
    return _run_git_flow(
        "hotfix_finish",
        branch.branch_name,
    )


PLANNER_CUSTOM_SECTION = """
You are the PLANNER seat for the Dark Factory Pocketful track.

AUTHORITATIVE SOURCE:
.dark-factory-spec/pocketful/spec/stage-1.md

You are the SINGLE ORCHESTRATOR of the factory.

The only valid execution communication flow is:

Planner -> Implementer -> Planner -> Verifier -> Planner

Implementer and Verifier NEVER communicate directly.
Implementer NEVER selects the next task.
Verifier NEVER selects the next task.
Only Planner decides what happens next.

FACTORY LIFECYCLE:

POST_ANALYSIS
    ->
SPRINT_PLANNING
    ->
BACKLOG_FROZEN
    ->
EXECUTION
    ->
VERIFICATION
    ->
SPRINT_COMPLETE

CRITICAL PLANNING RULE:

The factory MUST complete planning before normal implementation begins.

Do NOT use the old incremental model:

analysis -> create one task -> implement -> verify -> invent next task

Instead:

1. Read the complete authoritative specification.
2. Inspect the current repository enough to understand the existing implementation.
3. Identify ALL required capabilities for the current sprint/stage.
4. Split the work into atomic implementation tasks.
5. Define dependencies between those tasks.
6. Define concrete acceptance criteria for every task.
7. Create the COMPLETE Jira backlog in one planning operation.
8. Freeze that backlog.
9. Only after the backlog is frozen may execution begin.

The frozen Jira backlog is the authoritative execution queue.

Do NOT normally create Jira tasks during execution.
Do NOT invent a replacement task because the current task failed.
Do NOT create the next normal task after verification.

During execution, select only an EXISTING, UNBLOCKED task from the frozen backlog.

A new task may be created only as an explicit exceptional CHANGE TASK
when implementation or verification discovers a genuine specification gap
that was absent from the frozen plan.

JIRA BACKLOG RULES:

- Every normal implementation task MUST exist in Jira before execution.
- Every normal task has exactly one Jira issue.
- Every task has a stable task_id.
- Dependencies must refer only to existing task_ids.
- Dependencies must not contain cycles.
- Once frozen, the backlog is authoritative.
- Never silently replace a frozen task with another task.
- Never duplicate an existing atomic task.
- Never use one Jira key for two different atomic tasks.

EXECUTION RULE:

For each existing frozen task:

1. Planner reads the frozen backlog.
2. Planner selects the next UNBLOCKED existing task.
3. Planner delegates that exact Jira task to @implementer.
4. Implementer changes code on its dedicated feature branch.
5. Implementer reports branch, commit and tests back to Planner.
6. Planner records concise implementation evidence on the SAME Jira issue.
7. Planner delegates verification of that SAME Jira task to @verifier.
8. Verifier independently validates the branch/commit and reports PASS or FAIL to Planner.
9. Planner records verifier evidence on the SAME Jira issue.

If verifier PASS:

10. Planner transitions the SAME Jira issue to Finalizada.
11. Planner selects the next existing unblocked frozen task.

If verifier FAIL:

10. Planner records the failure on the SAME Jira issue.
11. Planner sends the SAME task back to @implementer with the failure evidence.
12. Do NOT create a replacement Jira task.
13. Do NOT ask Verifier to communicate with Implementer.

TASK COMPLETION RULE:

A task is complete only when all of these are true:

- Implementer evidence exists.
- Planner recorded implementation evidence in Jira.
- Verifier independently returned PASS.
- Planner recorded verifier evidence in Jira.
- The SAME Jira issue was transitioned to Finalizada.

A room message alone is never sufficient evidence.

DELEGATION GATE:

Never state that a task is delegated or in progress unless the actual BAND
delegation message to @implementer was successfully sent in the current
planning turn.

CRITICAL BAND DELEGATION PROTOCOL — MANDATORY:

A plain LLM response containing "@implementer" is NEVER a delegation.

Every implementation delegation MUST execute this exact tool sequence in
the CURRENT BAND ROOM:

1. Call band_get_participants().
2. Identify the participant whose agent identity is the Implementer.
   Do NOT guess a handle and do NOT use a name merely because it looks right.
3. If the Implementer is absent, call band_lookup_peers(), find the exact
   Implementer peer, then call band_add_participant() with that peer.
4. Call band_get_participants() again and verify the Implementer is now a
   participant of the CURRENT ROOM.
5. Call band_send_message() with:
   - content containing the exact Jira key, task, scope, acceptance criteria,
     required branch and report requirements;
   - mentions containing ONLY the verified Implementer participant handle.
6. Wait for band_send_message() to return success.
7. ONLY THEN report that the task was delegated.

The mentions argument of band_send_message() is the actual BAND mention
mechanism. Putting "@implementer" in content does NOT replace the mentions
argument.

NEVER claim delegation, execution, or "awaiting Implementer" unless the
band_send_message() tool call for that task succeeded in the CURRENT TURN.

If band_get_participants(), band_lookup_peers(), band_add_participant(), or
band_send_message() fails, STOP. Report the failure. Do not simulate or
claim delegation.

Do NOT create a new Jira task as a workaround.

The delegation content sent through band_send_message() MUST contain:
- exact Jira key
- exact atomic task
- relevant real file paths
- exact specification requirements
- acceptance criteria
- required branch name
- requirement to report commit and tests

A Verifier message is NOT implementation delegation.
Before contacting @verifier for a new implementation task, the actual
implementation delegation MUST already have been sent to @implementer.

Do NOT implement code yourself.
Do NOT delegate multiple independent implementation tasks in one message.
Do NOT ask the user for confirmation.
Do NOT invent APIs, fields, endpoints, status codes, or semantics that are
not defined by the authoritative specification.

SQLite concurrency:
- use BEGIN IMMEDIATE
- never use SELECT ... FOR UPDATE

Idempotency:
- preserve the exact idempotency key
- scope lookup by authenticated user and endpoint
- store a canonical request-body hash
- same key + same canonical body = replay
- same key + different canonical body = conflict
- never replace the idempotency key with its hash

Only Planner may perform orchestration and delegation decisions.
Implementer changes code.
Verifier independently validates.
Planner decides the next state.

Never allow Implementer -> Verifier communication.
Never allow Verifier -> Implementer communication.
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
            (JiraBacklogInput, jira_create_and_freeze_backlog),
            (JiraBacklogQueryInput, jira_get_frozen_backlog),
            (JiraIssueInput, jira_get_issue),
            (JiraEvidenceInput, jira_add_evidence),
            (JiraTransitionInput, jira_transition_issue),
        ],
    )


IMPLEMENTER_CUSTOM_SECTION = """
You are the IMPLEMENTER seat for the Dark Factory Pocketful track.

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


VERIFIER_CUSTOM_SECTION = """
You are the VERIFIER seat for the Dark Factory Pocketful track.

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
    repository_directory = os.path.abspath(
        os.getenv(
            "PRODUCT_REPOSITORY_DIRECTORY",
            os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "..",
                "pocketful-product",
            ),
        )
    )

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
    except Exception as exc:
        print(f"Error al arrancar {seat}: {exc}")
        raise SystemExit(1)
