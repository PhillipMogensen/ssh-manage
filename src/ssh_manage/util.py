from __future__ import annotations

import re
import shlex
import subprocess
from pathlib import Path

from ssh_manage.models import Destination


ALIAS_RE = re.compile(r"^[A-Za-z0-9._-]+$")


class UserFacingError(RuntimeError):
    """Error that should be printed without a traceback."""


def run_command(
    args: list[str],
    *,
    check: bool = True,
    capture: bool = True,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        check=check,
        text=True,
        input=input_text,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
    )


def parse_dest(raw: str, default_port: int = 22) -> Destination:
    if "@" not in raw:
        raise UserFacingError("--dest must be in the form user@host or user@host:port")
    user, host_part = raw.rsplit("@", 1)
    if not user:
        raise UserFacingError("--dest is missing the SSH username")

    port = default_port
    host = host_part
    if host_part.startswith("["):
        closing = host_part.find("]")
        if closing == -1:
            raise UserFacingError("--dest has an unterminated IPv6 host")
        host = host_part[1:closing]
        rest = host_part[closing + 1 :]
        if rest:
            if not rest.startswith(":"):
                raise UserFacingError("--dest IPv6 port must be written as user@[host]:port")
            port = _parse_port(rest[1:])
    elif host_part.count(":") == 1:
        host, port_raw = host_part.rsplit(":", 1)
        port = _parse_port(port_raw)

    if not host:
        raise UserFacingError("--dest is missing the host")
    return Destination(user=user, host=host, port=port)


def validate_alias(alias: str) -> None:
    if not ALIAS_RE.fullmatch(alias):
        raise UserFacingError("Alias must contain only letters, numbers, dots, underscores, and hyphens")


def _parse_port(raw: str) -> int:
    try:
        port = int(raw)
    except ValueError as exc:
        raise UserFacingError("Port must be an integer") from exc
    if port < 1 or port > 65535:
        raise UserFacingError("Port must be between 1 and 65535")
    return port


def shell_quote(value: str) -> str:
    return shlex.quote(value)


def ensure_private_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    path.chmod(0o700)


def format_command(args: list[str]) -> str:
    return " ".join(shlex.quote(arg) for arg in args)
