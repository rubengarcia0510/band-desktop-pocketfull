"""Command line entry point.

    python -m harness run --track tablekeeper --base-url http://127.0.0.1:8080
    python -m harness run --track pocketful --build ./submission/result
    python -m harness run --track pocketful --build ./result --mode isolated

Preserves the exit code, saves full per-stage logs, and writes a machine-readable
report.json alongside them.
"""
from __future__ import annotations

import argparse
import importlib
import json
import os
import uuid
import pathlib
import subprocess
import sys
from contextlib import ExitStack

from harness import docker_driver as dd
from harness import report as rp
from harness.provenance import suite_digest

TRACKS = ("toy", "tablekeeper", "pocketful")
ROOT = pathlib.Path(__file__).resolve().parent.parent

STAGE_DIRS = {
    "1": "stage_1",
    "2": "stage_2",
    "3": "stage_3",
    "4": "stage_4",
}


def stage_path(track: str, stage: str) -> pathlib.Path:
    return ROOT / track / "test" / STAGE_DIRS[stage]


PUBLISHED_STAGES = ("1", "2", "3", "4")


def available_stages(track: str) -> list[str]:
    """Every stage the track defines. Every track has four, and all ship at kickoff."""
    return [s for s in PUBLISHED_STAGES if stage_path(track, s).is_dir()]


# Only the toy's third stage is concurrency-only. Graded stage 3s add new contracts.
NO_NEW_SURFACE = {("toy", "3")}


def probe_stage(track: str, stage: str) -> str | None:
    """The suite that would show `stage-N/` holds a later solution, or None.

    A stage folder is meant to be that stage's answer. If it also passes the next
    stage's suite it is a later answer filed in the wrong folder, and claims nothing.
    """
    following = str(int(stage) + 1)
    if (track, following) in NO_NEW_SURFACE or following not in available_stages(track):
        return None
    return following


RUNNER_IMAGE = "df-harness-runner"
LOG_WIDTH = "200"


def ensure_runner_image() -> str:
    """Build the image the suites run inside for isolated mode."""
    return dd.build_image(str(ROOT / "harness"), tag=RUNNER_IMAGE,
                          dockerfile=str(ROOT / "harness" / "Dockerfile"))


def run_stage(track: str, stage: str, base_url: str, out_dir: pathlib.Path,
              extra: list[str], *, mode: str = dd.HOST,
              network: str | None = None) -> tuple[str, int]:
    """Run one stage's suite. Returns (status, exit code).

    In host mode pytest runs in this process's environment. In isolated mode it
    runs inside a container on `network`, which is the only place the service's
    base URL resolves.
    """
    path = stage_path(track, stage)
    if not path.is_dir():
        return rp.ERROR, 3
    log = out_dir / f"stage-{stage}.log"
    counts_path = out_dir / f"stage-{stage}.counts.json"
    pytest_args = [str(path.relative_to(ROOT) if mode == dd.ISOLATED else path),
                   "--base-url", base_url,
                   "-p", "harness.plugin",
                   "--rootdir", f"{track}/test" if mode == dd.ISOLATED
                   else str(ROOT / track / "test"),
                   "-q", *extra, "--harness-summary",
                   f"/out/{counts_path.name}" if mode == dd.ISOLATED else str(counts_path)]
    if mode == dd.ISOLATED:
        cmd = ["docker", "run", "--rm", "--network", network or dd.INTERNAL_NETWORK,
               "-v", f"{ROOT}:/work:ro", "-v", f"{out_dir}:/out",
               "-e", "PYTHONDONTWRITEBYTECODE=1", "-e", "PYTEST_DISABLE_PLUGIN_AUTOLOAD=1",
               "-e", f"COLUMNS={LOG_WIDTH}", "-w", "/work", RUNNER_IMAGE,
               "python", "-m", "pytest", *pytest_args]
    else:
        cmd = [sys.executable, "-m", "pytest", *pytest_args]
    env = {k: v for k, v in os.environ.items() if k not in ("PYTEST_ADDOPTS", "PYTEST_PLUGINS")}
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    # Captured output has no terminal width, so pytest falls back to 80 and truncates a
    # `FAILED <long nodeid> - <reason>` line before the reason, which is the half worth having.
    env["COLUMNS"] = LOG_WIDTH
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT, env=env, timeout=900)
    except subprocess.TimeoutExpired as exc:
        log.write_text(f"suite exceeded 900 seconds\n{exc.stdout!r}\n{exc.stderr!r}\n")
        return rp.ERROR, 3
    try:
        counts = json.loads(counts_path.read_text())
    except (OSError, ValueError):
        counts = {}
    status = (rp.PASS if proc.returncode == 0 and rp.complete_counts(counts)
              else rp.FAIL if proc.returncode == 1 and counts.get("failed", 0) and not counts.get("errors", 0)
              else rp.ERROR)
    log.write_text(f"$ {' '.join(cmd)}\n\n{proc.stdout}\n{proc.stderr}")
    print(f"  stage {stage}: {status}"
          f"  (log: {log.relative_to(ROOT) if log.is_relative_to(ROOT) else log})")
    return status, 0 if status == rp.PASS else proc.returncode or 3


