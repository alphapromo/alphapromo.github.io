"""Escolhe as ofertas "mais quentes" do dia."""
from __future__ import annotations

import math
import re
from datetime import date, timedelta

from .models import Deal

PALAVRAS_RUINS = re.compile(r"\b(usado|recondicionado|refil|capinha|película|pelicula|adesivo|kit \d+ un)\b", re.I)


def posicao(d: Deal) -> int:
    """Posição no ranking de mais vendidos do dia (1 = o mais vendido da categoria)."""
    if d.extras.get("posicao"):
        return int(d.extras["posicao"])
    return max(1, 60 - int(d.popularidade / 2)) if d.popularidade else 50


def score(d: Deal) -> float:
    """Mais vendido manda; desconto é bônus.

    1º lugar = 100 pontos, 10º = 55. Cada 1% de desconto vale 0,4 (60% OFF = +24).
    """
    s = max(0, 21 - posicao(d)) * 5.0
    s += min(d.desconto, 60) * 0.4
    s += 3 if d.frete_gratis else 0
    s += min((d.preco_original - d.preco) / 50, 5)
    return round(s, 2)


def _norm(t: str) -> str:
    import unicodedata
    return unicodedata.normalize("NFKD", (t or "").lower()).encode("ascii", "ignore").decode()


def marca_ok(d: Deal, cfg: dict) -> bool:
    """Categorias com lista de marcas (ex.: Games só Nintendo, Sony, Microsoft e 8BitDo)."""
    permitidas = (cfg.get("marcas_permitidas") or {}).get(d.extras.get("cat_raiz") or "")
    if not permitidas:
        return True
    permitidas = [_norm(m) for m in permitidas]
    marca = _norm(d.extras.get("marca", ""))
    if marca:
        return any(m == marca or m in marca.split() for m in permitidas)
    titulo = _norm(d.titulo)  # sem marca cadastrada: só aceita se o título cita a marca e não é "compatível"
    return any(m in titulo for m in permitidas) and not re.search(r"compativel|para (ps|xbox|switch|nintendo)", titulo)


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


# ---------------------------------------------------------------- temas por horário
def _no_tema(d: Deal, tema: dict, relaxado: bool) -> bool:
    pmin = tema.get("preco_minimo", 0)
    pmax = tema.get("preco_maximo", 10**9) * (1.5 if relaxado else 1)
    if not (pmin <= d.preco <= pmax):
        return False
    titulo = d.titulo.lower()
    if any(p in titulo for p in tema.get("excluir_palavras", [])):
        return False
    cats = tema.get("categorias")
    if cats and d.extras.get("cat_raiz") not in cats:
        return False
    return True


def _bonus_palavras(d: Deal, tema: dict) -> float:
    titulo = d.titulo.lower()
    return 15.0 if any(p in titulo for p in tema.get("palavras", [])) else 0.0


def selecionar_por_tema(deals: list[Deal], cfg: dict, historico: dict[str, str], hoje: date,
                        excluir: set[str] | None = None, ja_usados: list[Deal] | None = None) -> list[Deal | None]:
    """Uma oferta por horário: horários com tema primeiro, depois a melhor do dia nos demais.

    A melhor oferta restante vai para o 4º horário (19:50, nobre); a seguinte para o 5º.
    """
    corte = (hoje - timedelta(days=cfg["repetir_produto_apos_dias"])).isoformat()
    excluir = excluir or set()
    base = []
    for d in deals:
        if d.chave in excluir or d.desconto < cfg["desconto_minimo"] or d.desconto > cfg.get("desconto_maximo", 70):
            continue
        if not d.imagem or not d.titulo or PALAVRAS_RUINS.search(d.titulo):
            continue
        if not marca_ok(d, cfg):
            continue
        if historico.get(d.chave, "") >= corte:
            continue
        d.score = score(d)
        base.append(d)

    total = cfg["ofertas_por_dia"]
    temas = {int(k): v for k, v in (cfg.get("temas") or {}).items()}
    final: list[Deal | None] = [None] * total
    usados: list[Deal] = list(ja_usados or [])

    def livre(d: Deal) -> bool:
        marca = _norm(d.extras.get("marca", ""))
        if marca and any(_norm(u.extras.get("marca", "")) == marca for u in usados):
            return False  # no máximo 1 produto por marca no dia
        return d not in usados and not any(_parecido(d.titulo, u.titulo) for u in usados)

    for slot in sorted(temas):
        if slot > total:
            continue
        tema = temas[slot]
        escolhido = None
        # 1º: no tema e com palavra-chave no título; 2º: no tema; 3º: faixa de preço mais folgada
        for relaxado, exige_palavra in ((False, bool(tema.get("palavras"))), (False, False), (True, False)):
            opcoes = [d for d in base if livre(d) and _no_tema(d, tema, relaxado)
                      and (not exige_palavra or _bonus_palavras(d, tema) > 0)]
            if opcoes:
                escolhido = max(opcoes, key=lambda d: d.score + _bonus_palavras(d, tema))
                break
        if escolhido:
            escolhido.extras["tema"] = tema.get("nome", "")
            final[slot - 1] = escolhido
            usados.append(escolhido)

    # horários livres: só os mais vendidos das categorias principais (top N), nada de subcategoria
    top = cfg.get("top_mais_vendidos", 10)
    geral = [d for d in base if cfg["preco_minimo"] <= d.preco <= cfg["preco_maximo"]
             and not d.extras.get("subcategoria") and posicao(d) <= top]
    geral.sort(key=lambda d: d.score, reverse=True)
    sem_tema = [i for i in range(total) if final[i] is None]
    sem_tema.sort(key=lambda i: (i != 3, i != 4, i))  # 4º horário primeiro, depois o 5º
    def cat_cheia(d: Deal) -> bool:
        raiz = d.extras.get("cat_raiz") or d.categoria
        if any(u.categoria == d.categoria for u in usados):  # nada de dois smartwatches no mesmo dia
            return True
        return sum(1 for u in usados if (u.extras.get("cat_raiz") or u.categoria) == raiz) >= cfg["maximo_por_categoria"]

    for i in sem_tema:
        for d in geral:
            if livre(d) and not cat_cheia(d):
                final[i] = d
                usados.append(d)
                break
    return final
