from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Destination:
    user: str
    host: str
    port: int = 22


@dataclass(frozen=True)
class ManagedEntry:
    alias: str
    user: str
    host: str
    port: int
    public_key: str
    password_item: str | None = None
    item_title: str | None = None