def wait_healthy_inside(base_url: str, network: str, container: str,
                        timeout: float = dd.HEALTH_TIMEOUT) -> None:
    """Poll /health from inside the network, where the service name resolves."""
    import time
    deadline = time.monotonic() + timeout
    last = "no response"
    while time.monotonic() < deadline:
        if not dd.container_running(container):
            raise dd.DockerError(
                f"container exited before becoming healthy.\n{dd.logs(container)}")
        probe = subprocess.run(
            ["docker", "run", "--rm", "--network", network, RUNNER_IMAGE,
             "python", "-c",
             f"import httpx,sys;r=httpx.get('{base_url}/health',timeout=2);"
             "sys.exit(0 if r.status_code==200 and r.json().get('status')=='ok' else 1)"],
            capture_output=True, text=True)
        if probe.returncode == 0:
            return
        last = (probe.stderr or probe.stdout).strip()[-120:] or "not ready"
        time.sleep(1.0)
    raise dd.DockerError(
        f"service did not become healthy at {base_url} within {timeout:.0f}s "
        f"(last: {last})\n{dd.logs(container)}")


def reject(headline: str, problems: list[str], rerun: str = "") -> int:
    """Name every condition that is wrong, each with its fix, then a line to copy.

    One problem per line: a seat that made two mistakes should learn about both
    now, not discover the second after fixing the first.
    """
    print(headline, file=sys.stderr)
    for problem in problems:
        print(f"  - {problem}", file=sys.stderr)
    if rerun:
        print(f"rerun: {rerun}", file=sys.stderr)
    return 2


def corrected_command(args, stages: list[str], *, build: str = "") -> str:
    """The same invocation with the rejected parts replaced by working ones.

    `build` overrides the given directory when that is itself what was rejected;
    echoing the typo back would repeat the mistake rather than correct it.
    """
    parts = ["python -m harness run", f"--track {args.track}"]
    if args.mode == dd.ISOLATED:
        parts.append("--mode isolated")
    source = build or args.build
    if source:
        parts.append(f"--build {source}")
    elif args.mode == dd.ISOLATED:
        parts.append("--build <result repo>")   # it cannot run against --base-url
    else:
        parts.append(f"--base-url {args.base_url}")
    if args.stages:
        parts.append("--stages " + " ".join(stages))
    if args.out:
        parts.append(f"--out {args.out}")
    return " ".join(parts)


PREVIEW_NOTE = ("NOTE: this run only includes a portion of the full tests that are applied before "
                "judging; this is meant to provide directional feedback, and ultimately you may "
                "not pass the stage with the full set of tests.")


