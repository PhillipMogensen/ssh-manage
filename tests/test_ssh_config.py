from __future__ import annotations

from pathlib import Path

from ssh_manage.models import ManagedEntry
from ssh_manage.ssh_config import INCLUDE_LINE, write_managed_config


def test_write_managed_config_adds_include_and_alias(tmp_path: Path) -> None:
    ssh_config = tmp_path / ".ssh" / "config"
    managed_config = tmp_path / ".ssh" / "ssh-manage" / "config"
    keys_dir = tmp_path / ".ssh" / "ssh-manage" / "keys"
    agent_socket = tmp_path / ".ssh" / "proton-pass-agent.sock"
    ssh_config.parent.mkdir(parents=True)
    ssh_config.write_text("Host existing\n    HostName example.com\n", encoding="utf-8")

    write_managed_config(
        [
            ManagedEntry(
                alias="prod",
                user="root",
                host="192.0.2.10",
                port=22,
                public_key="ssh-ed25519 AAA prod",
            )
        ],
        ssh_config_path=ssh_config,
        managed_config_path=managed_config,
        keys_dir=keys_dir,
        agent_socket=agent_socket,
    )

    assert ssh_config.read_text(encoding="utf-8").splitlines()[0] == INCLUDE_LINE
    config = managed_config.read_text(encoding="utf-8")
    assert "Host prod" in config
    assert f"IdentityAgent {agent_socket}" in config
    assert (keys_dir / "prod.pub").read_text(encoding="utf-8") == "ssh-ed25519 AAA prod\n"


def test_write_managed_config_does_not_duplicate_include(tmp_path: Path) -> None:
    ssh_config = tmp_path / ".ssh" / "config"
    managed_config = tmp_path / ".ssh" / "ssh-manage" / "config"
    keys_dir = tmp_path / ".ssh" / "ssh-manage" / "keys"
    ssh_config.parent.mkdir(parents=True)
    ssh_config.write_text(f"{INCLUDE_LINE}\n", encoding="utf-8")

    write_managed_config([], ssh_config_path=ssh_config, managed_config_path=managed_config, keys_dir=keys_dir)
    write_managed_config([], ssh_config_path=ssh_config, managed_config_path=managed_config, keys_dir=keys_dir)

    assert ssh_config.read_text(encoding="utf-8").count(INCLUDE_LINE) == 1
