"""'Eu quero' nos comentários -> link da oferta no direct da pessoa.

A cada execução (15 em 15 min) o robô olha os comentários dos posts dos últimos
dias. Quem comentou "quero" recebe uma resposta privada (direct) com o link da
oferta e um convite para seguir o perfil, e o comentário ganha uma resposta
pública "te mandei no direct".

Precisa das permissões instagram_business_manage_comments e
instagram_business_manage_messages. Enquanto o app da Meta não passar pela
análise (acesso avançado), só funciona para contas com função no app (testadores).
"""
from __future__ import annotations

import logging
import re
import unicodedata
from datetime import date, timedelta

import requests

from . import site, state
from .config import Settings, env
from .models import brl
from .publish.instagram import HOST, _check

log = logging.getLogger(__name__)
GATILHO = re.compile(r"\bquero\b")
ARQ = "eu-quero.json"


def _norm(t: str) -> str:
    return unicodedata.normalize("NFKD", (t or "").lower()).encode("ascii", "ignore").decode()


def _mensagem(item: dict, curto: str, usuario: str) -> str:
    nome = item["titulo"] if len(item["titulo"]) <= 70 else item["titulo"][:69].rsplit(" ", 1)[0] + "…"
    oi = f"Oi, @{usuario}! 👋" if usuario else "Oi! 👋"
    return (f"{oi} Aqui está o link da oferta que você pediu:\n\n"
            f"🛒 {nome}\n💰 {brl(item['preco'])} no {item['loja']} (preço do dia do post, pode ter mudado)\n"
            f"👉 https://{curto}\n\n"
            "Segue a @alphapromo.ofertas pra receber as próximas ofertas antes de acabar 🧡")


def processar(cfg: Settings, hoje: date, dias: int = 3, dry_run: bool = False) -> int:
    uid, token = env("IG_USER_ID"), env("IG_ACCESS_TOKEN")
    if not (uid and token):
        return 0
    versao = cfg["publicar"]["instagram_api_versao"]
    base = f"{HOST}/{versao}"
    feitos = state._read(state.STATE / ARQ, {})
    enviados = 0
    arq = state.load_arquivo()
    for k in range(dias):
        dia = hoje - timedelta(days=k)
        for item in arq.get(dia.isoformat(), []):
            if not item.get("ig"):
                continue
            try:
                r = requests.get(f"{base}/{item['ig']}/comments", timeout=30, params={
                    "fields": "id,text,username,from", "limit": 50, "access_token": token})
                comentarios = _check(r).get("data", [])
            except Exception as e:  # noqa: BLE001
                log.warning("Eu quero: não consegui ler os comentários do post %s: %s", item["ig"], str(e)[:200])
                continue
            for c in comentarios:
                cid = c.get("id")
                if not cid or cid in feitos or not GATILHO.search(_norm(c.get("text", ""))):
                    continue
                if (c.get("from") or {}).get("id") == uid:
                    continue  # comentário da própria Alpha Promo
                usuario = c.get("username", "")
                curto = f"{cfg.pages_url.removeprefix('https://')}/o/{site.codigo_curto(dia, item['n'])}"
                if dry_run:
                    log.info("[dry-run] mandaria o link de #%s para @%s", item["n"], usuario)
                    continue
                try:
                    _check(requests.post(f"{base}/{uid}/messages", timeout=30, json={
                        "recipient": {"comment_id": cid},
                        "message": {"text": _mensagem(item, curto, usuario)}},
                        params={"access_token": token}))
                    feitos[cid] = f"ok:{hoje.isoformat()}"
                    enviados += 1
                    try:  # resposta pública, ajuda o post a aparecer mais
                        _check(requests.post(f"{base}/{cid}/replies", timeout=30, data={
                            "message": f"@{usuario} te mandei o link no direct! 📩" if usuario else "Te mandei o link no direct! 📩",
                            "access_token": token}))
                    except Exception as e:  # noqa: BLE001
                        log.debug("resposta pública: %s", e)
                    log.getChild("aviso").info("Eu quero: link de %s #%s enviado para @%s", dia.strftime("%d/%m"), item["n"], usuario)
                except Exception as e:  # noqa: BLE001
                    feitos[cid] = f"erro:{str(e)[:200]}"
                    log.warning("Eu quero: não consegui mandar direct para @%s: %s", usuario, str(e)[:200])
    if not dry_run:
        state._write(state.STATE / ARQ, feitos)
    return enviados
