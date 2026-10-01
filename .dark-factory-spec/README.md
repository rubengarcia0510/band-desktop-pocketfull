# Dark Factory — WeAreDevelopers hackathon

This is the kickoff package for the [WeAreDevelopers hackathon on lablab.ai](https://lablab.ai/ai-hackathons/wearedevelopers-hackathon).
You build a software factory in Band Desktop — at least three coding-agent seats that
plan, implement and review each other's work — and have it build a service, one stage at
a time.

**Read the [participant guide](docs/participant-guide.md) before anything else.** It is
the authoritative source for the rules, schedule, gates, rubric and submission steps.
This README only tells you where things are.

## What's in this repository

| Path | What it is |
|---|---|
| [`docs/participant-guide.md`](docs/participant-guide.md) | Rules, schedule, rubric and step-by-step instructions |
| `tablekeeper/` | Track 1: a restaurant reservation system. `spec/stage-1.md`…`stage-4.md` and part of each stage's tests |
| `pocketful/` | Track 2: a wallet and payments app. Same layout as `tablekeeper/` |
| `toy/` | Unscored practice track: a shared counter, with its full test suite and sample mandates |
| `scaffold/` | Minimal Python starting service, used only by the toy walkthrough |
| `harness/` | The `python -m harness` CLI that builds your stage folders and runs the checks |

Pick one track and stay in it. The result you submit is a **separate** repository your
band builds; nothing you submit goes into this one.

## Help

- Band Desktop, seats, permissions and the harness: the
  [BAND Discord](https://discord.com/invite/5YkNXmYfjk).
- Registration, uploads and prizes: the lablab Discord channel.
- Spec ambiguities: ask in the BAND Discord. Answers are shared publicly with every team.

## License

[Apache 2.0](LICENSE).
