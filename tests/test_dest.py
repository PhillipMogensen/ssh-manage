from __future__ import annotations

import pytest

from ssh_manage.util import UserFacingError, parse_dest, validate_alias


def test_parse_dest_with_default_port() -> None:
    dest = parse_dest("root@192.0.2.10")
    assert dest.user == "root"
    assert dest.host == "192.0.2.10"
    assert dest.port == 22


def test_parse_dest_with_port() -> None:
    dest = parse_dest("ubuntu@example.com:2200")
    assert dest.user == "ubuntu"
    assert dest.host == "example.com"
    assert dest.port == 2200


def test_parse_dest_with_ipv6_port() -> None:
    dest = parse_dest("root@[2001:db8::1]:2222")
    assert dest.host == "2001:db8::1"
    assert dest.port == 2222


def test_validate_alias_rejects_spaces() -> None:
    with pytest.raises(UserFacingError):
        validate_alias("bad alias")
