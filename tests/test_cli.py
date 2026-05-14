from __future__ import annotations

from ssh_manage.cli import main


def test_dry_run_does_not_require_pass_cli_login(capsys) -> None:  # noqa: ANN001
    code = main(
        [
            "--name",
            "login",
            "--dest",
            "user@example.com:2222",
            "--alias",
            "prod",
            "--vault",
            "Vault",
            "--dry-run",
        ]
    )

    assert code == 0
    assert "Would read password item" in capsys.readouterr().out
