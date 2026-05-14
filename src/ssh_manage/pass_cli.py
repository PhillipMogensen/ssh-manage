from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from typing import Any

from ssh_manage.models import ManagedEntry
from ssh_manage.util import UserFacingError, run_command


FIELD_ALIAS = "ssh_manage_alias"
FIELD_HOST = "ssh_manage_host"
FIELD_USER = "ssh_manage_user"
FIELD_PORT = "ssh_manage_port"
FIELD_PUBLIC_KEY = "ssh_manage_public_key"
FIELD_PASSWORD_ITEM = "ssh_manage_password_item"

SSH_MANAGE_FIELDS = {
    FIELD_ALIAS,
    FIELD_HOST,
    FIELD_USER,
    FIELD_PORT,
    FIELD_PUBLIC_KEY,
    FIELD_PASSWORD_ITEM,
}


@dataclass
class PassCli:
    binary: str = "pass-cli"

    def exists(self) -> bool:
        return shutil.which(self.binary) is not None

    def require(self) -> None:
        if not self.exists():
            raise UserFacingError("pass-cli is not installed. Run `ssh-manage install --vault <vault>` first.")

    def is_logged_in(self) -> bool:
        if not self.exists():
            return False
        result = run_command([self.binary, "info", "--output", "json"], check=False)
        return result.returncode == 0

    def login(self) -> None:
        run_command([self.binary, "login"], check=True, capture=False)

    def read_password(self, *, vault: str, item_title: str) -> str:
        result = run_command(
            [
                self.binary,
                "item",
                "view",
                "--vault-name",
                vault,
                "--item-title",
                item_title,
                "--field",
                "password",
            ],
            check=False,
        )
        if result.returncode != 0:
            raise UserFacingError(_stderr_or_default(result.stderr, f"Could not read password item {item_title!r}"))
        password = result.stdout.strip()
        if not password:
            raise UserFacingError(f"Password item {item_title!r} returned an empty password")
        return password

    def create_login(self, *, vault: str, title: str, username: str, password: str, url: str) -> None:
        payload = json.dumps(
            {
                "title": title,
                "username": username,
                "password": password,
                "urls": [url],
            }
        )
        result = run_command(
            [
                self.binary,
                "item",
                "create",
                "login",
                "--vault-name",
                vault,
                "--from-template",
                "-",
            ],
            check=False,
            input_text=payload,
        )
        if result.returncode != 0:
            raise UserFacingError(_stderr_or_default(result.stderr, f"Could not create login item {title!r}"))

    def import_ssh_key(self, *, vault: str, title: str, private_key_path: str) -> None:
        result = run_command(
            [
                self.binary,
                "item",
                "create",
                "ssh-key",
                "import",
                "--from-private-key",
                private_key_path,
                "--vault-name",
                vault,
                "--title",
                title,
            ],
            check=False,
        )
        if result.returncode != 0:
            raise UserFacingError(_stderr_or_default(result.stderr, f"Could not import SSH key {title!r}"))

    def update_fields(self, *, vault: str, item_title: str, fields: dict[str, str]) -> None:
        args = [
            self.binary,
            "item",
            "update",
            "--vault-name",
            vault,
            "--item-title",
            item_title,
        ]
        for key, value in fields.items():
            args.extend(["--field", f"{key}={value}"])
        result = run_command(args, check=False)
        if result.returncode != 0:
            raise UserFacingError(_stderr_or_default(result.stderr, f"Could not update SSH key {item_title!r}"))

    def item_exists(self, *, vault: str, item_title: str) -> bool:
        result = run_command(
            [
                self.binary,
                "item",
                "view",
                "--vault-name",
                vault,
                "--item-title",
                item_title,
                "--output",
                "json",
            ],
            check=False,
        )
        return result.returncode == 0

    def load_agent(self, *, vault: str) -> None:
        result = run_command(
            [self.binary, "ssh-agent", "daemon", "start", "--vault-name", vault],
            check=False,
        )
        if result.returncode != 0 and "already" not in (result.stderr + result.stdout).lower():
            # Fall back to a foreground-load refresh when the daemon is already managed by launchd.
            load = run_command([self.binary, "ssh-agent", "load", "--vault-name", vault], check=False)
            if load.returncode != 0:
                raise UserFacingError(_stderr_or_default(load.stderr, "Could not refresh Proton SSH agent"))

    def list_managed_entries(self, *, vault: str) -> list[ManagedEntry]:
        result = run_command(
            [
                self.binary,
                "item",
                "list",
                vault,
                "--filter-type",
                "ssh-key",
                "--filter-state",
                "active",
                "--output",
                "json",
            ],
            check=False,
        )
        if result.returncode != 0:
            raise UserFacingError(_stderr_or_default(result.stderr, f"Could not list SSH keys in {vault!r}"))
        items = _as_items(_parse_json(result.stdout))
        entries: list[ManagedEntry] = []
        for item in items:
            viewed = self._view_item(vault=vault, item=item)
            fields = extract_fields(viewed)
            if not fields.get(FIELD_ALIAS):
                continue
            missing = [field for field in (FIELD_HOST, FIELD_USER, FIELD_PUBLIC_KEY) if not fields.get(field)]
            if missing:
                raise UserFacingError(
                    f"Managed item {item_display_name(viewed)!r} is missing fields: {', '.join(missing)}"
                )
            entries.append(
                ManagedEntry(
                    alias=fields[FIELD_ALIAS],
                    user=fields[FIELD_USER],
                    host=fields[FIELD_HOST],
                    port=int(fields.get(FIELD_PORT) or "22"),
                    public_key=fields[FIELD_PUBLIC_KEY],
                    password_item=fields.get(FIELD_PASSWORD_ITEM),
                    item_title=item_display_name(viewed),
                )
            )
        return entries

    def _view_item(self, *, vault: str, item: dict[str, Any]) -> dict[str, Any]:
        item_id = _first_string(item, ("item_id", "itemId", "id", "ID"))
        title = item_display_name(item)
        args = [self.binary, "item", "view", "--vault-name", vault, "--output", "json"]
        if item_id:
            args.extend(["--item-id", item_id])
        elif title:
            args.extend(["--item-title", title])
        else:
            return item
        result = run_command(args, check=False)
        if result.returncode != 0:
            return item
        try:
            parsed = _parse_json(result.stdout)
        except UserFacingError:
            return item
        return parsed if isinstance(parsed, dict) else item


