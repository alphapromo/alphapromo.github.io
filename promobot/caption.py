"""Legendas para Instagram e TikTok."""
from __future__ import annotations

from .models import Deal, brl

TAG_LOJA = {"Mercado Livre": "#mercadolivre", "Amazon": "#amazonbrasil"}


def _curto(titulo: str, n: int) -> str:
    return titulo if len(titulo) <= n else titulo[: n - 1].rsplit(" ", 1)[0] + "…"


def legenda(d: Deal, numero: int, marca: dict, plataforma: str) -> str:
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
