"""Legendas para Instagram e TikTok."""
from __future__ import annotations

from .models import Deal, brl

TAG_LOJA = {"Mercado Livre": "#mercadolivre", "Amazon": "#amazonbrasil"}


def _curto(titulo: str, n: int) -> str:
    return titulo if len(titulo) <= n else titulo[: n - 1].rsplit(" ", 1)[0] + "…"


def legenda_lancamento(d: Deal, marca: dict) -> str:
    preco = f"{brl(d.preco)} no {d.loja}"
    if d.extras.get("pix"):
        preco = f"{brl(d.preco)} no Pix ou {brl(d.preco_original)} parcelado, no {d.loja}"
    elif d.desconto >= 5:
        preco = f"De {brl(d.preco_original)} por {brl(d.preco)} ({d.desconto}% OFF) no {d.loja}"
    linhas = [f"🎮 {d.extras.get('tema') or 'Lançamento'}: {_curto(d.titulo, 100)}", "", preco + "."]
    if d.extras.get("lancamento"):
        linhas.append(f"Lançamento: {d.extras['lancamento']}.")
    if d.extras.get("obs"):
        linhas.append(d.extras["obs"])
    linhas += ["", "👉 Link na bio, seção \"Lançamentos e pré-vendas\".", "",
               "Preço conferido agora; preço e estoque podem mudar a qualquer momento.",
               "Contém link de afiliado: posso ganhar comissão, sem custo extra para você.", "",
               " ".join(marca["hashtags_fixas"] + ["#prevenda", "#lancamento", "#games", TAG_LOJA.get(d.loja, "")]).strip()]
    return "\n".join(linhas)


def legenda(d: Deal, numero: int, marca: dict, plataforma: str) -> str:
    if d.extras.get("avulso"):
        return legenda_lancamento(d, marca)
    onde = "Toque no link da bio" if plataforma == "instagram" else "Link na bio"
    linhas = [
        f"🔥 {d.extras.get('tema') or 'Oferta'} · #{numero} do dia: {_curto(d.titulo, 100)}",
        "",
        f"De {brl(d.preco_original)} por {brl(d.preco)} ({d.desconto}% OFF) na {d.loja}.",
    ]
    if d.frete_gratis:
        linhas.append("Frete grátis.")
    linhas += [
        "",
        f"👉 {onde} e escolha a oferta #{numero}.",
        "",
        "Preço conferido hoje cedo; preço e estoque podem mudar a qualquer momento.",
        "Contém link de afiliado: posso ganhar comissão, sem custo extra para você.",
        "",
        " ".join(marca["hashtags_fixas"] + [TAG_LOJA.get(d.loja, "")]).strip(),
    ]
    return "\n".join(linhas)


def titulo_tiktok(d: Deal, numero: int) -> str:
    return _curto(f"{d.desconto}% OFF: {d.titulo}", 88)