def partial_suites(track: str) -> bool:
    """True in the participant package: its graded tracks ship only part of each suite, so
    a run there can show which stages look claimed but cannot know which ones count."""
    return track != "toy" and (ROOT / "kickoff-manifest.json").is_file()


def judges_only(name: str):
    """`harness.<name>`, or None in the participant package, which does not ship it."""
    try:
        return importlib.import_module(f"harness.{name}")
    except ModuleNotFoundError as exc:
        if exc.name != f"harness.{name}":
            raise
        return None


def cmd_run_all(args) -> int:
    """Build every stage folder in a submission and report the contiguous run.

    A stage folder is meant to hold that stage's answer, so this is the whole
    submission's stage chain in one command: the folders that claim their own stage,
    stopping at the first one that does not.
    """
    problems = []
    if not args.repo:
        problems.append("--all scores a submission repository: pass --repo <clone>. "
                        "--build takes one directory and claims nothing")
    if args.stage or args.stages:
        problems.append("--all runs every stage folder, so --stage and --stages have "
                        "nothing left to select; drop them")
    if problems:
        return reject("cannot run every folder:", problems,
                      f"python -m harness run --track {args.track} "
                      f"--repo {args.repo or '<result repo>'} --all")
    repo = pathlib.Path(args.repo)
    published = available_stages(args.track)
    present = [s for s in published if (repo / f"stage-{s}").is_dir()]
    if not present:
        return reject("cannot score this repository:", [
            f"{repo} holds no stage folder; a submission holds stage-1 through "
            f"stage-{published[-1]}, one per stage"])
    root = pathlib.Path(args.out or f"runs/{uuid.uuid4().hex}").resolve()
    try:
        root.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        print(f"{root} already exists; use a fresh output directory to preserve evidence",
              file=sys.stderr)
        return 2
    folders, worst = {}, 0
    for stage in present:
        print(f"stage-{stage}/ ...")
        one = argparse.Namespace(**vars(args))
        one.all, one.stage, one.out = False, stage, str(root / f"stage-{stage}")
        one.in_all = True   # the preview note prints once, after the summary
        # Not `worst or cmd_run(...)`: `or` short-circuits, and a folder that fails
        # must not stop the later folders from being built and reported.
        code = cmd_run(one)
        worst = worst or code
        try:
            body = json.loads((root / f"stage-{stage}" / "report.json").read_text())
        except (OSError, ValueError):
            body = {}
        folders[stage] = {
            "claimed": body.get("claimed_stage") == stage,
            "share": body.get("share") or 0.0,
            "overshoot": body.get("overshoot"),
            "highest_contiguous": body.get("highest_contiguous", 0),
            "report": f"stage-{stage}/report.json",
        }
    ql = judges_only("quality")
    measured = {}
    if ql:
        eligible = []
        for stage in rp.STAGES:
            if folders.get(stage, {}).get("claimed"):
                eligible.append(stage)
            else:
                break
        measured = {"quality": ql.measure_repo(repo, eligible_stages=eligible),
                    "quality_report": "quality.json"}
        rp.write(root / "quality.json", measured["quality"])
    summary = rp.build_summary(args.track, folders, run_id=root.name,
                               mode=args.mode or dd.HOST, **measured,
                               preview=partial_suites(args.track))
    rp.write(root / "summary.json", summary)
    for stage in present:
        folder = folders[stage]
        claim = (f"claims stage {stage} on the shipped checks" if summary["preview"]
                 else f"claims stage {stage}: {folder['share']:.0%} of its own suite")
        print(f"  stage-{stage}/: " + (
            claim if folder["claimed"]
            else f"holds a stage {folder['overshoot']} answer, so it claims nothing"
            if folder["overshoot"] else "does not claim its stage"))
    if ql:
        print(f"code quality: {ql.describe(measured['quality']['score'])}")
        trajectory = measured["quality"]["trajectory"]
        if trajectory["status"] == "measured":
            print("quality change: "
                  f"erosion {trajectory['erosion_change']:+.3f}, "
                  f"verbosity {trajectory['verbosity_change']:+.3f}")
        else:
            print("quality change: unavailable")
        print(f"quality: {root / 'quality.json'}")
    print(f"summary: {root / 'summary.json'}")
    if summary["preview"]:
        print(PREVIEW_NOTE)
    return worst


