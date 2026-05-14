from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ssh_manage.models import Destination
from ssh_manage.util import UserFacingError, ensure_private_dir, shell_quote


@dataclass(frozen=True)
class BootstrapResult:
    added: bool


def install_public_key_with_password(
    *,
    destination: Destination,
    password: str,
    public_key: str,
    accept_unknown_host: bool = False,
) -> BootstrapResult:
    try:
        import paramiko
    except ModuleNotFoundError as exc:
        raise UserFacingError(
            "Password bootstrap requires Paramiko. Install with `uv sync --extra bootstrap` "
            "or `pip install 'ssh-manage[bootstrap]'`."
        ) from exc

    known_hosts_path = Path.home() / ".ssh" / "known_hosts"
    ensure_private_dir(known_hosts_path.parent)
    known_hosts_path.touch(exist_ok=True)
    known_hosts_path.chmod(0o600)

    client = paramiko.SSHClient()
    client.load_system_host_keys()
    client.load_host_keys(str(known_hosts_path))
    client.set_missing_host_key_policy(_PromptHostKeyPolicy(accept_unknown_host, known_hosts_path))
    try:
        client.connect(
            destination.host,
            port=destination.port,
            username=destination.user,
            password=password,
            look_for_keys=False,
            allow_agent=False,
            timeout=20,
        )
        command = _authorized_keys_command(public_key)
        _, stdout, stderr = client.exec_command(command)
        exit_status = stdout.channel.recv_exit_status()
        if exit_status != 0:
            err = stderr.read().decode("utf-8", errors="replace").strip()
            raise UserFacingError(err or "Failed to update remote authorized_keys")
    finally:
        client.close()
    return BootstrapResult(added=True)


class _PromptHostKeyPolicy:
    def __init__(self, accept_unknown_host: bool, known_hosts_path: Path) -> None:
        self.accept_unknown_host = accept_unknown_host
        self.known_hosts_path = known_hosts_path

    def missing_host_key(self, client, hostname, key) -> None:  # noqa: ANN001
        fingerprint = key.get_fingerprint().hex(":")
        if self.accept_unknown_host:
            client.get_host_keys().add(hostname, key.get_name(), key)
            client.save_host_keys(str(self.known_hosts_path))
            return
        response = input(
            f"Unknown host key for {hostname} ({key.get_name()} SHA256/hex {fingerprint}). Trust it? [y/N] "
        )
        if response.strip().lower() not in {"y", "yes"}:
            raise UserFacingError("Host key was not trusted")
        client.get_host_keys().add(hostname, key.get_name(), key)
        client.save_host_keys(str(self.known_hosts_path))


def _authorized_keys_command(public_key: str) -> str:
    quoted_key = shell_quote(public_key.strip())
    return (
        "umask 077; "
        "mkdir -p ~/.ssh; "
        "touch ~/.ssh/authorized_keys; "
        f"grep -qxF {quoted_key} ~/.ssh/authorized_keys "
        f"|| printf '%s\\n' {quoted_key} >> ~/.ssh/authorized_keys; "
        "chmod 700 ~/.ssh; "
        "chmod 600 ~/.ssh/authorized_keys"
    )
