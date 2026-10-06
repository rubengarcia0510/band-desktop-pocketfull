# Participant guide

Everything you need to compete: what to build, when things happen, how to run your
band, and how to submit. This guide is the authoritative rules and instructions for
participants.

## What you build

A software factory in Band Desktop — a band of at least three distinct coding-agent
seats that plans work, implements it, hands off evidence and independently checks its
own results — and a service that factory builds. You give it a job and decide whether
to accept what comes back. What you submit is the factory, the room it worked in, and
the code it produced.

Pick one track and stay in it. You compete only against the track you chose.

| Track | You build | It's hard because |
|---|---|---|
| `tablekeeper` | a restaurant reservation system, an OpenTable | a table must never be double-booked, under concurrency, retries and time zones |
| `pocketful` | a wallet and payments app, a Venmo | money must never be created, destroyed or spent twice, under concurrent transfers, retries and rounding |

Both tracks follow the same four stages and the same rubric, each against its own written specification:

| Stage | What you build | Graded by |
|---|---|---|
| 1 | The JSON API: idempotent writes, atomic multi-item operations, and state export/import | API conformance |
| 2 | The browser UI, a richer resource model, and recovery from stale state and lost responses | API and Playwright, plus stage 1 |
| 3 | State over time: rules or corrections that take effect at a point in time, with past records that stay truthful | API conformance, upgrades and concurrent writes, plus stages 1 and 2 |
| 4 | Changes to many existing records at once, applied atomically without breaking history | Its own suite and populated-state upgrades, plus all three earlier ones |

**All four stages are released at kickoff.** There is nothing to wait for and nothing to
unlock. Work through them in order, because each one builds on the last.

### What each track asks for

**`tablekeeper`** — diners search for a table at a time, book it, get a confirmation, and
can cancel or change it. Restaurants have tables of different sizes, opening hours and a
cancellation policy. Stage 1 already requires atomic, idempotent bookings and
all-or-nothing multi-booking moves through `POST /reservation-moves`. Stage 2 adds the
browser product — search and availability grid, booking, confirmation and lookup — with
recovery from stale state and lost responses, plus combined-table bookings. Stage 3 adds
manager-published, effective-dated policies: each booking retains the terms it accepted,
amendments adopt the applicable new terms, and history remains truthful. Existing bookings
can become recurring agreements whose occurrences keep independent identities and
exceptions. Stage 4 adds series amendments and a bounded, deterministic closure-replanning
problem, with a read-only preview and atomic application.

**`pocketful`** — people hold money in a wallet, send it to each other by handle, ask each
other for it, and split a bill so everyone pays their share. Payments land in an activity
feed, public or private. Five stage-1 write paths require an idempotency key; decline and
cancel do not. Deposits, top-ups and withdrawals are out of scope: money only moves
between existing wallets, and balances always sum to the seeded total. Atomic transfers,
exact split arithmetic and atomic net settlements are stage-1 requirements. Stage 2 adds
the browser product — balance and pay, activity feed, requests and splits — with recovery
from stale state and lost responses, plus holds, partial captures and their screen. Stage
3 adds immutable payment corrections, historical views separating when money moved from
when a correction became known, and snapshot-stable statement pagination and historical
hold accounting. Stage 4 adds refunds by the receiver from available funds, and operator
batch corrections that must include every member of a corrected settlement. Every amount
is an exact integer count of minor units.

