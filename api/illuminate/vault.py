"""Credential vault (D7). Keys are encrypted at rest per user and decrypted only
inside the connector/model process. Nothing here is ever placed in a prompt."""
from __future__ import annotations

import json
from pathlib import Path

from cryptography.fernet import Fernet

from .config import settings


class Vault:
    def __init__(self, data_dir: Path | None = None) -> None:
        self.dir = data_dir or settings.data_dir
        self.key_path = self.dir / "vault.key"
        self.store_path = self.dir / "vault.json"
        if not self.key_path.exists():
            self.key_path.write_bytes(Fernet.generate_key())
            try:
                self.key_path.chmod(0o600)
            except Exception:
                pass
        self._f = Fernet(self.key_path.read_bytes())

    def _load(self) -> dict:
        if self.store_path.exists():
            try:
                return json.loads(self.store_path.read_text())
            except Exception:
                return {}
        return {}

    def _save(self, d: dict) -> None:
        self.store_path.write_text(json.dumps(d, indent=2))
        try:
            self.store_path.chmod(0o600)
        except Exception:
            pass

    def set(self, user: str, name: str, value: str) -> None:
        d = self._load()
        d.setdefault(user, {})[name] = self._f.encrypt(value.encode()).decode()
        self._save(d)

    def get(self, user: str, name: str) -> str | None:
        tok = self._load().get(user, {}).get(name)
        if not tok:
            return None
        try:
            return self._f.decrypt(tok.encode()).decode()
        except Exception:
            return None

    def delete(self, user: str, name: str) -> None:
        d = self._load()
        d.get(user, {}).pop(name, None)
        self._save(d)

    def masked(self, user: str) -> dict[str, str]:
        """Only the last three characters ever leave the process."""
        out = {}
        for name in self._load().get(user, {}):
            v = self.get(user, name) or ""
            out[name] = ("····" + v[-3:]) if len(v) >= 6 else "····"
        return out


_vault: Vault | None = None


def vault() -> Vault:
    global _vault
    if _vault is None:
        _vault = Vault()
    return _vault
