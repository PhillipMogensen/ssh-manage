from __future__ import annotations

import argparse
import getpass
import sys
import tempfile
from pathlib import Path

from ssh_manage.bootstrap import install_public_key_with_password
from ssh_manage.installer import configure_agent, configure_shell_profile, install_pass_cli_if_needed
from ssh_manage.keygen import generate_ed25519_key
from ssh_manage.models import ManagedEntry
from ssh_manage.pass_cli import PassCli, managed_fields_for
from ssh_manage.ssh_config import AGENT_SOCKET, CONFIG_PATH, INCLUDE_LINE, SSH_CONFIG_PATH, write_managed_config
from ssh_manage.util import UserFacingError, format_command, parse_dest, run_command, validate_alias


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return dispatch(args, parser)
    except UserFacingError as exc:
        print(f"ssh-manage: {exc}", file=sys.stderr)
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ssh-manage")
    _add_entry_flags(parser)
    subparsers = parser.add_subparsers(dest="command")

    add_parser = subparsers.add_parser("add", help="Create a Proton-backed SSH alias")
    _add_entry_flags(add_parser, required=True)

    install_parser = subparsers.add_parser("install", help="Install pass-cli and configure the Proton SSH agent")
    install_parser.add_argument("--vault", required=True, help="Proton Pass vault that stores SSH keys")

    sync_parser = subparsers.add_parser("sync", help="Rebuild local SSH aliases from Proton metadata")
    sync_parser.add_argument("--vault", required=True, help="Proton Pass vault that stores SSH keys")

    subparsers.add_parser("doctor", help="Check local ssh-manage setup")
    return parser


