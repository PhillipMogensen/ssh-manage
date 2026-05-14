from __future__ import annotations

import subprocess

from ssh_manage.pass_cli import PassCli
from ssh_manage.pass_cli import FIELD_ALIAS, FIELD_HOST, FIELD_PUBLIC_KEY, FIELD_USER, extract_fields


def test_extract_fields_from_custom_field_list() -> None:
    data = {
        "title": "ssh-manage/prod",
        "customFields": [
            {"name": FIELD_ALIAS, "value": "prod"},
            {"name": FIELD_HOST, "value": "192.0.2.10"},
            {"name": FIELD_USER, "value": "root"},
            {"name": FIELD_PUBLIC_KEY, "value": "ssh-ed25519 AAA test"},
        ],
    }
    assert extract_fields(data)[FIELD_ALIAS] == "prod"
    assert extract_fields(data)[FIELD_HOST] == "192.0.2.10"


def test_extract_fields_from_direct_shape() -> None:
    data = {
        FIELD_ALIAS: "prod",
        FIELD_HOST: "host",
        FIELD_USER: "user",
        FIELD_PUBLIC_KEY: "key",
    }
    fields = extract_fields(data)
    assert fields[FIELD_ALIAS] == "prod"
    assert fields[FIELD_USER] == "user"


def test_create_login_uses_stdin_template(monkeypatch) -> None:  # noqa: ANN001
    calls = []

    def fake_run_command(args, *, check=True, capture=True, input_text=None):  # noqa: ANN001, ARG001
        calls.append((args, input_text))
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr("ssh_manage.pass_cli.run_command", fake_run_command)

    PassCli().create_login(
        vault="SSH Keys",
        title="Proxmox host",
        username="root",
        password="secret",
        url="ssh://192.168.0.200:22",
    )

    args, input_text = calls[0]
    assert args == [
        "pass-cli",
        "item",
        "create",
        "login",
        "--vault-name",
        "SSH Keys",
        "--from-template",
        "-",
    ]
    assert '"password": "secret"' in input_text