def managed_fields_for(
    *, alias: str, user: str, host: str, port: int, public_key: str, password_item: str
) -> dict[str, str]:
    return {
        FIELD_ALIAS: alias,
        FIELD_HOST: host,
        FIELD_USER: user,
        FIELD_PORT: str(port),
        FIELD_PUBLIC_KEY: public_key,
        FIELD_PASSWORD_ITEM: password_item,
    }


def extract_fields(data: Any) -> dict[str, str]:
    fields: dict[str, str] = {}
    _extract_fields(data, fields)
    return fields


def item_display_name(data: dict[str, Any]) -> str | None:
    return _first_string(data, ("title", "name", "item_title", "itemTitle")) or _nested_name(data)


def _extract_fields(data: Any, out: dict[str, str]) -> None:
    if isinstance(data, dict):
        for key in SSH_MANAGE_FIELDS:
            value = data.get(key)
            if isinstance(value, (str, int)) and key not in out:
                out[key] = str(value)

        label = _first_string(data, ("name", "label", "fieldName", "title"))
        value = data.get("value", data.get("content", data.get("text")))
        if label in SSH_MANAGE_FIELDS and isinstance(value, (str, int)) and label not in out:
            out[label] = str(value)

        for child in data.values():
            _extract_fields(child, out)
    elif isinstance(data, list):
        for child in data:
            _extract_fields(child, out)


def _as_items(parsed: Any) -> list[dict[str, Any]]:
    if isinstance(parsed, list):
        return [item for item in parsed if isinstance(item, dict)]
    if isinstance(parsed, dict):
        for key in ("items", "data", "results"):
            value = parsed.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def _parse_json(raw: str) -> Any:
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise UserFacingError("pass-cli returned invalid JSON") from exc


def _first_string(data: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = data.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _nested_name(data: dict[str, Any]) -> str | None:
    for key in ("metadata", "item", "content"):
        value = data.get(key)
        if isinstance(value, dict):
            found = _first_string(value, ("title", "name"))
            if found:
                return found
    return None


def _stderr_or_default(stderr: str | None, default: str) -> str:
    return (stderr or "").strip() or default
