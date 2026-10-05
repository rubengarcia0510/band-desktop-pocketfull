# BAND Software Factory

## Purpose

This repository contains an autonomous software factory built with BAND.

The factory coordinates planning, implementation, verification, and evidence
collection through dedicated seats. The human operator provides the stage/task
input; normal task selection, delegation, implementation, verification, and
state progression are handled by the factory.

## Seat Architecture

The factory uses three logical seats:

- **Planner** — authoritative orchestrator.
- **Implementer** — performs the assigned implementation task.
- **Verifier** — independently validates the implementation.

The communication flow is strictly:

Planner -> Implementer -> Planner -> Verifier -> Planner

Implementer and Verifier do not communicate directly.

Only the Planner decides which task is executed next and whether the factory
advances, retries, or stops.

## Planner Responsibilities

The Planner:

1. Reads the authoritative specification.
2. Inspects the current repository.
3. Identifies the complete work required for the current stage.
4. Decomposes the work into atomic tasks.
5. Defines dependencies and acceptance criteria.
6. Creates the complete Jira backlog.
7. Freezes the backlog before normal execution begins.
8. Selects only existing, unblocked tasks from the frozen backlog.
9. Delegates the selected task to the Implementer.
10. Records implementation evidence on the same Jira issue.
11. Delegates verification of the same task to the Verifier.
12. Records verification evidence.
13. Marks the task complete only after independent verification passes.
14. Selects the next unblocked frozen task.

The Planner never implements the task itself.

## Backlog Authority

Jira is the authoritative task state.

A normal implementation task must exist in the frozen backlog before
execution begins.

The factory does not normally create replacement tasks during execution.

If verification fails, the same task is returned to the Implementer together
with the failure evidence.

A new task is allowed only when implementation or verification identifies a
genuine specification gap that was not represented in the frozen plan.

The factory must never silently replace, duplicate, or reinterpret a frozen
task.

## Delegation Protocol

A task is not considered delegated merely because an agent message mentions
the Implementer.

Before every implementation delegation the Planner:

1. Reads the current BAND participants.
2. Identifies the participant whose agent identity is Implementer.
3. Discovers and adds the peer if necessary.
4. Re-reads participants and verifies membership.
5. Sends the task using the BAND messaging tool.
6. Includes the exact task, scope, acceptance criteria, branch requirements,
   and reporting requirements.
7. Mentions only the verified Implementer participant.
8. Waits for successful delivery.
9. Only then records or reports the task as delegated.

If delegation fails, the Planner stops rather than simulating progress.

## Implementation Workflow

The Implementer:

1. Receives one exact task from the Planner.
2. Checks the working tree.
3. Inspects the existing implementation.
4. Preserves unrelated work.
5. Creates or uses the dedicated feature branch.
6. Implements only the assigned task.
7. Runs the relevant tests.
8. Reviews the diff and working tree.
9. Commits only task-related changes.
10. Pushes the feature branch.
11. Reports the branch, commit, changed files, and test results.

The Implementer does not select additional work and does not modify the
factory orchestration.

## Verification Workflow

The Verifier independently validates the exact implementation reported by
the Implementer.

Verification includes:

- confirming the reported branch and commit;
- inspecting the implementation diff;
- running the required tests;
- checking for relevant uncommitted changes;
- determining PASS or FAIL.

The Verifier does not implement fixes and does not create implementation
commits.

A failed verification returns the same task to the Implementer.

## Completion Criteria

A task is complete only when all of the following exist:

- implementation evidence;
- Planner evidence recorded on the Jira issue;
- independent verification;
- verification evidence recorded on the same Jira issue;
- final Jira transition performed by the Planner.

A chat or room message by itself is not considered completion evidence.

## Git Workflow

Implementation work uses dedicated feature branches.

The factory base branch is not used for direct implementation commits.

Each implementation task should produce traceable Git evidence:

Jira task
    |
    v
Feature branch
    |
    v
Commit
    |
    v
Push
    |
    v
Independent verification

Unrelated changes must not be included in a task commit.

## Recovery From Incorrect Work

If implementation fails or verification returns FAIL:

1. The Planner records the failure evidence on the existing Jira issue.
2. The same task is returned to the Implementer.
3. The Implementer reviews the failure and corrects only that task.
4. A new commit is produced on the task branch.
5. The Planner records the new implementation evidence.
6. The same task is independently verified again.

The factory does not create a replacement task merely because implementation
failed.

If a genuine specification gap is discovered, the Planner may create an
explicit change task. That exception must be documented and must not silently
alter an existing frozen task.

## State Machine

The normal lifecycle is:

POST_ANALYSIS
      |
      v
SPRINT_PLANNING
      |
      v
BACKLOG_FROZEN
      |
      v
EXECUTION
      |
      v
VERIFICATION
      |
      v
SPRINT_COMPLETE

Verification failures remain inside the execution/verification cycle until
the existing task passes or the Planner determines that an explicit change
task is required.

## Running the Factory

Create and activate a Python virtual environment:

    python3 -m venv venv
    source venv/bin/activate

Install the project dependencies:

    pip install -r requirements.txt

Configure the required environment variables in `.env` according to the
provided environment template.

Start the Planner seat:

    python band_agent.py planner

Start the Implementer seat in a separate BAND-capable environment:

    python band_agent.py implementer

Start the Verifier seat:

    python band_agent.py verifier

The exact runtime environment and BAND room configuration are external to
the factory logic and must not be hard-coded into task mandates.

## Measured Costs

The factory records execution evidence through Jira, Git, and BAND.

When evaluating a run, record:

- number of Planner turns;
- number of Implementer turns;
- number of Verifier turns;
- number of retries;
- number of generated commits;
- number of completed Jira tasks;
- model/token cost when available;
- elapsed execution time when available.

These measurements should be taken from actual runs rather than estimated.

## Design Rationale

The architecture deliberately separates planning, implementation, and
verification.

The frozen backlog prevents the implementation process from redefining the
work while execution is already in progress.

The Planner remains the single orchestrator so that task ordering and state
transitions are deterministic.

The Implementer is isolated from verification so that implementation cannot
self-certify.

The Verifier is independent and reports evidence back to the Planner.

Jira provides persistent task state while Git provides implementation
traceability.

BAND provides the agent communication and delegation layer.

This separation makes failures observable, recoverable, and auditable without
requiring the human operator to coordinate each individual implementation
step.

## Human Input Boundary

Normal execution requires only the stage/task input needed to start the
factory.

After dispatch, the factory is responsible for:

- planning;
- backlog creation and freezing;
- task selection;
- delegation;
- implementation;
- verification;
- evidence recording;
- retries;
- and normal state progression.

Human intervention is reserved for environment failures, missing external
credentials or services, and exceptional decisions outside the frozen
specification.
