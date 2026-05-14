from __future__ import annotations

from ssh_manage.bootstrap import _authorized_keys_command


def test_authorized_keys_command_is_idempotent() -> None:
    command = _authorized_keys_command("ssh-ed25519 AAA test")
    assert "grep -qxF" in command
    assert "authorized_keys" in command
    assert "chmod 600 ~/.ssh/authorized_keys" in command