def dispatch(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    command = args.command
    if command == "install":
        return install(args)
    if command == "sync":
        return sync(args)
    if command == "doctor":
        return doctor()
    if command == "add" or _root_add_flags_present(args):
        return add(args)
    parser.print_help()
    return 2


def install(args: argparse.Namespace) -> int:
    pass_cli = PassCli()
    install_pass_cli_if_needed(pass_cli)
    if not pass_cli.is_logged_in():
        print("Logging in to Proton Pass CLI...")
        pass_cli.login()
    configure_agent(pass_cli, vault=args.vault)
    profile = configure_shell_profile()
    print(f"Configured Proton Pass SSH agent at {AGENT_SOCKET}")
    print(f"Updated shell profile: {profile}")
    print("Open a new shell or source the profile before using ssh aliases.")
    return 0


def add(args: argparse.Namespace) -> int:
    _require_entry_args(args)
    validate_alias(args.alias)
    destination = parse_dest(args.dest, default_port=args.port)
    item_title = f"ssh-manage/{args.alias}"
    if args.dry_run:
        _print_add_plan(args, destination, item_title)
        return 0

    pass_cli = PassCli()
    pass_cli.require()
    if not pass_cli.is_logged_in():
        raise UserFacingError("pass-cli is not logged in. Run `pass-cli login` or `ssh-manage install`.")
    item_exists = pass_cli.item_exists(vault=args.vault, item_title=item_title)
    if item_exists:
        if not args.force:
            raise UserFacingError(f"SSH key item {item_title!r} already exists. Use --force to refresh local config.")
        entries = pass_cli.list_managed_entries(vault=args.vault)
        if not any(entry.alias == args.alias for entry in entries):
            raise UserFacingError(
                f"SSH key item {item_title!r} exists but has no ssh-manage metadata for alias {args.alias!r}."
            )
        write_managed_config(entries)
        pass_cli.load_agent(vault=args.vault)
        _verify_ssh_config(args.alias)
        print(f"Refreshed `ssh {args.alias}` from existing Proton metadata")
        return 0

    password = _get_or_create_password_item(pass_cli, args=args, destination=destination)
    with tempfile.TemporaryDirectory(prefix="ssh-manage-") as temp_dir:
        key_path = Path(temp_dir) / "id_ed25519"
        generated = generate_ed25519_key(key_path, comment=f"ssh-manage:{args.alias}")
        pass_cli.import_ssh_key(
            vault=args.vault,
            title=item_title,
            private_key_path=str(generated.private_key),
        )
        install_public_key_with_password(
            destination=destination,
            password=password,
            public_key=generated.public_key_text,
            accept_unknown_host=args.yes,
        )
        pass_cli.update_fields(
            vault=args.vault,
            item_title=item_title,
            fields=managed_fields_for(
                alias=args.alias,
                user=destination.user,
                host=destination.host,
                port=destination.port,
                public_key=generated.public_key_text,
                password_item=args.name,
            ),
        )
        entry = ManagedEntry(
            alias=args.alias,
            user=destination.user,
            host=destination.host,
            port=destination.port,
            public_key=generated.public_key_text,
            password_item=args.name,
            item_title=item_title,
        )
        entries = _replace_entry(pass_cli.list_managed_entries(vault=args.vault), entry)
        write_managed_config(entries)
    pass_cli.load_agent(vault=args.vault)
    _verify_ssh_config(args.alias)
    print(f"Configured `ssh {args.alias}`")
    return 0


def sync(args: argparse.Namespace) -> int:
    pass_cli = PassCli()
    pass_cli.require()
    if not pass_cli.is_logged_in():
        raise UserFacingError("pass-cli is not logged in. Run `pass-cli login` or `ssh-manage install`.")
    entries = pass_cli.list_managed_entries(vault=args.vault)
    write_managed_config(entries)
    print(f"Synced {len(entries)} SSH alias(es) to {CONFIG_PATH}")
    return 0


def doctor() -> int:
    pass_cli = PassCli()
    checks = [
        ("pass-cli installed", pass_cli.exists()),
        ("pass-cli logged in", pass_cli.is_logged_in()),
        ("agent socket exists", AGENT_SOCKET.exists()),
        ("ssh config exists", SSH_CONFIG_PATH.exists()),
        ("ssh config includes managed file", _config_has_include()),
        ("managed config exists", CONFIG_PATH.exists()),
    ]
    failed = False
    for label, ok in checks:
        print(f"{'ok' if ok else 'fail'}  {label}")
        failed = failed or not ok
    return 1 if failed else 0


def _add_entry_flags(parser: argparse.ArgumentParser, *, required: bool = False) -> None:
    parser.add_argument("--name", required=required, help="Existing Proton Pass login item with bootstrap password")
    parser.add_argument("--dest", required=required, help="SSH destination, e.g. user@host or user@host:2222")
    parser.add_argument("--alias", required=required, help="OpenSSH host alias to create")
    parser.add_argument("--vault", required=required, help="Proton Pass vault name")
    parser.add_argument("--port", type=int, default=22, help="Default port when --dest omits one")
    parser.add_argument("--yes", action="store_true", help="Trust unknown host keys without prompting")
    parser.add_argument("--force", action="store_true", help="Refresh local config for an existing managed key item")
    parser.add_argument("--dry-run", action="store_true", help="Print planned actions without changing anything")


def _root_add_flags_present(args: argparse.Namespace) -> bool:
    return all(getattr(args, name, None) for name in ("name", "dest", "alias", "vault"))


def _require_entry_args(args: argparse.Namespace) -> None:
    missing = [name for name in ("name", "dest", "alias", "vault") if not getattr(args, name, None)]
    if missing:
        raise UserFacingError(f"Missing required add option(s): {', '.join('--' + name for name in missing)}")


def _replace_entry(entries: list[ManagedEntry], new_entry: ManagedEntry) -> list[ManagedEntry]:
    return [entry for entry in entries if entry.alias != new_entry.alias] + [new_entry]


def _get_or_create_password_item(pass_cli: PassCli, *, args: argparse.Namespace, destination) -> str:  # noqa: ANN001
    if pass_cli.item_exists(vault=args.vault, item_title=args.name):
        return pass_cli.read_password(vault=args.vault, item_title=args.name)

    password = getpass.getpass(
        f"Password for {destination.user}@{destination.host} to create Proton login item {args.name!r}: "
    )
    if not password:
        raise UserFacingError("Password cannot be empty")
    pass_cli.create_login(
        vault=args.vault,
        title=args.name,
        username=destination.user,
        password=password,
        url=f"ssh://{destination.host}:{destination.port}",
    )
    print(f"Created Proton Pass login item {args.name!r}")
    return password


def _verify_ssh_config(alias: str) -> None:
    result = run_command(["ssh", "-G", alias], check=False)
    if result.returncode != 0:
        raise UserFacingError((result.stderr or "").strip() or f"ssh -G {alias} failed")


def _config_has_include() -> bool:
    if not SSH_CONFIG_PATH.exists():
        return False
    return any(line.strip() == INCLUDE_LINE for line in SSH_CONFIG_PATH.read_text(encoding="utf-8").splitlines())


def _print_add_plan(args: argparse.Namespace, destination, item_title: str) -> None:  # noqa: ANN001
    keygen_cmd = ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", f"ssh-manage:{args.alias}"]
    print(f"Would read password item: {args.name!r} in vault {args.vault!r}")
    print("Would prompt for the password and create that Proton login item if it does not exist")
    print(f"Would create/import Proton SSH key item: {item_title!r}")
    print(f"Would generate key with: {format_command(keygen_cmd)}")
    print(f"Would install public key on: {destination.user}@{destination.host}:{destination.port}")
    print(f"Would write managed SSH alias: {args.alias}")
