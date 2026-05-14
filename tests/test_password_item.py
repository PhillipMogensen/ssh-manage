from __future__ import annotations

import argparse

from ssh_manage.cli import _get_or_create_password_item
from ssh_manage.models import Destination


class FakePassCli:
    def __init__(self, exists: bool) -> None:
        self.exists = exists
        self.created = None

    def item_exists(self, *, vault: str, item_title: str) -> bool:
        assert vault == "SSH Keys"
        assert item_title == "Proxmox host"
        return self.exists

    def read_password(self, *, vault: str, item_title: str) -> str:
        assert vault == "SSH Keys"
        assert item_title == "Proxmox host"
        return "existing-secret"

    def create_login(self, **kwargs) -> None:  # noqa: ANN003
        self.created = kwargs


def test_existing_password_item_is_read() -> None:
    fake = FakePassCli(exists=True)
    password = _get_or_create_password_item(
        fake,
        args=argparse.Namespace(vault="SSH Keys", name="Proxmox host"),
        destination=Destination(user="root", host="192.168.0.200"),
    )
    assert password == "existing-secret"
    assert fake.created is None


def test_missing_password_item_is_created(monkeypatch) -> None:  # noqa: ANN001
    fake = FakePassCli(exists=False)
    monkeypatch.setattr("ssh_manage.cli.getpass.getpass", lambda prompt: "new-secret")

    password = _get_or_create_password_item(
        fake,
        args=argparse.Namespace(vault="SSH Keys", name="Proxmox host"),
        destination=Destination(user="root", host="192.168.0.200"),
    )

    assert password == "new-secret"
    assert fake.created == {
        "vault": "SSH Keys",
        "title": "Proxmox host",
        "username": "root",
        "password": "new-secret",
        "url": "ssh://192.168.0.200:22",
    }
