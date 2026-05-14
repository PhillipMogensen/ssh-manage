from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from ssh_manage.util import UserFacingError


@dataclass(frozen=True)
class GeneratedKey:
    private_key: Path
    public_key: Path
    public_key_text: str


def generate_ed25519_key(path: Path, *, comment: str) -> GeneratedKey:
    result = subprocess.run(
        ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", comment, "-f", str(path)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise UserFacingError((result.stderr or "").strip() or "ssh-keygen failed")
    public_key = path.with_suffix(path.suffix + ".pub")
    return GeneratedKey(
        private_key=path,
        public_key=public_key,
        public_key_text=public_key.read_text(encoding="utf-8").strip(),
    )
