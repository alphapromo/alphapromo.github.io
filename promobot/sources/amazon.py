"""Ofertas da Amazon via Creators API (sucessora da PA-API, desligada em maio/2026).

Só funciona depois que a Amazon libera o acesso: conta de Associado aprovada e
pelo menos 10 vendas qualificadas nos últimos 30 dias. Até lá, este módulo
retorna lista vazia e o robô usa só o Mercado Livre (a página "link na bio"
continua com o botão "Ofertas do dia da Amazon" usando a sua tag).

Secrets: AMAZON_CLIENT_ID, AMAZON_CLIENT_SECRET, AMAZON_TAG.
"""
from __future__ import annotations

import logging

import requests

from ..config import env
from ..models import Deal

log = logging.getLogger(__name__)
TOKEN_URL = "https://api.amazon.com/auth/o2/token"  # credenciais v3.1 (NA) cobrem o Brasil
BASE = "https://creatorsapi.amazon/catalog/v1"
MARKETPLACE = "www.amazon.com.br"
RESOURCES = [
    "images.primary.large",
    "itemInfo.title",
    "offersV2.listings.price",
    "offersV2.listings.availability",
    "offersV2.listings.dealDetails",
    "browseNodeInfo.websiteSalesRank",
]


def _token() -> str | None:
    cid, secret = env("AMAZON_CLIENT_ID"), env("AMAZON_CLIENT_SECRET")
    if not (cid and secret and env("AMAZON_TAG")):
        return None
    r = requests.post(
        TOKEN_URL,
        json={"grant_type": "client_credentials", "client_id": cid, "client_secret": secret, "scope": "creatorsapi::default"},
        timeout=30,
    )
    if r.status_code != 200:
        log.error("Amazon: falha no token (%s): %s", r.status_code, r.text[:300])
        return None
    return r.json()["access_token"]


def _parse(item: dict, categoria: str) -> Deal | None:
    listings = (item.get("offersV2") or {}).get("listings") or []
    if not listings:
        return None
    price = listings[0].get("price") or {}
    atual = (price.get("money") or {}).get("amount")
    base = ((price.get("savingBasis") or {}).get("money") or {}).get("amount")
    if not atual or not base or base <= atual:
        return None
    rank = ((item.get("browseNodeInfo") or {}).get("websiteSalesRank") or {}).get("salesRank") or 0
    img = (((item.get("images") or {}).get("primary") or {}).get("large") or {}).get("url", "")
    return Deal(
        loja="Amazon",
        id=item["asin"],
        titulo=((item.get("itemInfo") or {}).get("title") or {}).get("displayValue", ""),
        preco=float(atual),
        preco_original=float(base),
        imagem=img,
        url=item.get("detailPageURL", f"https://www.amazon.com.br/dp/{item['asin']}"),
        categoria=categoria,
        popularidade=max(0.0, 100 - (rank / 500)) if rank else 20,
        link_afiliado=item.get("detailPageURL", ""),  # já vem com a tag
        extras={"fonte": "creators_api", "deal": listings[0].get("dealDetails")},
    )


def fetch(buscas: list[list[str]], desconto_minimo: int) -> list[Deal]:
    token = _token()
    if not token:
        log.info("Amazon: Creators API ainda não configurada — pulando.")
        return []
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json", "x-marketplace": MARKETPLACE}
    out: list[Deal] = []
    for search_index, keywords in buscas:
        body = {
            "partnerTag": env("AMAZON_TAG"),
            "marketplace": MARKETPLACE,
            "keywords": keywords,
            "searchIndex": search_index,
            "minSavingPercent": desconto_minimo,
            "minReviewsRating": 4,
            "itemCount": 10,
            "resources": RESOURCES,
        }
        try:
            r = requests.post(f"{BASE}/searchItems", json=body, headers=headers, timeout=30)
            r.raise_for_status()
            for it in (r.json().get("searchResult") or {}).get("items", []):
                d = _parse(it, keywords)
                if d:
                    out.append(d)
        except Exception as e:  # noqa: BLE001
            log.warning("Amazon busca '%s' falhou: %s", keywords, e)
    log.info("Amazon: %s ofertas", len(out))
    return out