def cmd_run(args) -> int:
    if getattr(args, "all", False):
        return cmd_run_all(args)
    args.mode = args.mode or dd.HOST
    probe = None
    published = available_stages(args.track)
    if args.repo and (args.previous_build or args.previous_base_url):
        return reject("cannot replace a repository's upgrade source:", [
            "--repo uses its own preceding stage folders; drop --previous-build and --previous-base-url"])
    if args.repo:
        if args.stages:
            return reject("cannot combine --repo with --stages:", [
                "--repo --stage N runs stage N's suite and every earlier one, so "
                "--stages would be discarded. Drop --stages, or use --build <folder> "
                "--stages ... to run an exact set against one directory"],
                f"python -m harness run --track {args.track} --repo {args.repo} "
                f"--stage {args.stage or 'N'}")
        if not args.stage:
            return reject("cannot pick a stage folder:", [
                "--repo holds one folder per stage; pass --stage N to say which one to "
                "build. Its suite and every earlier stage's suite are run against it"],
                f"python -m harness run --track {args.track} --repo {args.repo} --stage 1")
        if args.stage not in published:
            return reject("that stage does not exist:", [
                f"--stage {args.stage} was given, but {args.track} defines stages "
                f"{', '.join(published)}"])
        folder = pathlib.Path(args.repo) / f"stage-{args.stage}"
        if not folder.is_dir():
            return reject("cannot build the service:", [
                f"{folder} does not exist. A submission repository holds one folder per "
                f"stage, named stage-1 through stage-4"])
        # The folder is scored on every suite up to its own number: a stage-3 service
        # that broke stage 1 has not extended anything.
        args.build = str(folder)
        args.stages = [s for s in published if s <= args.stage]
        probe = probe_stage(args.track, args.stage)
    stages = args.stages or published
    problems, seen = [], set()
    for stage in stages:
        if stage in seen:
            problems.append(f"stage {stage!r} is repeated; name each stage once")
        seen.add(stage)
    for stage in dict.fromkeys(stages):
        if stage not in rp.STAGES:
            problems.append(f"{stage!r} is not a stage; {args.track} has {' '.join(published)}")
        elif not stage_path(args.track, stage).is_dir():
            problems.append(f"{args.track} has no stage {stage!r} in this package; "
                            f"it has {' '.join(published)}")
    if problems:
        return reject(f"cannot run {args.track}:", problems,
                      corrected_command(args, published))
    if args.build and not pathlib.Path(args.build).is_dir():
        what = "is a file, not a directory" if pathlib.Path(args.build).exists() else "does not exist"
        return reject("cannot build the service:", [
            f"--build {args.build} {what}; point it at the result repository that "
            f"holds the Dockerfile"],
            corrected_command(args, stages, build="<result repo>"))
    if args.mode == dd.ISOLATED and not args.build:
        return reject("cannot run in isolated mode:", [
            f"isolated mode builds the service itself, but only --base-url "
            f"{args.base_url} was given; pass --build <result repo>, or use "
            f"--mode host to check a service you started yourself"],
            corrected_command(args, stages))
    if args.mode == dd.ISOLATED and args.previous_base_url:
        return reject("cannot use an external upgrade source in isolated mode:", [
            "use --previous-build so both services run on the grading network"])
    run_id = uuid.uuid4().hex
    out_dir = pathlib.Path(args.out or f"runs/{run_id}").resolve()
    try:
        out_dir.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        print(f"{out_dir} already exists; use a fresh output directory to preserve evidence", file=sys.stderr)
        return 2
    started = rp.now()
    metadata = dict(schema_version=2, run_id=run_id, mode=args.mode,
                    provenance="working-tree" if args.build else "external-url",
                    state="running", pytest_args=args.pytest_args,
                    suite_digest=suite_digest(args.track, stages), checks={},
                    overshoot=None, claimed_stage=None, share=None,
                    upgrade_sources={})
    # Judges build from a clone, so the commit behind the tree is there to record.
    # Empty when the source is not a checkout, which is what --base-url always is.
    revision = rp.git_revision(args.repo or args.build) if (args.repo or args.build) else ""
    results = {s: rp.ERROR for s in stages}

    def save():
        body = rp.build(args.track, results, revision=revision, started_at=started,
                        finished_at=rp.now(), **metadata)
        rp.write(out_dir / "report.json", body)
        return body

    save()  # Even SIGKILL leaves an explicit incomplete run, never a previous green report.
    container = image = network = None
    sources = ExitStack()
    worst = 0
    try:
        context = args.build
        if args.build:
            print(f"building {args.build} ...")
            image = dd.build_image(context)
            if args.mode == dd.ISOLATED:
                ensure_runner_image()
                network = dd.ensure_internal_network(f"df-run-{run_id}")
            container, base_url, _ = dd.start_service(image, mode=args.mode, network=network)
            if args.mode == dd.HOST:
                dd.wait_healthy(base_url, container=container, timeout=args.health_timeout)
            else:
                wait_healthy_inside(base_url, network, container, timeout=args.health_timeout)
        else:
            base_url = args.base_url
            dd.wait_healthy(base_url, timeout=args.health_timeout)

        source_urls = {}

        def check_stage(stage, stop_early=False):
            extra = list(args.pytest_args) + (["-x"] if stop_early else [])
            if args.track != 'toy' and int(stage) >= 2:
                folder = (str(pathlib.Path(args.repo) / f'stage-{int(stage) - 1}')
                          if args.repo else args.previous_build)
                previous = args.previous_base_url
                if folder:
                    if folder == args.build:
                        previous = base_url  # the next-stage overshoot probe
                    elif folder in source_urls:
                        previous = source_urls[folder]
                    else:
                        print(f"building upgrade source {folder} ...")
                        source_image = dd.build_image(folder)
                        sources.callback(dd._run, ['docker', 'rmi', '-f', source_image], 120)
                        source_container, previous, _ = dd.start_service(source_image,
                            mode=args.mode, network=network)
                        sources.callback(dd.stop, source_container)
                        if args.mode == dd.HOST:
                            dd.wait_healthy(previous, container=source_container, timeout=args.health_timeout)
                        else:
                            wait_healthy_inside(previous, network, source_container, timeout=args.health_timeout)
                        source_urls[folder] = previous
                    metadata['upgrade_sources'][stage] = dict(folder=folder,
                        revision=rp.git_revision(folder))
                elif previous:
                    metadata['upgrade_sources'][stage] = dict(url=previous, provenance='external-url')
                if previous:
                    extra += ['--previous-base-url', previous]
            return run_stage(args.track, stage, base_url, out_dir, extra,
                             mode=args.mode, network=network)

        for stage in stages:
            status, code = check_stage(stage)
            results[stage] = status
            counts_path = out_dir / f"stage-{stage}.counts.json"
            if counts_path.exists():
                metadata["checks"][stage] = json.loads(counts_path.read_text())
            worst = worst or code
            save()
        if probe and rp.claims(metadata["checks"], args.stage):
            # A stage folder holds that stage's answer. If it also passes the next
            # stage's suite it is a later answer in the wrong folder. The probe's
            # exit code is not this run's: the probe FAILING is the good case.
            # An overshoot needs every next-stage check to pass, so the first failure
            # settles it; the rest of that suite would only burn browser timeouts.
            probe_status, _ = check_stage(probe, stop_early=True)
            if probe_status == rp.PASS:
                metadata["overshoot"] = probe
            save()
        if metadata["suite_digest"] != suite_digest(args.track, stages):
            raise ValueError("conformance sources changed during the check; rerun with a stable release")
        metadata["state"] = "completed"
    except KeyboardInterrupt:
        metadata["state"] = "interrupted"
        worst = 130
    except (dd.DockerError, ValueError, OSError, subprocess.SubprocessError) as exc:
        metadata["state"] = "error"
        (out_dir / "startup.log").write_text(str(exc) + "\n")
        print(f"harness could not complete: {exc}", file=sys.stderr)
        worst = 3
    finally:
        if args.repo:
            claimed = rp.claims(metadata["checks"], args.stage) and not metadata["overshoot"]
            metadata["claimed_stage"] = args.stage if claimed else None
            metadata["share"] = (rp.pass_rate(metadata["checks"].get(args.stage))
                                 if claimed else 0.0)
        report = save()
        sources.close()
        if container:
            dd.stop(container)
        if image:
            dd._run(["docker", "rmi", "-f", image], 120)
        if network:
            dd._run(["docker", "network", "rm", network], 60)
    print(f"highest contiguous stage: {report['highest_contiguous']}")
    if args.repo:
        if metadata["overshoot"]:
            print(f"stage-{args.stage}/ also passes the stage {metadata['overshoot']} "
                  f"suite, so it is not a stage {args.stage} solution")
            print("claimed stage: none")
        elif metadata["claimed_stage"] and partial_suites(args.track):
            print(f"claimed stage: {args.stage} on the shipped checks")
        elif metadata["claimed_stage"]:
            print(f"claimed stage: {args.stage} ({metadata['share']:.0%} of its own suite)")
        else:
            print(f"claimed stage: none (a suite passed under {rp.PASS_BAR:.0%} of its checks)")
    print(f"report: {out_dir / 'report.json'}")
    if args.repo and partial_suites(args.track) and not getattr(args, "in_all", False):
        print(PREVIEW_NOTE)
    return worst


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m harness")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="run a track's suites against a service")
    run.add_argument("--track", required=True, choices=TRACKS)
    source = run.add_mutually_exclusive_group(required=True)
    source.add_argument("--base-url", help="service already running at this URL")
    source.add_argument("--build", help="directory with the service's Dockerfile")
    source.add_argument("--repo", help="submission repository holding stage-N/ folders")
    run.add_argument("--mode", default=None, choices=(dd.HOST, dd.ISOLATED),
                     help="host (default): published port, outbound NOT blocked "
                          "(development). isolated: internal network, no outbound "
                          "(grading)")
    run.add_argument("--stage",
                     help="with --repo: the stage folder to build; its suite and "
                          "every earlier stage's suite are run against it")
    run.add_argument("--all", action="store_true",
                     help="with --repo: build every stage folder and score the "
                          "whole submission; a folder counts only if every earlier "
                          "folder does")
    previous = run.add_mutually_exclusive_group()
    previous.add_argument('--previous-build', help='development: preceding service build directory')
    previous.add_argument('--previous-base-url', help='development: preceding service already running')
    run.add_argument("--stages", nargs="*",
                 help="default: every stage this track ships (1 2 3 4)")
    run.add_argument("--out", help="new directory for logs and report; default: unique runs/<id>")
    run.add_argument("--health-timeout", type=float, default=dd.HEALTH_TIMEOUT)
    run.add_argument("pytest_args", nargs="*", default=[],
                     help="extra arguments passed through to pytest")
    run.set_defaults(func=cmd_run)

    from harness import check as ck
    ck.add_parser(sub)
    for name in ("quality", "judge"):
        module = judges_only(name)
        if module:
            module.add_parser(sub)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
