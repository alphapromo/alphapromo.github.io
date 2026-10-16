"""Configuração: config.yaml + variáveis de ambiente (Secrets do GitHub)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
BRT = timezone(timedelta(hours=-3))  # Brasil não tem horário de verão desde 2019


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


@dataclass
class Settings:
    raw: dict

    @classmethod
    def load(cls, path: Path | None = None) -> "Settings":
        with open(path or ROOT / "config.yaml", encoding="utf-8") as f:
            return cls(yaml.safe_load(f))

    def __getitem__(self, key):
        return self.raw[key]

    # ---- endereços públicos (GitHub Pages / raw) ----
    @property
    def repo(self) -> str:
        return env("GITHUB_REPOSITORY", "SEU_USUARIO/alpha-promo")

    @property
    def pages_url(self) -> str:
        custom = env("SITE_URL")
        if custom:
            return custom.rstrip("/")
        owner, name = self.repo.split("/", 1)
        if name.lower() == f"{owner.lower()}.github.io":  # site da organização: sem /repo no final
            return f"https://{owner.lower()}.github.io"
        return f"https://{owner.lower()}.github.io/{name}"

    def raw_url(self, rel_path: str) -> str:
        branch = env("GITHUB_REF_NAME", "main") or "main"
        return f"https://raw.githubusercontent.com/{self.repo}/{branch}/{rel_path}"


def now_brt() -> datetime:
    fake = env("PROMOBOT_NOW")  # para testes: 2026-10-16T11:50
    if fake:
        return datetime.fromisoformat(fake).replace(tzinfo=BRT)
    return datetime.now(BRT)
