from __future__ import annotations

import os
import platform
import plistlib
import shutil
import subprocess
from pathlib import Path

from ssh_manage.pass_cli import PassCli
from ssh_manage.ssh_config import AGENT_SOCKET
from ssh_manage.util import UserFacingError, ensure_private_dir


LAUNCH_AGENT_LABEL = "com.ssh-manage.proton-pass-agent"
LAUNCH_AGENT_PATH = Path.home() / "Library" / "LaunchAgents" / f"{LAUNCH_AGENT_LABEL}.plist"
SHELL_BLOCK_START = "# >>> ssh-manage >>>"
SHELL_BLOCK_END = "# <<< ssh-manage <<<"


def install_pass_cli_if_needed(pass_cli: PassCli) -> None:
    if pass_cli.exists():
        return
    if platform.system() != "Darwin":
        raise UserFacingError("Automatic pass-cli installation is only implemented for macOS in v1")
    brew = shutil.which("brew")
    if not brew:
        raise UserFacingError(
            "Homebrew is not installed. Install pass-cli from "
            "https://protonpass.github.io/pass-cli/get-started/installation/ and rerun this command."
        )
    subprocess.run([brew, "install", "protonpass/tap/pass-cli"], check=True)


def configure_agent(pass_cli: PassCli, *, vault: str) -> None:
    if platform.system() != "Darwin":
        raise UserFacingError("Automatic agent setup is only implemented for macOS in v1")
    pass_cli_path = shutil.which(pass_cli.binary)
    if not pass_cli_path:
        raise UserFacingError("pass-cli is not on PATH after installation")

    ensure_private_dir(AGENT_SOCKET.parent)
    LAUNCH_AGENT_PATH.parent.mkdir(parents=True, exist_ok=True)
    plist = {
        "Label": LAUNCH_AGENT_LABEL,
        "ProgramArguments": [
            pass_cli_path,
            "ssh-agent",
            "start",
            "--vault-name",
            vault,
            "--socket-path",
            str(AGENT_SOCKET),
        ],
        "RunAtLoad": True,
        "KeepAlive": True,
        "StandardOutPath": str(Path.home() / ".ssh" / "proton-pass-agent.log"),
        "StandardErrorPath": str(Path.home() / ".ssh" / "proton-pass-agent.err.log"),
    }
    with LAUNCH_AGENT_PATH.open("wb") as handle:
        plistlib.dump(plist, handle)

    subprocess.run(["launchctl", "unload", str(LAUNCH_AGENT_PATH)], check=False)
    subprocess.run(["launchctl", "load", str(LAUNCH_AGENT_PATH)], check=True)


def configure_shell_profile() -> Path:
    profile = _shell_profile()
    profile.parent.mkdir(parents=True, exist_ok=True)
    existing = profile.read_text(encoding="utf-8") if profile.exists() else ""
    block = (
        f"{SHELL_BLOCK_START}\n"
        'export SSH_AUTH_SOCK="$HOME/.ssh/proton-pass-agent.sock"\n'
        f"{SHELL_BLOCK_END}\n"
    )
    if SHELL_BLOCK_START in existing and SHELL_BLOCK_END in existing:
        before, rest = existing.split(SHELL_BLOCK_START, 1)
        _, after = rest.split(SHELL_BLOCK_END, 1)
        profile.write_text(before.rstrip() + "\n" + block + after.lstrip(), encoding="utf-8")
    else:
        profile.write_text(existing.rstrip() + "\n\n" + block if existing else block, encoding="utf-8")
    return profile


def _shell_profile() -> Path:
    shell = Path(os.environ.get("SHELL", "")).name
    if shell == "zsh":
        return Path.home() / ".zshrc"
    if shell == "bash":
        return Path.home() / ".bashrc"
    return Path.home() / ".profile"
