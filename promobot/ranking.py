"""Escolhe as ofertas "mais quentes" do dia."""
from __future__ import annotations

import math
import re
from datetime import date, timedelta

from .models import Deal

PALAVRAS_RUINS = re.compile(r"\b(usado|recondicionado|refil|capinha|película|pelicula|adesivo|kit \d+ un)\b", re.I)


def score(d: Deal) -> float:
    s = d.desconto * 1.0
    s += min(math.log10(1 + d.popularidade), 2.5) * 10
    s += 4 if d.frete_gratis else 0
    # descontos absurdos (>85%) costumam ser preço "de" inflado
    if d.desconto > 85:
        s -= 40
    # economia em reais também importa: R$ 300 off chama mais atenção que R$ 8 off
    s += min((d.preco_original - d.preco) / 50, 10)
    return round(s, 2)


def selecionar(deals: list[Deal], cfg: dict, historico: dict[str, str], hoje: date) -> list[Deal]:
    corte = (hoje - timedelta(days=cfg["repetir_produto_apos_dias"])).isoformat()
    candidatos = []
    for d in deals:
        if d.desconto < cfg["desconto_minimo"]:
            continue
        if not (cfg["preco_minimo"] <= d.preco <= cfg["preco_maximo"]):
            continue
        if not d.imagem or not d.titulo or PALAVRAS_RUINS.search(d.titulo):
            continue
        if historico.get(d.chave, "") >= corte:
            continue
        d.score = score(d)
        candidatos.append(d)
    candidatos.sort(key=lambda d: d.score, reverse=True)

    total = cfg["ofertas_por_dia"]
    quota_amz = min(cfg.get("amazon_quando_disponivel", 2), sum(1 for d in candidatos if d.loja == "Amazon"))
    escolhidos: list[Deal] = []
    por_cat: dict[str, int] = {}

    def tenta(d: Deal) -> bool:
        cat = d.categoria or d.titulo.split()[0].lower()
        if por_cat.get(cat, 0) >= cfg["maximo_por_categoria"] or d in escolhidos:
            return False
        if any(_parecido(d.titulo, e.titulo) for e in escolhidos):
            return False
        por_cat[cat] = por_cat.get(cat, 0) + 1
        escolhidos.append(d)
        return True

    for d in candidatos:
        if sum(1 for e in escolhidos if e.loja == "Amazon") >= quota_amz:
            break
        if d.loja == "Amazon":
            tenta(d)
    for d in candidatos:
        if len(escolhidos) >= total:
            break
        if d.loja != "Amazon" or quota_amz == 0:
            tenta(d)
    for d in candidatos:  # completa se faltou por causa das cotas
        if len(escolhidos) >= total:
            break
        tenta(d)

    # a melhor oferta vai no horário nobre (4º post, ~19h50), a 2ª no almoço
    escolhidos.sort(key=lambda d: d.score, reverse=True)
    ordem = [3, 1, 2, 4, 0] if len(escolhidos) == 5 else list(range(len(escolhidos)))
    final = [None] * len(escolhidos)
    for rank, slot in enumerate(ordem):
        final[slot] = escolhidos[rank]
    return final


def _parecido(a: str, b: str) -> bool:
    wa, wb = set(a.lower().split()[:5]), set(b.lower().split()[:5])
    return len(wa & wb) >= 4
