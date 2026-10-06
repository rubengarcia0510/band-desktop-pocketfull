"""Build and run a submitted service under the resource limits in the spec.

The runner works against any base URL . This module produces one.

Two modes, because "no outbound network at run time" and "reachable from the host"
cannot both hold on one Docker network:

  isolated  Service and harness both attach to an `--internal` network. The service
            is reached by container name and genuinely cannot reach the internet.
            This is the grading mode and the documented single-service grading architecture.
  host      Service on the default bridge with a published port, reached on
            127.0.0.1. Convenient for development. Outbound is NOT blocked --
            a service that fetches a CDN at run time will pass here and fail
            grading, so never score a submission from this mode.

Limits, from the spec's "Resource limits" table:
    CPU 2 vCPU · memory 2 GiB · 60 s to first healthy response
"""
from __future__ import annotations

import contextlib
import pathlib
import socket
import subprocess
import time
import uuid

import httpx

CPUS = "2"
MEMORY = "2g"
HEALTH_TIMEOUT = 60.0
BUILD_TIMEOUT = 1800.0
CONTAINER_PORT = 8080
INTERNAL_NETWORK = "df-harness-internal"

ISOLATED, HOST = "isolated", "host"


class DockerError(RuntimeError):
    """A docker command failed, or the service never became healthy."""


def _run(args: list[str], timeout: float) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise DockerError(f"`{' '.join(args[:3])}...` timed out after {timeout}s") from exc
    except FileNotFoundError as exc:
        raise DockerError("docker is not installed or not on PATH") from exc


def free_port() -> int:
    with contextlib.closing(socket.socket()) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def build_image(context: pathlib.Path | str, tag: str | None = None,
                dockerfile: str | None = None) -> str:
    """Build `context`'s Dockerfile. Outbound network is available here, by design."""
    context = pathlib.Path(context)
    df = pathlib.Path(dockerfile) if dockerfile else context / "Dockerfile"
    if not df.is_file():
        raise DockerError(f"no Dockerfile at {df}")
    tag = tag or f"df-harness/{uuid.uuid4().hex[:12]}"
    args = ["docker", "build", "-t", tag, "-f", str(df), str(context)]
    proc = _run(args, BUILD_TIMEOUT)
    if proc.returncode != 0:
        raise DockerError(f"docker build failed:\n{proc.stdout}\n{proc.stderr}")
    return tag


def ensure_internal_network(name: str = INTERNAL_NETWORK) -> str:
    """An internal bridge network: containers on it reach each other and nothing else.

    Verified behaviour: container-to-container works, outbound is refused, and a
    published port does NOT reach it -- which is why `host` mode exists separately.
    """
    if _run(["docker", "network", "inspect", name], 30).returncode == 0:
        return name
    proc = _run(["docker", "network", "create", "--internal", name], 60)
    if proc.returncode != 0 and "already exists" not in proc.stderr:
        raise DockerError(f"could not create network {name}: {proc.stderr}")
    return name


def container_running(container: str) -> bool:
    proc = _run(["docker", "inspect", "-f", "{{.State.Running}}", container], 30)
    return proc.returncode == 0 and proc.stdout.strip() == "true"


def logs(container: str, tail: int = 80) -> str:
    proc = _run(["docker", "logs", "--tail", str(tail), container], 30)
    return f"--- container logs ({container}) ---\n{proc.stdout}{proc.stderr}"


def wait_healthy(base_url: str, timeout: float = HEALTH_TIMEOUT,
                 container: str | None = None) -> float:
    """Poll GET /health until it returns 200 {"status": "ok"}.

    Anything other than 200 before the deadline is fine and not an error, per the
    spec. Fails loudly -- never hangs -- on a service that binds nothing.
    """
    deadline = time.monotonic() + timeout
    last = "no response"
    while time.monotonic() < deadline:
        if container and not container_running(container):
            raise DockerError(
                f"container exited before becoming healthy.\n{logs(container)}")
        try:
            resp = httpx.get(f"{base_url}/health", timeout=2.0)
            if resp.status_code == 200:
                try:
                    if resp.json().get("status") == "ok":
                        return timeout - (deadline - time.monotonic())
                    last = f"200 but body was {resp.text[:120]!r}"
                except ValueError:
                    last = f"200 but body was not JSON: {resp.text[:120]!r}"
            else:
                last = str(resp.status_code)
        except httpx.HTTPError as exc:
            last = type(exc).__name__
        time.sleep(0.25)
    detail = f"\n{logs(container)}" if container else ""
    raise DockerError(
        f"service did not serve 200 {{'status':'ok'}} at {base_url}/health "
        f"within {timeout:.0f}s (last: {last}){detail}")


def start_service(image: str, *, mode: str = HOST, name: str | None = None,
                  network: str | None = None) -> tuple[str, str, str]:
    """Start `image` under the spec's limits. Returns (container, base_url, network).

    In isolated mode `base_url` is only resolvable from inside `network`.
    """
    name = name or f"df-svc-{uuid.uuid4().hex[:12]}"
    args = ["docker", "run", "-d", "--name", name,
            "--cpus", CPUS, "--memory", MEMORY,
            "-e", f"PORT={CONTAINER_PORT}"]
    if mode == ISOLATED:
        network = network or ensure_internal_network()
        args += ["--network", network]
        base_url = f"http://{name}:{CONTAINER_PORT}"
    elif mode == HOST:
        port = free_port()
        if network:
            args += ["--network", network]
        args += ["-p", f"127.0.0.1:{port}:{CONTAINER_PORT}"]
        base_url = f"http://127.0.0.1:{port}"
    else:
        raise ValueError(f"mode must be {ISOLATED!r} or {HOST!r}, not {mode!r}")
    args.append(image)
    proc = _run(args, 120)
    if proc.returncode != 0:
        raise DockerError(f"docker run failed: {proc.stderr}")
    return name, base_url, network or "bridge"


def stop(container: str) -> None:
    _run(["docker", "rm", "-f", container], 60)


@contextlib.contextmanager
def service(context: pathlib.Path | str, *, mode: str = HOST,
            tag: str | None = None, keep_image: bool = False):
    """Build and run a service from `context`; yield (base_url, container_name).

    In host mode the yielded URL is reachable from this process. In isolated mode
    it is not -- only from a container on the same network.
    """
    image = build_image(context, tag)
    container, base_url, _ = start_service(image, mode=mode)
    try:
        if mode == HOST:
            wait_healthy(base_url, container=container)
        yield base_url, container
    finally:
        stop(container)
        if not keep_image and tag is None:
            _run(["docker", "rmi", "-f", image], 120)
