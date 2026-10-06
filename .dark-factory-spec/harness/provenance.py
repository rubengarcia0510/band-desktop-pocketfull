"""Pin build inputs and identify the exact conformance sources used."""
import hashlib
import pathlib
import subprocess

ROOT = pathlib.Path(__file__).resolve().parent.parent
STAGE_DIRS = {'1': 'stage_1', '2': 'stage_2', '3': 'stage_3', '4': 'stage_4'}


def git(repo, *args):
    result = subprocess.run(['git', '-C', str(repo), *args], capture_output=True,
                            text=True, timeout=60, check=False)
    if result.returncode:
        raise ValueError(result.stderr.strip() or 'git command failed')
    return result.stdout.strip()


def suite_digest(track, stages):
    """Digest relative names and bytes, independent of checkout path and mtimes.

    Records which suite bytes a run used. It hashes the LOCAL checkout, so it does not
    detect edited tests: a team that edits a suite gets a digest matching their edit.
    Tampering is caught by judges running their own pristine harness against the
    submitted stage folders.
    """
    files = set((ROOT / 'harness').glob('*.py'))
    # check.py, vocabulary.py and evidence.py act before and after a run, never
    # during it: they cannot change what a run decided, and pinning them would invalidate
    # reports whenever one is fixed. Internal export/rehearsal tools are excluded
    # too, so the judges export has the same grading digest as its source tree.
    files = {p for p in files if not p.name.startswith('test_') and p.name not in
             {'agent.py', 'validate.py', 'release.py', 'publish.py', 'rehearse.py',
              'reference_submission.py',
              'check.py', 'vocabulary.py', 'artifacts.py', 'mandate_audit.py',
              'evidence.py'}}
    files.update(ROOT / 'harness' / name for name in ('Dockerfile', 'requirements.txt'))
    tests = ROOT / track / 'test'
    files.update(tests.glob('*.py'))
    for stage in stages:
        files.update((tests / STAGE_DIRS[stage]).rglob('*.py'))
    digest = hashlib.sha256()
    for path in sorted(files):
        digest.update(path.relative_to(ROOT).as_posix().encode() + b'\0')
        digest.update(path.read_bytes() + b'\0')
    return digest.hexdigest()
