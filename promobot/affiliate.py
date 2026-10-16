"""Transforma o link do produto em link de afiliado."""
from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from .config import env


def _set_params(url: str, params: dict) -> str:
    p = urlparse(url)
    q = dict(parse_qsl(p.query, keep_blank_values=True))
    q.update({k: v for k, v in params.items() if v})
    return urlunparse(p._replace(query=urlencode(q), fragment=""))


def mercado_livre(url: str) -> str:
    """Formato dos links gerados no portal de afiliados do ML.

    Abra afiliados.mercadolivre.com.br > Gerador de link, gere um link qualquer
    e copie os valores de `matt_word` e `matt_tool` para os Secrets
    ML_MATT_WORD e ML_MATT_TOOL. Se o seu link usar só `tag`, preencha ML_TAG.
    """
    clean = url.split("#")[0]
    params = {
        "matt_word": env("ML_MATT_WORD"),
        "matt_tool": env("ML_MATT_TOOL"),
        "tag": env("ML_TAG"),
    }
    if not any(params.values()):
        return clean
    return _set_params(clean, params)


def amazon(url: str) -> str:
    tag = env("AMAZON_TAG")  # ex.: alphapromo-20
    return _set_params(url.split("#")[0], {"tag": tag}) if tag else url


def amazon_ofertas_do_dia() -> str:
    return amazon("https://www.amazon.com.br/deals")


def afiliar(loja: str, url: str) -> str:
    return mercado_livre(url) if loja == "Mercado Livre" else amazon(url)
