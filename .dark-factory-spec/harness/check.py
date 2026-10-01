"""Everything about a submission repository a judge can check without Docker.

`harness run --repo` covers gate 3 by building the service. This covers the rest:
layout, mandates, the room log, and the two things that must not be in a public
repository -- credentials, and the problem's answer written into a mandate.
"""
from __future__ import annotations

import json
import pathlib
import re
import shlex
import sys

from harness import vocabulary

# Credential shapes that must not reach a public repository. Short on purpose.
SECRETS: tuple[tuple[str, str], ...] = (
    # A token, not the word after "bearer": 20+ characters with a digit in them.
    # `bearer authentication` in a comment is prose, and `check` fails a submission.
    ("bearer-token", r"(?i)\bbearer\s+(?=[A-Za-z0-9._\-]*\d)[A-Za-z0-9._\-]{20,}"),
    ("api-key", r"\bsk-[A-Za-z0-9._\-]{16,}"),
    ("aws-access-key", r"\bAKIA[0-9A-Z]{16}\b"),
    ("github-token", r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    ("env-assignment", r"(?i)\b[A-Z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD)\s*=\s*\S+"),
    # No quote or backslash in the user or password: in code, they end the URL.
    ("url-credentials", r"""(?<=://)[^/\s:@"'\\]+:[^/\s@"'\\]+(?=@)"""),
)
# The room as downloaded from Band, saved unchanged at the repository root.
ROOM = "room.json"
DOWNLOAD = ("open the room in the Band console (Band Desktop: the room's ⋮ menu, Open in "
            "Band), choose ⋮, Download, Download full session, and save the file "
            "unchanged as room.json at the repository root")
# Each mandate says what the seat runs, so a judge can read the factory without Band.
SEAT_FIELDS = ("Harness", "Model")

REQUIRED_FILES = ("README.md", "FACTORY.md")
STAGE_FOLDER = re.compile(r"^stage-[1-4]$")
TEXT_SUFFIXES = {".md", ".py", ".txt", ".json", ".jsonl", ".yml", ".yaml", ".toml",
                 ".env", ".cfg", ".ini", ".js", ".ts", ".sh", ".go", ".rb", ".rs", ".java"}
# A suffix is not how these two are recognised, and they are where a key actually lands.
TEXT_NAMES = {"Dockerfile", ".env", ".envrc", "Makefile"}
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "target", "dist"}
# `NAME=value` is a guess, and in source it guesses wrong: `password = body["password"]`
# and `token = uuid4().hex` are every auth endpoint ever written, including this event's
# own scaffold. Keep it for config, where a bare assignment really is a credential.
CONFIG_ONLY = {"env-assignment"}
CONFIG_SUFFIXES = {".env", ".yml", ".yaml", ".toml", ".cfg", ".ini", ".json"}


def check_repo(path: pathlib.Path | str, track: str) -> list[str]:
    """Every problem found, in the order a team would fix them. Empty means good."""
    root = pathlib.Path(path)
    if not root.is_dir():
        return [f"{root} is not a directory"]
    return (_layout(root, track) + _mandates(root, track) + _room(root)
            + _seats_have_mandates(root) + _credentials(root))


