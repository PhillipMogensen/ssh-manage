#!/usr/bin/env sh
set -eu

REPO_URL="${SSH_MANAGE_REPO_URL:-https://github.com/PhillipMogensen/ssh-manage.git}"
PACKAGE_SPEC="ssh-manage[bootstrap] @ git+${REPO_URL}"

info() {
  printf '%s\n' "$*"
}

have() {
  command -v "$1" >/dev/null 2>&1
}

install_uv() {
  if have uv; then
    return
  fi

  if have brew; then
    info "Installing uv with Homebrew..."
    brew install uv
    return
  fi

  info "Installing uv with the official Astral installer..."
  curl -LsSf https://astral.sh/uv/install.sh | sh

  if [ -d "$HOME/.local/bin" ]; then
    PATH="$HOME/.local/bin:$PATH"
    export PATH
  fi
}

install_ssh_manage() {
  info "Installing ssh-manage..."
  uv tool install "$PACKAGE_SPEC" --force
  uv tool update-shell >/dev/null 2>&1 || true
}

verify_install() {
  if have ssh-manage; then
    ssh-manage --help >/dev/null
    return
  fi

  if [ -x "$HOME/.local/bin/ssh-manage" ]; then
    "$HOME/.local/bin/ssh-manage" --help >/dev/null
    return
  fi

  info "ssh-manage was installed, but it is not on PATH yet."
  info "Open a new shell, or add this to your shell profile:"
  info '  export PATH="$HOME/.local/bin:$PATH"'
}

install_uv
install_ssh_manage
verify_install

info "ssh-manage is installed."
info "Next:"
info "  pass-cli login"
info '  ssh-manage install --vault "SSH Keys"'