`toy` is an unscored four-stage practice track with the same shape as the real ones. Run
it for easy practice — see [Practice on the toy](#practice-on-the-toy-example).

## Schedule

| PDT | What happens |
|---|---|
| Sat Sep 26, 09:00 | Kickoff. Both tracks, all four specs, part of each stage's checks, and the toy are released |
| Mon Oct 5, 23:59 | Submissions close |

## What makes an entry count

### Eligibility

- At least three distinct coding-agent seats in Band Desktop, each with a mandate file
  that says which harness and model the seat runs. Seats may share a harness and a model.
- At least one complete output for stage 1.
- A submitted presentation, video and public GitHub repository as specified below. **The video shows
  your factory working** — the room, a handoff between seats, and the result it produced.
  A slideshow about the factory is not the same as the factory.

### The three rules that decide most entries

- **Hand-built code does not count.** A stage counts only if the code that passes its
  tests came out of a collaboration in your Band Desktop room. However green your tests
  are, code you wrote by hand does not count. Your room event log is what shows the work was
  the band's.

- **Code written to the tests disqualifies the entry.** You get part of each stage's
  checks, not the full set of tests. That is enough to wire your service up, 
  but it's not meant to be a list of what will be run. Build to the specification, not the tests. 
  See [Do not write to the tests](#do-not-write-to-the-tests) — this is the rule most likely
  to cost a team its entry, and it is enforced after submissions close.

- **Your mandates must be generic.** A mandate says how a seat works — what it owns, how
  it hands off, when it rejects. It must not name anything specific to your track: no
  endpoint paths, field names, or error codes. **A mandate that
  names track-specific detail disqualifies the entry** — see
  [Your mandates must be generic](#your-mandates-must-be-generic).

### Four gates. Fail any one and your entry is not ranked.

A failed gate is not a low score — it is a disqualified entry. `harness check` runs gates
1, 2 and the mandate half of gate 4 offline, so run it before you push.

1. Your roster lists **three or more distinct Band Desktop seat identities that you
   configured**, each with a mandate file named after that seat that names the seat's
   harness and model. 
2. Your room log shows messages exchanged **between at least two of your own seats**,
   each addressing the other by `@handle`, with a reply in each direction. 
3. `stage-1/` **builds and serves from a clean container** by following its `RUN.md`.
   Every other folder is judged the same way, but a folder that does not start costs
   that stage and the ones above it rather than the entry — see [Rubric](#rubric).
4. Your **mandates are generic** — they describe your factory, not this track — and
   your code is written to the spec rather than to the tests.

### Rubric

Every entry that passes the gates is judged on three criteria. 

| Criterion | Weight | What judges look for |
|---|---|---|
| **Factory** | **50%** | **Generic:** another team could point your mandates at a different problem. **Effective:** how far through the four stages it got with code that meets the spec, including what the shipped checks never asked. **Reusable:** `FACTORY.md` and `mandates/` are enough to stand it up, and explain your design choices and what they cost, measured time and model spend, and how the factory catches and recovers from bad work |
| **App** | **25%** | What your factory built: a UI that is coherent, presentation-ready, responsive and clear in the states the stage-2 spec identifies, over code another developer could maintain |
| **Agent Teamwork** | **25%** | Your seats did the work together, and without you. **Collaboration:** the seats really shared the work — more than one seat did it, review changed something, handoffs carried the whole task, and the code traces to the room. **Autonomy:** in the run you submit, the task you dispatch for each stage is the only human input — no steering, approvals, debugging hints or reruns until it passed. Runs made while you developed the factory are not judged — see [Build and check each stage](#build-and-check-each-stage) |

We do not score chat volume, seat count or prompt length. What is read from the room log
is whether the work was **distributed** — one seat carrying 90% of it looks the same
however many messages it sent. Nor is manufactured conflict worth anything: a rejection
counts when it changed the work, and correct work that was accepted first time loses
nothing. [Agent Teamwork evidence](#agent-teamwork-evidence) says how to make sure the
evidence is there.

Use the presentation and video to explain your factory design, what it cost, a bad result
it caught, and the stage you reached. It does not replace `FACTORY.md`, which has to be
enough on its own for another team to stand your factory up.

## Prepare

Use Python 3.12+, Git, a running Docker daemon, a Band Desktop account, 
and your own model-provider access. All seats may use the same
runtime/model, but can also use different harnesses or models. 

Python is required here only to run the event harness. **Your submitted service may use
any language or framework.** Judges build your `Dockerfile` and communicate with the
container exclusively over HTTP. They do not import your source into Python or require
your compiler, interpreter, package manager or dependencies on the judge host. Install
everything your service needs while building the image and include its runtime in that
image. A TypeScript/Node, Go, Rust, Java or other implementation follows the same contract
and is judged the same way as a Python implementation.

Clone the kickoff repository, or extract the kickoff archive if you were given one.
Run commands below from its `dark-factory-wearedevs/` directory:

```sh
python3 --version                # use any Python 3.12+ interpreter
docker --version                 # the daemon must be running
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r harness/requirements.txt
python -m playwright install chromium
python -m harness --help
```

Use a Python 3.12+ interpreter to create the venv. If `python3` points to an older
version, substitute the command for your newer interpreter (for example, `python3.12` or
`python3.13`). Inside the venv, `python` is the right one.

On Linux, browser system libraries may also be needed: `python -m playwright install
--with-deps chromium`. Isolated checks install the browser inside Docker. On Windows, run
these steps inside WSL2.

Keep the result repository separate from the challenge package and factory inputs:

```sh
mkdir -p ../band-work/result/stage-1 ../band-work/checks
git -C ../band-work/result init -b main
git -C ../band-work/result config user.name "Your Name"
git -C ../band-work/result config user.email you@example.test
```

`../band-work/` is this guide's convention for everything you produce, kept beside the
extracted package. The harness does not know about it; every path is passed on the
command line; if you choose a different path - that's perfectly fine, just be aware 
that you'll have to modify that in the command line where needed.

`../band-work/result` is the convention for where the output of the factory resides. 
Give your agents its absolute path, not the relative one: a seat works in its own
sandbox, may not be able to resolve `../band-work`, and will otherwise create a repository only it
can see.

| Path | Holds |
|---|---|
| `../band-work/result` | the submission repository for your chosen track |
| `../band-work/checks` | the `harness run --out` directories you keep while iterating |

The graded repository starts empty deliberately so the event does not choose an
implementation language for your factory. Configure Git names and emails for each seat.
The Python `scaffold/` is used by the toy walkthrough only; it is not part of either
challenge and need not be copied, translated or retained in a graded submission.

In Band Desktop, create at least three seats, each with its own seat identity. Confirm
that direct `@handle` messages reach each seat and that each seat can reply.

Prepare permissions for the result checkout, Git, Docker and browser checks. Keep
credentials outside the result repository and its Git history. 

### Optional: run a seat in a Docker Sandbox

Band Desktop can start a seat's runtime inside a [Docker Sandbox](https://www.docker.com/products/docker-sandboxes/) — 
a microVM with its own filesystem, network boundary and Docker daemon — so that seat builds
and commits without holding those permissions on your machine. That makes it safer to
give a seat the broad permissions an unattended run needs: a wrong command, or a harmful
instruction hidden in something the seat reads, reaches only its working directory and
the network its policy allows, not your home directory, credentials or other
repositories. It is optional, it changes nothing you submit, and no gate depends on it.

You also need Band Desktop 0.4.10 or newer, Docker Sandboxes 0.42 or newer, and a
supported host — macOS 14+ on Apple silicon, Windows 11, or Ubuntu 24.04+ with KVM.

**Install `sbx`.** It is its own download — Docker Desktop neither provides it nor is
required for it:

```sh
# macOS 14+ on Apple silicon
brew trust docker/tap && brew install docker/tap/sbx

# Ubuntu 24.04+ with KVM — the repository, then the package
curl -fsSL https://get.docker.com | sudo REPO_ONLY=1 sh
sudo apt install docker-sbx
```

On Windows 11, enable the hypervisor first, then install from an elevated PowerShell:

```powershell
Enable-WindowsOptionalFeature -Online -FeatureName HypervisorPlatform -All
winget install -h Docker.sbx
```

Docker's own guide wins if it disagrees with the above:
<https://docs.docker.com/ai/sandboxes/install/>. Then sign in and start the daemon:

```sh
sbx version                      # 0.42 or newer
sbx login
sbx daemon start --detach
sbx policy ls                    # if it reports no policy yet:
sbx policy init balanced
```

Band Desktop starts sandboxes without a terminal, so it cannot answer the network-policy
prompt `sbx` shows before a first sandbox. Do not reset a policy that already exists.

**Give the seat a credential.** A sandboxed seat cannot use your host Claude login.

| Paying with | Do this |
|---|---|
| An Anthropic **API key** | `sbx secret set anthropic` and paste it, or `echo "$ANTHROPIC_API_KEY" \| sbx secret set anthropic` |
| A Claude **subscription** | From an empty scratch directory, `sbx run --name sbx-login claude`, then `/login` inside it; exit, then `sbx rm sbx-login`. `sbx secret set` cannot store a subscription. `sbx secret ls` should now show `anthropic` as `(oauth configured)` |

An OpenCode seat is not sandboxed at all — see
[the OpenCode section](#optional-run-a-seat-on-opencode-with-featherless-models).

**On macOS, let Band Desktop see `sbx`.** Homebrew installs it to `/opt/homebrew/bin`,
which a GUI app does not inherit, so the runtime check reports `sbx` missing however
happily your terminal runs it. Set the PATH, then reboot:

```sh
sudo launchctl config user path "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
```

`launchctl config` takes effect only after a reboot (`man launchctl`). Quitting and
reopening Band Desktop is not enough, and neither is restarting its background daemon.

**Turn it on.** **Settings → Experiments → Docker Sandboxes**, then **Settings → Runtime
→ Re-check**. Only a seat Band Desktop runs itself can be sandboxed: create it with
**New local agent** as a headless Claude Code, Codex, GitHub Copilot or Cursor seat.
OpenCode seats, and any session you started yourself, stay on the host. The credential
and setup steps in this section are for Claude Code; for the other harnesses, follow
Band Desktop's advanced reference.

Choose the sandbox when you create the seat:
**Docker Sandbox** on, **Direct host workspace** mode, and **Working directory** set to
the absolute path of `../band-work/result` — the same path you give the band, so the
seat's commits land in your repository rather than a copy you cannot see. For the
credential, pick **Docker-managed Anthropic credential** — it covers both the key and
the subscription. Run **Test runtime** before
you give the seat work; if it cannot authenticate, give it an API key or run it on the
host.

Nothing else moves: the room, the room download and the submission layout are
unchanged, and `python -m harness run` still runs on your machine rather than inside a
sandbox.

### Optional: run a seat on OpenCode with Featherless models

To run any of your seats in OpenCode, and using one of the open-weights models provided
by Featherless AI, follow these steps:

**1. Install both pieces.**

```sh
brew install sst/tap/opencode      # or: curl -fsSL https://opencode.ai/install | bash
pip install 'band-sdk[opencode]'
pip install 
```

**2. Write the provider config to `~/.config/opencode/opencode.json`** — not to the
repository. OpenCode reads `./opencode.json` from its working directory, which for a seat
is `../band-work/result`, the repository you submit. A key committed there is in your Git
history for good.

```json
{
  "$schema": "https://opencode.ai/config.json",
  "provider": {
    "featherless": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "Featherless AI",
      "options": {
        "baseURL": "https://api.featherless.ai/v1",
        "apiKey": "{env:FEATHERLESS_API_KEY}"
      },
      "models": {
        "MiniMaxAI/MiniMax-M2.5": {},
        "moonshotai/Kimi-K2.5": {},
        "deepseek-ai/DeepSeek-V3.2": {}
      }
    }
  }
}
```

**3. Confirm the model writes files before you involve Band.**

```sh
export FEATHERLESS_API_KEY=...
opencode models | grep featherless
opencode run -m featherless/MiniMaxAI/MiniMax-M2.5 \
  "Create hello.txt containing the word banana, then run 'wc -c hello.txt'."
```

If you see `hello.txt` on disk then things are working and you're clear to proceed. 

To see the list of models you can use, try: `curl https://api.featherless.ai/v1/models`.

**4. Start the server.** It stays in the foreground, and it has no authentication unless
you set `OPENCODE_SERVER_PASSWORD` — anyone who can reach it can write files and run
commands, so keep it on `127.0.0.1`.

```sh
opencode serve --hostname=127.0.0.1 --port=4096
```

**5. Run the adapter.** It is a small program you run yourself.

```python
import asyncio

from band import Agent, Emit
from band.adapters import OpencodeAdapter, OpencodeAdapterConfig
from band.config import load_agent_config

agent_id, api_key = load_agent_config("reviewer")   # YAML kept outside the result repo

adapter = OpencodeAdapter(
    config=OpencodeAdapterConfig(
        base_url="http://127.0.0.1:4096",
        # Absolute, and the same path you give the band. A relative path resolves
        # against wherever you started the server, and the seat commits somewhere
        # you never look.
        directory="/absolute/path/to/band-work/result",
        provider_id="featherless",
        model_id="MiniMaxAI/MiniMax-M2.5",
        # Defaults to "manual", which stalls every tool call waiting for an answer.
        # auto_accept means this seat runs shell commands without asking, so run the
        # server and this adapter on a box you can throw away.
        approval_mode="auto_accept",
        # Defaults to 300s. A one-file edit took 16-41s against these models, so five
        # minutes cuts real turns short.
        turn_timeout_s=900,
    ),
    emit={Emit.TOOL_CALLS, Emit.TASK_EVENTS},
)
agent = Agent.create(adapter=adapter, agent_id=agent_id, api_key=api_key)
asyncio.run(agent.run())
```

The Docker Sandbox toggle does not cover this seat — it sandboxes a Band Desktop runtime,
not a server you launched yourself. If the seat will not start, run it as a Claude Code
seat in Band Desktop and carry on; the event is not the place to debug a runtime.

## The repository you submit

Your entry to the hackathon is in the form of a github repository. The folder structure should
look like this:

```text
your-repo/
  README.md          team, track, and how to read this repository
  FACTORY.md         your factory: seats, design choices, costs, failure handling
  mandates/          one .md per seat, named after the seat, at least three; each
                     names the seat's harness and model
  room.json          the room, downloaded from Band — see Record the room
  stage-1/           Dockerfile, RUN.md, source
  stage-2/           Dockerfile, RUN.md, source
  stage-3/           Dockerfile, RUN.md, source
  stage-4/           Dockerfile, RUN.md, source
```

**Name each mandate after its seat as the room shows it**, ignoring case and punctuation:
`reviewer.md` for Reviewer, `delivery-manager.md` for Delivery Manager. Gate 1 checks that
every seat in your room log has a mandate file named after it. **Start each mandate with
the harness and model that seat actually runs:**

```text
Harness: Claude Code
Model: claude-sonnet-5
```

Use the harness name as Band Desktop shows it (Claude Code, Codex, OpenCode, …) and the
exact model id. `harness check` reports a mandate that is missing either line. Mandates
must also be generic — see [Your mandates must be generic](#your-mandates-must-be-generic).

**Each stage folder is a complete, buildable service on its own, and it holds the
solution to that stage — not to a later one.** `stage-2/` is `stage-1/` carried forward
and extended; `stage-3/` is `stage-2/` carried forward, and so on. When you finish a
stage, have the band copy the folder and widen the copy to the next stage's spec.

**If the folder you copy holds a `.git` directory, delete it.** A stage folder that is
its own repository is recorded as a link, not as files: everything is there in your
working directory and absent from a clone, so the folder builds for you and arrives
empty for a judge. `harness check` reports it.

Each folder is graded against **every suite up to its own number**: `stage-3/` runs
suites 1, 2 and 3, and it counts as a completed stage 3 only if it passes at least half of
each of the three suites. A
stage-3 service that broke stage 1 has not extended anything, and extending what already
works is the whole exercise.

**A folder that also passes the *next* stage's whole suite claims nothing.** If `stage-1/`
passes every stage 2 check, it is a stage 2 solution filed in the wrong folder, and it
earns no stage 1. The point of the four folders is to show requirements accumulating the
way they do on real work: build stage 1, then take stage 2's requirements and widen what
you built. Copying your final answer back into every folder defeats that and scores
nothing for the earlier ones.

`harness run --repo ... --stage N` runs this check for you and prints
`claimed stage: N on the shipped checks` or `claimed stage: none`.

For both graded tracks, every folder below stage 4 is checked against the next suite,
including `stage-2/` against suite 3: stage 3 introduces new endpoints and semantics.
Only the practice `toy` skips the stage-2 → suite-3 probe, because its stage 3 adds
load rather than new surface.

Submit only the folders you completed. A team that reached stage 2 submits `stage-1/`
and `stage-2/` and nothing else. An empty or half-finished `stage-3/` does not hurt the
folders below it — a folder that does not build claims nothing, exactly as an absent one
does, and either way the chain stops there. There is simply no reason to include it.
`stage-1/` is the one folder every entry must have: it is gate 3, and a `stage-1/` that
does not start is an unranked entry.

**The chain is what scores.** A folder counts only if every earlier folder counts too, so
a passing `stage-4/` above a failing `stage-2/` counts for nothing at stages 2, 3 or 4 — fix
the earlier folder before adding another. `harness run --repo <repo> --all` shows which
folders claim their stage in one run.

## Build and check each stage

Use one room and one result repository throughout. Give the band each spec in order,
asking it to copy the previous stage folder forward and extend it. Seats assign and
reply using each other's literal `@handles`. The coordinator must add every configured
seat to the room before its first handoff and retry a handoff if Jam reports that the
named seat is absent. A coordinator must paste the complete task
and spec into each delegated handoff; pointing at a room message id or asking a seat to
read the room is insufficient. Long handoffs can be split into numbered direct messages.
The implementer posts the full committed revision, and the reviewer independently runs
the checks against a handoff that also contains the complete requirements.

Iterate on your factory as much as you like: try seats, mandates and whole bands, and
step in while you do. The run you submit is different. Once you have chosen the factory,
run it in a fresh room and a fresh result repository, and submit that room and those
mandates. Only that run is judged for Agent Teamwork.

In the submitted run, each stage is a **dark-factory run**. The task you dispatch is its only human input.
From that dispatch until the coordinator's final report, no seat may ask you for
clarification, approval, confirmation or another decision, or pause waiting for your
reply. Seats resolve choices from the supplied requirements and communicate within the
band. If they cannot proceed, the coordinator records the blocker and available evidence
as the stage outcome. Resolve event or specification questions before starting the stage.

You may dispatch each stage separately or all four at once. Either way, send nothing
between dispatches: a "looks good, continue" is steering, and dispatching the same stage
twice is a rerun.

### Example prompt for your lead seat

Once you have everything ready and you want to prepare for submission, you can give the lead the full stage sequence up front. 
The example below shows one way to do this. Replace `<WORKSPACE>` with the absolute path to the folder containing your `dark-factory-wearedevs/` 
kickoff checkout and `band-work/` workspace. This example uses Tablekeeper; for Pocketful, change the track and spec paths.
The kickoff checkout contains the specs, so the lead can read them directly. It must still
include the complete task and spec in every delegated handoff.

```text
You are the lead seat for our factory. Build all four stages sequentially, coordinating
the other seats and keeping every stage in its own complete, buildable folder.

Workspace root: <WORKSPACE>
Working folder: <WORKSPACE>/dark-factory-wearedevs
Track: tablekeeper
Result repository: <WORKSPACE>/band-work/result

Your goal is to implement each stage fully, and only then move to the next stage.

For stage 1, read the full spec at:
<WORKSPACE>/dark-factory-wearedevs/tablekeeper/spec/stage-1.md
Implement it in:
<WORKSPACE>/band-work/result/stage-1/

When you are done, continue to stage-2. Start from the codebase of stage-1 and implement  stage-2 spec starting from that code.
From there, continue on to stage-3 and then stage-4 in the same manner.
At the end you should have a subfolder for each stage with the code generated for that stage.
```

The real submission repository is the separate `band-work/result/` repo, not the kickoff
repo. Its stage folders are the outputs every seat shares and commits to.

To check a stage, run the harness. For example:

```sh
python -m harness run --track tablekeeper --repo ../band-work/result --stage 3 \
  --out ../band-work/checks/s3-01
```

That builds `../band-work/result/stage-3/` and runs the checks for stages 1, 2 and 3
against it, then the stage 4 suite as the overshoot check. **That last one should fail** —
a `stage-3/` that passes suite 4 claims nothing — so ignore its line and read the last two:

```text
highest contiguous stage: 3
claimed stage: 3 on the shipped checks
report: ../band-work/checks/s3-01/report.json
NOTE: this run only includes a portion of the full tests that are applied before judging; this is meant to provide directional feedback, and ultimately you may not pass the stage with the full set of tests.
```

For `stage-N/`, you want `claimed stage: N`. `highest contiguous stage` is the last stage
whose every shipped check passed against this folder, so it can read lower than a stage
the folder still claims. `claimed stage: none` means one of the suites passed under half
of its checks, or that the folder also passes every check of the next stage.

IMPORTANT: The package ships only part of the tests for each challenge, so this output cannot tell 
you how a folder does on the full set of tests. In other words, the `harness run` command above is only
meant to give you directional guidance, but judging will be done based on a larger set of tests, and a folder 
that reads `claimed stage: N` here can still fail. See [Do not write to the tests](#do-not-write-to-the-tests).

**Run your final check of each stage in isolated mode**, because that is how it will be
graded:

```sh
python -m harness run --track tablekeeper --repo ../band-work/result --stage 3 \
  --mode isolated --out ../band-work/checks/s3-final
```

Swap `--stage 3` for `--all` to build every folder you have and see which ones claim their
stage.

Host mode is the default and is the right thing while you iterate, but it publishes a
port and does **not** block outbound network. Isolated mode runs on an internal network
with no outbound access, 2 vCPU and 2 GiB — a service that quietly depends on reaching
the internet at runtime passes in host mode and fails when judged.

Every check writes `report.json`, per-stage logs and count files into a **new**
directory. Existing output directories are refused: choose another name or omit `--out`
to get a unique directory under `runs/`. Preserve failures. In the submitted run the
band reads the failing log and fixes the implementation itself; handing it the log is for
while you develop the factory. Skips, deselection, missing browsers, empty suites
and startup errors cannot produce a passing stage.

Keep result repositories self-contained: no Git submodules or symlinks. Builds may fetch
dependencies. `Dockerfile` is required in each stage folder; Compose is optional and is
never read by the harness. All required services must work inside the single image. The
harness runs locally as a terminal command; your reviewer can run it. It is not a Band
Desktop seat and never posts messages.

## Do not write to the tests

Each stage ships part of its checks so your band can wire a service up and iterate: run a
stage, read the failing log, fix the implementation, run it again. Every stage ships
`test_sample.py`, which shows each surface once; most stages also ship some of the graded
suite's own files, unchanged. The rest of each suite is held back:

| Stage | Tablekeeper checks shipped | Pocketful checks shipped |
|---|---:|---:|
| 1 | 83% | 79% |
| 2 | 41% | 35% |
| 3 | 11% | 9% |
| 4 | 21% | 16% |

During judging, the full set of tests are run to validate your solution.
Every one of them is written in the specification you were given, and a careful reading finds them. 

**A green run on the shipped checks is not evidence of a stage.** When a stage looks done,
re-read its spec section and ask what the shipped checks never asked for — that question
is the work.

## Your mandates must be generic

**This is the rule teams most often break by accident, and it is disqualifying.** Read it
before you write a single mandate.

Your mandates describe **how your factory works**: what each seat owns, how it takes work,
how it hands work off, what makes it reject something, how it reports evidence. Nothing in
a mandate should tell a reader which of the two tracks you entered.

The task you paste into the room describes **what this track needs**. That is where the
spec goes. Pasting a whole spec into the room is expected and correct.

**A mandate may freely say** things like: "you implement one scoped work item at a time",
"you reject any change without a passing check", "post the committed revision in the room
when you are done", "read the specification the coordinator gives you and ask if it is
ambiguous". None of that names a track.

The test to apply yourself: **could you hand these mandates to a team building something
completely different, and would they still make sense?** If not, they are not a factory —
they are a transcript of this problem, and half of the judging is about whether your
factory is generic and whether another team could stand it up from `FACTORY.md` and
`mandates/`.

## Agent Teamwork evidence

Agent Teamwork is read from your room log and your Git history, not from what you write
about it. Judges compare the two to see whether the seats shared the work, whether the
code came out of the room, and whether anyone outside the band steered it.

Good teamwork leaves a trail in both. The work is split between seats rather than carried
by one. Handoffs happen in the room and carry the whole task. Review is real: when a seat
rejects work, it says what failed, and the fix comes back through the room. Progress shows
up as commits made along the way, each traceable to the discussion that produced it.

Keep that trail intact. Push the history the seats made, without amending, rebasing or
squashing it, and leave the code under `stage-N/` to the band: anything you commit there
yourself is code the band did not write.

## Record the room

The room log is what shows the code came from your band. No harness command fetches it:
you download it from Band yourself and commit the file.

1. **Open the room in the Band console.** In Band Desktop, open the room you worked in,
   click the `⋮` menu at the top right of the room and choose **Open in Band**. The room
   opens in the Band console under **Sessions**. You can also sign in to the Band
   console directly and pick the room from **Sessions**.
2. **Download the full session.** In the console, click the room's `⋮` menu at the top
   right, then **Download → Download full session**. Do not use **Download filtered**,
   and it does not matter what the **Event type** and **Sender** filters are set to. 
3. **Save the file, unchanged, as `room.json`** at the root of your result repository.
   Band names the file after the room, e.g. `Tablekeeper.json` for a room called
   Tablekeeper. Rename it, and do not edit its contents.

```sh
mv ~/Downloads/Tablekeeper.json ../band-work/result/room.json
```

The file holds every message in the room, including the seats' tool calls and their
output, exactly as Band stored them. **Nothing redacts it.** Your repository is public,
so read it before you commit it: `harness check` scans `room.json` for credential
shapes like every other file, but it cannot recognise every private value. If it finds
one, rotate the credential and replace the value in `room.json` with `[REDACTED]`.

Download it at the end, after the work is done, so the log holds the whole
collaboration. Download it again whenever you want to refresh it, and overwrite
`room.json`.

## Check and submit

Run the offline check from the repository root before you push:

```sh
python -m harness check ../band-work/result --track tablekeeper
```

It validates the folder layout, that each stage folder has a `Dockerfile` and a
`RUN.md`, that `room.json` is a whole-room download, that every seat in it has a
mandate file named after it, that every mandate names its harness and model, that two
seats really exchanged `@handle` messages in both directions, that no mandate names
track vocabulary, and that no file in the repository, `room.json` included, looks like
it holds a credential.
It builds nothing — gate 3 is `harness run --repo`.

Then commit everything, push to a public GitHub repository a judge can clone without
Band Desktop membership, and submit its URL along with your presentation and video to
the lablab submission page. 

Write `README.md` and `FACTORY.md` yourself. `FACTORY.md` is what judges read to decide
whether another team could stand your factory up: seat ownership and setup, your design
choices and the reasons for them, what you tried that failed, measured costs and time, and
how your factory catches a bad result. Agent Teamwork is not written — it is read out of
your room log and your commit history, so the way to show it is to actually work in the
room and leave the band to run.

## Practice on the toy example

Everything above is the real track. The toy is where you rehearse it first, on a problem
small enough to read in a minute, before you hand your band a spec that counts.

`toy` is an unscored four-stage exercise. It builds one shared counter: the API, then a
page with an increment button, then 20 simultaneous increments with none lost, then a
request that chooses how much to add.

It is small on purpose. The shape is the same as `tablekeeper` and `pocketful` — a
submission repository with one folder per stage, each folder a service that still passes
every earlier stage — so one run puts your band through the whole loop, producing code
and checking it independently.

Its specs are `toy/spec/stage-1.md` through `toy/spec/stage-4.md`.

The supplied mandates are **minimal practice templates** for assignments, handoffs and
basic review, not a complete factory design. Adapt your workflow for the graded challenges;
short mandates are allowed, but a successful toy run does not establish their effectiveness
on the real tracks.

Prepare a separate practice repository the same way:

```sh
mkdir -p ../band-work/toy-result/stage-1 ../band-work/toy-result/mandates
cp scaffold/* ../band-work/toy-result/stage-1/
cp toy/mandates/*.md ../band-work/toy-result/mandates/
git -C ../band-work/toy-result init -b main
(cd ../band-work/toy-result && pwd)
```

`scaffold/` is a starting service, not a solution. It answers `/health` and
`/_test/reset` and hashes passwords, and that is all — your band writes the rest. Using
it is optional; any language is fine.

Paste `stage-1.md` into one Band Desktop room with the absolute path that prints:

> Build this shared-counter service one stage at a time. The result repository is
> `/absolute/path/to/band-work/toy-result`. Stage 1 goes in `stage-1/`; when it passes,
> copy that folder to `stage-2/` and extend the copy, and the same again for `stage-3/`
> and `stage-4/`. Produce source files, a Dockerfile and RUN.md in each, and commit
> nowhere else. Have the reviewer check each stage, and after each one post the full
> committed revision in the room.

Use the same room and repository for all four stages so the band extends the service it
already built. Paste one stage's spec at a time, or give the lead all four as in
[Example prompt for your lead seat](#example-prompt-for-your-lead-seat), and stop wherever
you like: the point is to run the loop, not to finish the toy.

Check each stage as it lands:

```sh
python -m harness run --track toy --repo ../band-work/toy-result --stage 1 \
  --out ../band-work/checks/toy-s1
python -m harness run --track toy --repo ../band-work/toy-result --stage 2 \
  --out ../band-work/checks/toy-s2
python -m harness run --track toy --repo ../band-work/toy-result --stage 3 \
  --out ../band-work/checks/toy-s3
python -m harness run --track toy --repo ../band-work/toy-result --stage 4 \
  --out ../band-work/checks/toy-s4
```

`--stage N` runs stage N's suite **and every earlier stage's** against that folder, so a
stage-4 check prints four `pass` lines, not one.

**Note that some of these runs print one extra line that says `fail`, and that is intended.**
After the graded suites, the harness runs the *next* stage's suite to check that you did
not overshoot. `--stage 1` also runs suite 2. `--stage 3` also runs suite 4. Your
`stage-1/` folder is supposed to solve stage 1 and not stage 2, so it should fail suite 2
— a folder that passed it would be a stage 2 answer sitting in the stage 1 folder, and it
would not count.

So this is a clean stage 1 run, not a broken one:

```text
  stage 1: pass
  stage 2: fail
highest contiguous stage: 1
claimed stage: 1 (100% of its own suite)
```

| Stage | Its own suite | A passing `--stage N` run prints |
|---|---|---|
| 1 | 8 API checks | `stage 1: pass`, `stage 2: fail`, then `highest contiguous stage: 1` |
| 2 | 4 browser checks | stages 1 and 2 pass, `highest contiguous stage: 2` |
| 3 | 2 concurrency checks | stages 1 to 3 pass, `stage 4: fail`, `highest contiguous stage: 3` |
| 4 | 10 checks, 2 of them concurrent | stages 1 to 4 pass, `highest contiguous stage: 4` |

`--stage 2` and `--stage 4` print no extra line: `stage-2/` is never run against the
stage 3 suite, and stage 4 has no suite above it. Whatever the other lines say, the one
that tells you the folder is right is the last one, `claimed stage: N`.

That is why you copy the folder forward: `stage-4/` still has to serve the page and
survive the burst, not only accept the new field.

`--all` builds every folder the way the organizers do and prints one line per folder.
It does not add the chain up for you: count from `stage-1/` and stop at the first folder
that does not claim its stage. A passing `stage-4/` above a broken `stage-2/` still prints
`claims stage 4` on its own line, but the entry reaches stage 1 and nothing more.

Check it before the band has written anything and stage 1 fails, which is expected: the
scaffold answers health and reset but has no counter, so **2 of the 8 stage-1 checks pass
and 6 fail**. The terminal prints only `stage 1: fail` — the counts are in the
`stage-1.log` it names on that line. Once the band has implemented the counter you will
see `stage 1: pass` instead, and that is the exercise. Give the band a failing stage's
log and ask it to fix the implementation; if Docker cannot build or the service never
starts, give it the terminal error, because the tests cannot run until that is fixed.
Stage 4 is where a band that special-cased its way through stage 3 finds out: the lock
it wrote has to hold for an amount it did not know about.

Confirm the *reviewer* ran these checks, not the implementer, and that the room holds a
message from a seat naming the committed revision. What to look for is in
[Build and check each stage](#build-and-check-each-stage); the toy is the cheap place to
find out whether your seats actually produce it.

**Finish the loop on the toy, too.** Passing the checks is half of it; the other half is
the submission, and that is where entries are lost. On your toy repository, follow
[Record the room](#record-the-room) into `../band-work/toy-result/room.json`, then run
the offline check:

```sh
python -m harness check ../band-work/toy-result --track toy
```

It lists what a submission still needs — `README.md`, `FACTORY.md`, `mandates/` with
their `Harness:` and `Model:` lines filled in, `room.json` — and it is the only check that proves gates 1 and 2 without Docker, so it takes a
minute. Fix those on the toy now and both gates are rehearsed before the real repository
matters. Gate 2 clears only once two of your seats have exchanged `@handle` messages in
the room, with a reply in each direction, which is what the toy is for.

One difference from the real tracks: the toy ships its **whole** suite, because its job
is to show you the loop. Your track ships part of each stage's checks and the rest stay
with the judges — see [Do not write to the tests](#do-not-write-to-the-tests).
Do not read the toy's green run as what a green run on your track proves.

Every run needs an `--out` directory that does not exist yet, so number them. The first
isolated run installs the runner's dependencies and browser in Docker and takes longer;
time it now rather than on the last day.

## Before you submit

Work through this against a fresh clone, not the directory you worked in.

1. Clone your pushed repository somewhere new and run `harness check` there. A file you
   forgot to commit, and a stage folder that is its own git repository, are both
   invisible from your working directory and both arrive empty for a judge. This step is
   the only one that shows them.
2. Run `harness run --repo <clone> --all --mode isolated` once. It builds every stage
   folder and shows which ones claim their stage on the shipped checks; the organizers'
   full run decides which stages count. A folder counts only if every earlier folder
   counts, so one failing folder caps everything above it. Per folder,
   `claimed stage: none` means either a suite passed under half of its checks or the
   folder also passes every check of the next stage.
3. Follow each folder's `RUN.md` by hand in a clean environment, then use the UI. No
   offline check covers this. For `stage-1/` it is gate 3; for every other folder it is
   what lets the folder claim its stage, and a service that does not start counts for
   nothing at that stage or any above it.
4. Read `room.json` and confirm the reciprocal `@handle` exchange between two of
   your seats is really there, and that no history was rewritten
   ([Agent Teamwork evidence](#agent-teamwork-evidence)).
5. Confirm `README.md` and `FACTORY.md` are written, not placeholders.
6. Re-read every mandate and ask whether a team building something else could use it.
   Anything naming your track's endpoints, fields, error codes or test ids has to go.
7. Skim the repository for anything private that automatic redaction would not
   recognise. If you find a credential, rotate it — deleting the line does not unpublish
   what was already pushed.
8. Submit the repository URL, the presentation and the video, then keep the receipt.

## Getting help

Ask in the **BAND Discord**: <https://discord.com/invite/5YkNXmYfjk>. That is the formal
channel for Band Desktop, seat, permission and harness questions. Event and platform
questions — registration, uploads, prizes — go to the lablab Discord channel.

If you find a genuine ambiguity in a published spec, ask. Clarifications are answered
**publicly to every team**, because everyone builds the same specification.