def _layout(root: pathlib.Path, track: str) -> list[str]:
    from harness.cli import available_stages
    problems = []
    for name in REQUIRED_FILES:
        if not (root / name).is_file():
            problems.append(f"{name} is missing; it is where the factory is described")
    if not (root / "stage-1").is_dir():
        problems.append("stage-1/ is missing; every entry needs one complete stage 1")
    defined = available_stages(track)
    for child in sorted(root.iterdir()):
        if not child.is_dir() or child.name in SKIP_DIRS:
            continue
        if re.match(r"^stage[-_]", child.name) and not STAGE_FOLDER.match(child.name):
            problems.append(f"{child.name}/ is not a stage folder the harness will "
                            f"find; name it stage-1 through stage-4")
            continue
        if not STAGE_FOLDER.match(child.name):
            continue
        stage = child.name.removeprefix("stage-")
        if stage not in defined:
            problems.append(f"{child.name}/ is present, but {track} defines stages "
                            f"{', '.join(defined)}")
            continue
        # A stage folder copied forward brings the `.git` of whatever it was copied
        # from, and git then records a gitlink instead of the files. Every file below
        # is present on disk and absent from a clone, so this is the one defect the
        # directory you worked in cannot show you.
        if (child / ".git").exists():
            problems.append(f"{child.name}/ is a git repository of its own, so a clone "
                            f"of this submission gets an empty {child.name}/. Delete "
                            f"{child.name}/.git and commit the files themselves")
        for required in ("Dockerfile", "RUN.md"):
            if not (child / required).is_file():
                problems.append(f"{child.name}/{required} is missing; a judge builds "
                                f"this folder by following its RUN.md, so without it "
                                f"the folder claims nothing and caps the chain above it")
    return problems


def _mandates(root: pathlib.Path, track: str) -> list[str]:
    folder = root / "mandates"
    if not folder.is_dir():
        return ["gate 1: mandates/ is missing; every seat needs a mandate file"]
    files = sorted(folder.glob("*.md"))
    problems = []
    if len(files) < 3:
        problems.append(f"gate 1: {len(files)} mandate file(s) in mandates/; three or "
                        f"more distinct seats are required")
    for mandate in files:
        text = mandate.read_text(errors="replace")
        for field in SEAT_FIELDS:
            if not re.search(rf"(?im)^[-*_ \t]*{field}[*_ \t]*:[*_ \t]*[^*_\s]", text):
                problems.append(f"gate 1: mandates/{mandate.name} has no `{field}:` line; "
                                f"say which {field.lower()} this seat runs")
    # The same tokens and the same list the organizers audit against after submissions
    # close, reported with a line number so a team can fix the line rather than hunt
    # for it. A substring scan would flag `table_ids` inside `available_table_ids`
    # twice and match it inside an unrelated word.
    distinctive = set(vocabulary.for_track(track))
    for mandate in files:
        seen = set()
        for number, line in enumerate(
                mandate.read_text(errors="replace").splitlines(), 1):
            for kind, term in vocabulary.terms_in(line):
                if term in distinctive and (number, term) not in seen:
                    seen.add((number, term))
                    problems.append(
                        f"gate 4: mandates/{mandate.name}:{number} names the {track} "
                        f"problem with the {kind} `{term}`, rather than how your factory "
                        f"works. Move track-specific detail into the task you give the "
                        f"band in the room")
    return problems


def load_room(root: pathlib.Path | str) -> tuple[dict, list]:
    """({seat id: display name}, messages) from `room.json`.

    Raises OSError when it is absent and ValueError on anything the Band download
    would not produce, which callers turn into a readable problem.
    """
    return _parse(json.loads((pathlib.Path(root) / ROOM).read_text()))


def _parse(room) -> tuple[dict, list]:
    messages = room.get("messages") if isinstance(room, dict) else None
    if not isinstance(messages, list) or not all(isinstance(m, dict) for m in messages):
        raise ValueError("expected an object whose `messages` is a list of message objects")
    seats = {m["senderId"]: m.get("senderName") or m["senderId"] for m in messages
             if m.get("senderId") and str(m.get("senderType", "")).lower() == "agent"}
    return seats, messages


def said(messages: list) -> list:
    """Only what a seat said: a mention echoed in a tool call or its output is not one
    seat addressing another."""
    return [m for m in messages if str(m.get("senderType", "")).lower() == "agent"
            and m.get("messageType") == "text"]


