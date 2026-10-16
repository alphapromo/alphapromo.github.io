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


def parse_sale_price(sp: dict | None) -> tuple[float | None, float | None]:
    """/items/{id}/sale_price -> (preço atual, preço "de")."""
    if not sp:
        return None, None
    return sp.get("amount"), sp.get("regular_amount")


def parse_product_items(data: dict | None) -> dict:
    """/products/{id}/items -> o anúncio mais barato, no formato do buy_box_winner."""
    res = [r for r in (data or {}).get("results", []) if r.get("price")]
    return min(res, key=lambda r: r["price"]) if res else {}


def parse_product(p: dict | None, posicao: int, categoria: str, preco_extra: tuple | None = None) -> Deal | None:
    if not p:
        return None
    bb = p.get("buy_box_winner") or {}
    preco = bb.get("price")
    original = bb.get("original_price")
    if preco_extra and preco_extra[0] and preco_extra[1]:
        preco, original = preco_extra
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


def diagnostico(categoria: str = "MLB1000", n: int = 3) -> None:
    """Mostra no log onde estão vídeos/clips nos dados de alguns produtos."""
    import json as _json

    cli = _Client(_token())
    prods = parse_highlights(cli.get(f"/highlights/MLB/category/{categoria}"))[:n]
    for pid, _ in prods:
        p = cli.get(f"/products/{pid}") or {}
        bb = p.get("buy_box_winner") or {}
        iid = bb.get("item_id")
        log.info("PRODUTO %s chaves=%s", pid, sorted(p.keys()))
        for k, v in p.items():
            if re.search(r"video|clip|media|short", k, re.I):
                log.info("  produto.%s = %s", k, _json.dumps(v, ensure_ascii=False)[:400])
        log.info("  buy_box chaves=%s", sorted(bb.keys()))
        for path in (f"/items/{iid}", f"/items/{iid}/clips", f"/items/{iid}/videos", f"/products/{pid}/clips",
                     f"/marketplace/items/{iid}/clips", f"/clips/items/{iid}"):
            if not iid and "items" in path:
                continue
            r = cli.s.get(f"{API}{path}", timeout=30)
            corpo = r.text[:300].replace("\n", " ")
            achou = re.findall(r'"([^"]*(?:video|clip)[^"]*)"\s*:', r.text, re.I)[:10]
            log.info("  GET %s -> %s chaves_video=%s corpo=%s", path, r.status_code, achou, corpo if r.status_code < 400 else "")


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
            p = cli.get(f"/products/{pid}")
            if not p:
                continue
            bb = p.get("buy_box_winner") or {}
            extra = None
            if not (bb.get("price") and bb.get("original_price")):
                if not bb:  # sem buy box: pega o anúncio mais barato do produto
                    bb = parse_product_items(cli.get(f"/products/{pid}/items"))
                    p = {**p, "buy_box_winner": bb}
                if bb.get("item_id") and not bb.get("original_price"):
                    extra = parse_sale_price(cli.get(f"/items/{bb['item_id']}/sale_price", context="channel_marketplace"))
            if len(vistos) == 1:  # diagnóstico (sem dados sensíveis)
                log.info("ML diagnóstico %s: buy_box=%s sale_price=%s", pid,
                         {k: bb.get(k) for k in ("item_id", "price", "original_price")}, extra)
            d = parse_product(p, pos, cat_nome, extra)
            if d:
                deals.append(d)
                achados += 1
        log.info("ML %s (%s): %s mais vendidos, %s com desconto", cat_nome, cat_id, len(produtos), achados)
    log.info("ML: %s ofertas com desconto (%s chamadas à API)", len(deals), cli.chamadas)
    return deals
