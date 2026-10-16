"""Ofertas do Mercado Livre pela API oficial (api.mercadolibre.com).

A página pública de ofertas e a busca /sites/MLB/search passaram a bloquear
acesso automatizado (login obrigatório / 403). O caminho que funciona é:

1. /highlights/MLB/category/{categoria}  -> mais vendidos de cada categoria
2. /products/{id}                       -> nome, fotos, link e o vencedor da
                                           "buy box" (preço atual e preço "de")

Precisa de um app em developers.mercadolivre.com.br.
Secrets: ML_CLIENT_ID e ML_CLIENT_SECRET (obrigatórios);
ML_REFRESH_TOKEN (opcional — se existir, é usado e renovado sozinho).
"""
from __future__ import annotations

import logging
import re
import time

import requests

from ..config import env
from ..models import Deal
from ..secrets_store import save_secret

log = logging.getLogger(__name__)
API = "https://api.mercadolibre.com"
MAX_PRODUTOS_POR_CATEGORIA = 20


class MLAuthError(RuntimeError):
    pass


# ---------------------------------------------------------------- token
def _token() -> str:
    cid, secret, refresh = env("ML_CLIENT_ID"), env("ML_CLIENT_SECRET"), env("ML_REFRESH_TOKEN")
    if not (cid and secret):
        raise MLAuthError("ML_CLIENT_ID / ML_CLIENT_SECRET não configurados")
    if refresh:
        data = {"grant_type": "refresh_token", "client_id": cid, "client_secret": secret, "refresh_token": refresh}
    else:
        data = {"grant_type": "client_credentials", "client_id": cid, "client_secret": secret}
    r = requests.post(f"{API}/oauth/token", data=data, headers={"Accept": "application/json"}, timeout=30)
    if r.status_code != 200:
        raise MLAuthError(f"falha ao obter token ({r.status_code}): {r.text[:300]}")
    body = r.json()
    if refresh and body.get("refresh_token") and body["refresh_token"] != refresh:
        save_secret("ML_REFRESH_TOKEN", body["refresh_token"])
    return body["access_token"]


class _Client:
    def __init__(self, token: str):
        self.s = requests.Session()
        self.s.headers.update({"Authorization": f"Bearer {token}", "Accept": "application/json"})
        self.chamadas = 0

    def get(self, path: str, **params):
        for tentativa in range(3):
            self.chamadas += 1
            r = self.s.get(f"{API}{path}", params=params or None, timeout=30)
            if r.status_code == 429:
                time.sleep(2 + tentativa * 3)
                continue
            if r.status_code >= 400:
                log.debug("ML %s -> %s", path, r.status_code)
                return None
            return r.json()
        return None


# ---------------------------------------------------------------- parsing
def _hi_res(url: str) -> str:
    url = (url or "").replace("http://", "https://")
    return re.sub(r"-[A-Z]\.(jpg|webp|png)$", r"-O.jpg", url)


def parse_highlights(data: dict | None) -> list[tuple[str, int]]:
    """Retorna [(product_id, posição)] só dos itens do tipo PRODUCT."""
    out = []
    for c in (data or {}).get("content", []):
        if c.get("type", "PRODUCT") == "PRODUCT" and c.get("id"):
            out.append((c["id"], int(c.get("position") or len(out) + 1)))
    return out


def parse_product(p: dict | None, posicao: int, categoria: str) -> Deal | None:
    if not p:
        return None
    bb = p.get("buy_box_winner") or {}
    preco = bb.get("price")
    original = bb.get("original_price")
    if not preco or not original or original <= preco:
        return None
    pics = p.get("pictures") or []
    imagem = _hi_res(pics[0].get("url") or pics[0].get("secure_url", "")) if pics else ""
    pid = p.get("id", "")
    link = p.get("permalink") or f"https://www.mercadolivre.com.br/p/{pid}"
    return Deal(
        loja="Mercado Livre",
        id=pid,
        titulo=p.get("name", "").strip(),
        preco=float(preco),
        preco_original=float(original),
        imagem=imagem,
        url=link,
        categoria=categoria,
        frete_gratis=bool((bb.get("shipping") or {}).get("free_shipping")),
        popularidade=max(0, 60 - posicao) * 2,  # posição no ranking de mais vendidos
        extras={"fonte": "api_highlights", "item_id": bb.get("item_id")},
    )


# ---------------------------------------------------------------- coleta
def fetch(categorias: dict[str, str]) -> list[Deal]:
    try:
        cli = _Client(_token())
    except MLAuthError as e:
        log.error("Mercado Livre: %s", e)
        return []
    deals: list[Deal] = []
    vistos: set[str] = set()
    for cat_id, cat_nome in categorias.items():
        produtos = parse_highlights(cli.get(f"/highlights/MLB/category/{cat_id}"))
        achados = 0
        for pid, pos in produtos[:MAX_PRODUTOS_POR_CATEGORIA]:
            if pid in vistos:
                continue
            vistos.add(pid)
            d = parse_product(cli.get(f"/products/{pid}"), pos, cat_nome)
            if d:
                deals.append(d)
                achados += 1
        log.info("ML %s (%s): %s mais vendidos, %s com desconto", cat_nome, cat_id, len(produtos), achados)
    log.info("ML: %s ofertas com desconto (%s chamadas à API)", len(deals), cli.chamadas)
    return deals