def _room(root: pathlib.Path) -> list[str]:
    if not (root / ROOM).is_file():
        return [f"{ROOM} is missing; {DOWNLOAD}"]
    try:
        room = json.loads((root / ROOM).read_text())
        seats, messages = _parse(room)
    except (ValueError, OSError) as exc:
        return [f"{ROOM} could not be read ({exc}); {DOWNLOAD}"]
    problems = []
    if room.get("scope", "full") != "full":
        problems.append(f"{ROOM} is a filtered download (scope `{room.get('scope')}`); "
                        f"use Download full session, not Download filtered")
    if len(seats) < 3:
        problems.append(f"gate 1: the room holds {len(seats)} agent seat(s); three or "
                        f"more distinct seats are required")
    edges = {(m["senderId"], target) for m in said(messages) for target in seats
             if target != m.get("senderId") and mentions(m.get("content"), target)}
    if not any((b, a) in edges for a, b in edges):
        problems.append("gate 2: two of your own seats must exchange messages using "
                        "each other's @handles, with a reply in each direction")
    return problems


def mentions(content, seat_id: str) -> bool:
    """Whether `content` addresses that seat. Band stores a typed `@handle` as
    `@[[participant-id]]`, and that is the only form the download carries."""
    return f"@[[{seat_id}]]" in str(content or "")


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(text).lower())


def _seats_have_mandates(root: pathlib.Path) -> list[str]:
    """Gate 1 is a mandate per seat, so a filename has to name a seat that exists.

    Counting three files and three seats separately passes a repository with three
    mandates for seats nobody configured.
    """
    if not (root / "mandates").is_dir():
        return []                      # `_mandates` already reported it; do not repeat
    try:
        seats, _messages = load_room(root)
    except (OSError, ValueError):
        return []                      # `_room` already reported it; do not repeat
    files = {_slug(p.stem) for p in (root / "mandates").glob("*.md")}
    missing = sorted(name for name in set(seats.values()) if _slug(name) not in files)
    if missing:
        return [f"gate 1: no mandate file for {', '.join(missing)}; name each one after "
                f"the seat it belongs to, e.g. mandates/{_slug(missing[0]) or 'seat'}.md"]
    return []


def _credentials(root: pathlib.Path) -> list[str]:
    """Name the file and the shape, never the secret: this output ends up in logs."""
    problems = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if (not path.is_file() or SKIP_DIRS & set(relative.parts)
                or (path.suffix.lower() not in TEXT_SUFFIXES
                    and path.name not in TEXT_NAMES)):
            continue
        # The room download is JSON, but its tool results are source code, where the
        # `NAME=value` guess is wrong for the same reason it is in a .py file.
        config = ((path.suffix.lower() in CONFIG_SUFFIXES or path.name in TEXT_NAMES)
                  and str(relative) != ROOM)
        try:
            text = path.read_text(errors="replace")
        except OSError:
            continue
        for name, pattern in SECRETS:
            if name in CONFIG_ONLY and not config:
                continue
            if re.search(pattern, text):
                article = "an" if name[0] in "aeiou" else "a"
                problems.append(
                    f"{relative} looks like it holds {article} {name}. This repository "
                    f"is public: remove it, rotate the credential, and rewrite the "
                    f"history that carried it")
                break
    return problems


def add_parser(sub) -> None:
    p = sub.add_parser("check", help="validate a submission repository, offline")
    p.add_argument("repo", help="the submission repository")
    p.add_argument("--track", required=True, choices=("toy", "tablekeeper", "pocketful"))
    p.set_defaults(func=cmd_check)


def cmd_check(args) -> int:
    problems = check_repo(pathlib.Path(args.repo), args.track)
    for problem in problems:
        print(problem, file=sys.stderr)
    print(f"{len(problems)} problem(s)" if problems else
          "ok — gates 1, 2 and the mandate part of gate 4 pass. Not checked here: gate 3 "
          "(stage-1/ builds and serves /health). Run: python -m harness run --track "
          f"{args.track} --repo {shlex.quote(args.repo)} --stage 1 --mode isolated",
          file=sys.stderr)
    return 1 if problems else 0
