"""Ofertas do Mercado Livre.

Duas fontes, combinadas:
1. Página pública "Ofertas do dia" (mercadolivre.com.br/ofertas) — não precisa de cadastro.
2. API oficial (api.mercadolibre.com), se ML_CLIENT_ID / ML_CLIENT_SECRET / ML_REFRESH_TOKEN
   estiverem nos Secrets. Mais estável que a página; o refresh token gira a cada uso
   e é salvo de volta automaticamente.
"""
from __future__ import annotations

import logging
import re

import requests
from bs4 import BeautifulSoup

from ..config import env
from ..models import Deal
from ..secrets_store import save_secret

log = logging.getLogger(__name__)
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
)
API = "https://api.mercadolibre.com"


# ---------------------------------------------------------------- página pública
def _money(el) -> float | None:
    if el is None:
        return None
    frac = el.select_one(".andes-money-amount__fraction")
    if frac is None:
        return None
    cents = el.select_one(".andes-money-amount__cents")
    inteiro = re.sub(r"\D", "", frac.get_text())
    if not inteiro:
        return None
    return float(inteiro) + (float(cents.get_text()) / 100 if cents and cents.get_text().strip().isdigit() else 0)


def _item_id(url: str) -> str:
    m = re.search(r"(MLB-?\d{6,})", url)
    return m.group(1).replace("-", "") if m else url.split("?")[0][-40:]


def parse_ofertas_html(html: str) -> list[Deal]:
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select(".poly-card, .promotion-item") or soup.select("li.ui-search-layout__item")
    deals: list[Deal] = []
    vistos: set[str] = set()
    for pos, card in enumerate(cards):
        link = card.select_one("a.poly-component__title, a.promotion-item__link-container, a[href*='mercadolivre.com.br']")
        title_el = card.select_one(".poly-component__title, .promotion-item__title, h2, h3")
        if not link or not title_el:
            continue
        url = link.get("href", "").split("#")[0]
        if not url or _item_id(url) in vistos:
            continue
        vistos.add(_item_id(url))
        prev = _money(card.select_one(".andes-money-amount--previous, s.andes-money-amount"))
        cur = None
        for el in card.select(".poly-price__current .andes-money-amount, .andes-money-amount"):
            classes = " ".join(el.get("class", []))
            if "previous" in classes or el.name == "s":
                continue
            cur = _money(el)
            if cur:
                break
        if not cur or not url:
            continue
        if not prev:
            m = re.search(r"(\d{1,2})\s*%\s*OFF", card.get_text(" "), re.I)
            prev = round(cur / (1 - int(m.group(1)) / 100), 2) if m else cur
        img = card.select_one("img")
        img_url = ""
        if img:
            img_url = img.get("data-src") or img.get("src") or ""
            if img_url.startswith("data:"):
                img_url = img.get("data-src", "")
        deals.append(
            Deal(
                loja="Mercado Livre",
                id=_item_id(url),
                titulo=title_el.get_text(" ", strip=True),
                preco=cur,
                preco_original=prev,
                imagem=_hi_res(img_url),
                url=url,
                frete_gratis="grátis" in card.get_text(" ").lower(),
                popularidade=max(0, 100 - pos),  # ordem da página = relevância do ML
                extras={"fonte": "pagina_ofertas"},
            )
        )
    return deals


def _hi_res(url: str) -> str:
    # miniaturas do ML: ...-I.jpg / -V.webp -> -O.jpg (original)
    return re.sub(r"-[A-Z]\.(jpg|webp|png)$", r"-O.jpg", url) if url else url


def from_ofertas_page(paginas: int = 3) -> list[Deal]:
    out: list[Deal] = []
    for page in range(1, paginas + 1):
        try:
            r = requests.get(
                "https://www.mercadolivre.com.br/ofertas",
                params={"page": page},
                headers={"User-Agent": UA, "Accept-Language": "pt-BR,pt;q=0.9"},
                timeout=30,
            )
            r.raise_for_status()
            found = parse_ofertas_html(r.text)
            log.info("ML página %s: %s ofertas", page, len(found))
            out += found
        except Exception as e:  # noqa: BLE001
            log.warning("ML página de ofertas falhou (página %s): %s", page, e)
    return out


# ---------------------------------------------------------------- API oficial
def _token() -> str | None:
    cid, secret, refresh = env("ML_CLIENT_ID"), env("ML_CLIENT_SECRET"), env("ML_REFRESH_TOKEN")
    if not (cid and secret and refresh):
        return None
    r = requests.post(
        f"{API}/oauth/token",
        data={"grant_type": "refresh_token", "client_id": cid, "client_secret": secret, "refresh_token": refresh},
        headers={"Accept": "application/json"},
        timeout=30,
    )
    if r.status_code != 200:
        log.error("ML: falha ao renovar token (%s): %s", r.status_code, r.text[:300])
        return None
    data = r.json()
    if data.get("refresh_token") and data["refresh_token"] != refresh:
        save_secret("ML_REFRESH_TOKEN", data["refresh_token"])
    return data["access_token"]


def from_api(categorias: dict[str, str]) -> list[Deal]:
    token = _token()
    if not token:
        return []
    out: list[Deal] = []
    for cat_id, cat_nome in categorias.items():
        try:
            r = requests.get(
                f"{API}/sites/MLB/search",
                params={"category": cat_id, "limit": 50},
                headers={"Authorization": f"Bearer {token}"},
                timeout=30,
            )
            r.raise_for_status()
            for pos, it in enumerate(r.json().get("results", [])):
                orig = it.get("original_price") or 0
                if not orig or orig <= it.get("price", 0):
                    continue
                out.append(
                    Deal(
                        loja="Mercado Livre",
                        id=it["id"],
                        titulo=it["title"],
                        preco=float(it["price"]),
                        preco_original=float(orig),
                        imagem=_hi_res((it.get("thumbnail") or "").replace("http://", "https://")),
                        url=it["permalink"],
                        categoria=cat_nome,
                        frete_gratis=bool((it.get("shipping") or {}).get("free_shipping")),
                        popularidade=max(0, 50 - pos) * 2,
                        extras={"fonte": "api"},
                    )
                )
        except Exception as e:  # noqa: BLE001
            log.warning("ML API categoria %s falhou: %s", cat_id, e)
    log.info("ML API: %s ofertas com desconto", len(out))
    return out


def fetch(categorias: dict[str, str]) -> list[Deal]:
    deals = from_api(categorias) + from_ofertas_page()
    seen, uniq = set(), []
    for d in deals:
        if d.id not in seen:
            seen.add(d.id)
            uniq.append(d)
    return uniq
