# ssh-manage

`ssh-manage` is a command-line tool for turning SSH password logins into Proton Pass-backed SSH key aliases.

The goal is to make this workflow simple:

```bash
ssh-manage install --vault "SSH Keys"
ssh-manage add --name "Proxmox host" --dest root@192.168.0.200 --alias proxmox --vault "SSH Keys"
ssh proxmox
```

If the Proton Pass login item named by `--name` does not exist yet, `ssh-manage` prompts for the current SSH password and creates the login item. It then generates an SSH key, imports the private key into Proton Pass, installs the public key on the remote host, and writes a local OpenSSH alias.

## What It Does

- Installs or verifies Proton Pass CLI on macOS.
- Configures the Proton Pass SSH agent to run through launchd.
- Creates Proton Pass login items for password-based SSH hosts when needed.
- Creates Proton Pass SSH key items for managed SSH aliases.
- Adds the generated public key to the remote host's `~/.ssh/authorized_keys`.
- Writes a managed OpenSSH config include so `ssh <alias>` works normally.
- Rebuilds aliases on another device from Proton Pass metadata with `ssh-manage sync`.

## Requirements

- macOS for the automated install and launchd agent setup.
- Python 3.10 or newer.
- `uv` for global tool installation.
- Proton Pass CLI access for your Proton account.
- Password SSH access to the host for first-time bootstrap.

Linux support is intentionally not first-class yet. The code is structured so a systemd install path can be added later.

## Install as a Global Command

From this repo:

```bash
./scripts/install-global.sh
```

Or directly:

```bash
uv tool install --editable ".[bootstrap]" --force
```

This installs `ssh-manage` into uv's tool bin directory, normally `~/.local/bin`, so it can run from any directory. If your shell cannot find it afterward, run:

```bash
uv tool update-shell
```

Then open a new shell or source your shell profile.

## First-Time Setup

Log in to Proton Pass CLI if you have not already:

```bash
pass-cli login
```

Configure the Proton Pass SSH agent:

```bash
ssh-manage install --vault "SSH Keys"
```

The install command writes a macOS LaunchAgent and adds this environment variable to your shell profile:

```bash
export SSH_AUTH_SOCK="$HOME/.ssh/proton-pass-agent.sock"
```

## Add a Host

```bash
ssh-manage add \
  --name "Proxmox host" \
  --dest root@192.168.0.200 \
  --alias proxmox \
  --vault "SSH Keys"
```

Behavior:

1. If `"Proxmox host"` exists in Proton Pass, its password is used for the bootstrap connection.
2. If it does not exist, you are prompted for the SSH password and a Proton Pass login item is created.
3. A temporary Ed25519 key is generated locally.
4. The private key is imported into Proton Pass as `ssh-manage/<alias>`.
5. The public key is appended to the remote host's `authorized_keys` if it is not already present.
6. Proton custom fields are written to the SSH key item so another device can recreate the alias.
7. Local SSH config is updated so `ssh <alias>` works.

You can preview the planned actions without contacting Proton or the host:

```bash
ssh-manage add --name "Proxmox host" --dest root@192.168.0.200 --alias proxmox --vault "SSH Keys" --dry-run
```

## Sync on Another Device

Managed SSH aliases are portable because the private keys and alias metadata live in Proton Pass, not only on the original machine. On a new Mac, install the CLI, authenticate Proton Pass CLI, start the Proton Pass SSH agent, then rebuild local OpenSSH config from the Proton metadata.

On the new device:

```bash
git clone https://github.com/PhillipMogensen/ssh-manage.git
cd ssh-manage
./scripts/install-global.sh
pass-cli login
ssh-manage install --vault "SSH Keys"
ssh-manage sync --vault "SSH Keys"
ssh proxmox
```

`sync` reads managed Proton SSH key items and recreates:

- `~/.ssh/ssh-manage/config`
- `~/.ssh/ssh-manage/keys/<alias>.pub`
- the `Include ~/.ssh/ssh-manage/config` line in `~/.ssh/config`

The generated public-key files are selector files only. OpenSSH uses them to choose the matching private key from the Proton Pass SSH agent, so private keys are not written to disk on the new device.

If you add or update aliases on one machine, run this on the other machines:

```bash
ssh-manage sync --vault "SSH Keys"
```

## Commands

```bash
ssh-manage install --vault "SSH Keys"
ssh-manage add --name "Login Item" --dest user@host --alias alias --vault "SSH Keys"
ssh-manage sync --vault "SSH Keys"
ssh-manage doctor
```

The root command also acts as `add` when passed `--name`, `--dest`, `--alias`, and `--vault`.

## Managed Files

`ssh-manage` writes:

- `~/.ssh/ssh-manage/config`
- `~/.ssh/ssh-manage/keys/<alias>.pub`
- `~/.ssh/config`, adding one `Include ~/.ssh/ssh-manage/config` line if missing
- `~/Library/LaunchAgents/com.ssh-manage.proton-pass-agent.plist`

It does not store private keys locally after importing them into Proton Pass.

## Proton Pass Metadata

Each managed SSH key item gets custom fields:

- `ssh_manage_alias`
- `ssh_manage_host`
- `ssh_manage_user`
- `ssh_manage_port`
- `ssh_manage_public_key`
- `ssh_manage_password_item`

These fields are what make `ssh-manage sync` work on another device.

## Development

```bash
uv sync --extra dev --extra bootstrap
uv run pytest
uv run ruff check .
```

The package exposes the console script through `pyproject.toml`:

```toml
[project.scripts]
ssh-manage = "ssh_manage.cli:main"
```
