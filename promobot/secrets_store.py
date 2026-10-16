"""Guarda tokens renovados de volta nos Secrets do GitHub (para não expirarem nunca).

Precisa do Secret GH_PAT: um token do GitHub com permissão "Secrets: read and write"
neste repositório. Sem ele, o robô continua funcionando, mas tokens que giram
(Mercado Livre, TikTok) e o token do Instagram (60 dias) vão expirar.
"""
from __future__ import annotations

import logging
import os
import subprocess

from .config import env

log = logging.getLogger(__name__)


def save_secret(name: str, value: str) -> bool:
    os.environ[name] = value  # vale para o restante desta execução
    pat, repo = env("GH_PAT"), env("GITHUB_REPOSITORY")
    if not (pat and repo):
        log.warning("Sem GH_PAT: o novo valor de %s não foi salvo para as próximas execuções.", name)
        return False
    r = subprocess.run(
        ["gh", "secret", "set", name, "--repo", repo, "--body", value],
        env={**os.environ, "GH_TOKEN": pat},
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        log.error("Falha ao salvar o Secret %s: %s", name, r.stderr.strip())
        return False
    log.info("Secret %s atualizado.", name)
    return True
