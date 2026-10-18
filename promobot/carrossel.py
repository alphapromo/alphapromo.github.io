"""Carrossel semanal "Top 5 da semana" (domingo).

1. preparar(): junta as ofertas publicadas nos últimos 7 dias, confere o preço de
   hoje no Mercado Livre, fica com as 5 mais vendidas que ainda estão com desconto,
   desenha a capa e as 5 cartas e salva em docs/posts/<data>/semana-*.jpg.
2. publicar(): na execução seguinte (as imagens já estão no GitHub), posta o carrossel.
"""
from __future__ import annotations

import html
import logging
from datetime import date, timedelta

from . import carta, render, state
from .config import ROOT, Settings
from .models import Deal, brl
from .ranking import marca_ok, posicao, score

log = logging.getLogger(__name__)


def arquivo(dia: date):
    return state.STATE / f"carrossel-{dia.isoformat()}.json"


def carregar(dia: date) -> dict | None:
    return state._read(arquivo(dia), None)


def mais_recente(hoje: date, dias: int = 7) -> dict | None:
    for k in range(dias):
        c = carregar(hoje - timedelta(days=k))
        if c:
            return c
    return None


def _publicadas(hoje: date) -> list[Deal]:
    vistos, out = set(), []
    for k in range(7):
        p = state.load_plan(hoje - timedelta(days=k))
        if not p:
            continue
        for n, raw in enumerate(p["deals"], start=1):
            feito = p.get("posts", {}).get(str(n), {})
            if not any(str(v).startswith("ok:") for v in feito.values()):
                continue
            d = Deal.from_dict(raw)
            if d.chave not in vistos and d.loja == "Mercado Livre":
                vistos.add(d.chave)
                out.append(d)
    return out


def _capa(deals: list[Deal], hoje: date) -> str:
    ini = (hoje - timedelta(days=6)).strftime("%d/%m")
    fim = hoje.strftime("%d/%m")
    miniaturas = "".join(
        f'<div style="display:flex;flex-direction:column;align-items:center;gap:12px">'
        f'<div style="width:168px;height:168px;border-radius:26px;background:#fff;box-shadow:0 10px 24px rgba(80,60,40,.10);'
        f'display:flex;align-items:center;justify-content:center;overflow:hidden">'
        f'<img src="{carta._data_uri(img)}" style="max-width:84%;max-height:84%;object-fit:contain"></div>'
        f'<span style="font-family:Outfit;font-size:28px;font-weight:800;color:#C8644D">#{i}</span></div>'
        for i, (d, img) in enumerate(deals, start=1))
    return (f"<!doctype html><html><head><meta charset='utf-8'><style>{carta._fontes()}body{{margin:0}}</style></head><body>"
            f'<div id="arte" style="width:1080px;height:1350px;position:relative;background:#FBF7F2;font-family:\'DM Sans\';color:#24283B;overflow:hidden">'
            f'<div style="position:absolute;left:84px;right:84px;top:120px;display:flex;flex-direction:column;gap:22px">'
            f'<span style="font-size:24px;font-weight:700;letter-spacing:6px;color:#C8644D">ALPHA CARDS · {ini} A {fim}</span>'
            f'<span style="font-family:Outfit;font-size:150px;font-weight:900;letter-spacing:-5px;line-height:.95">Top 5<br>da semana</span>'
            f'<span style="font-size:38px;line-height:1.35;color:#6B6F7E;max-width:820px">Os mais vendidos que <b style="color:#24283B">continuam com desconto hoje</b>. Preços conferidos agora.</span>'
            f'</div>'
            f'<div style="position:absolute;left:84px;right:84px;top:820px;display:flex;justify-content:space-between">{miniaturas}</div>'
            f'<div style="position:absolute;left:84px;right:84px;bottom:90px;display:flex;justify-content:space-between;align-items:center">'
            f'<span style="font-family:Outfit;font-size:40px;font-weight:800">arraste para o lado →</span>'
            f'<span style="font-family:Outfit;font-size:40px;font-weight:800">alpha <span style="color:#C8644D">promo</span></span>'
            f'</div></div></body></html>')


def legenda(deals: list[Deal], marca: dict) -> str:
    linhas = ["🏆 Top 5 da semana: os mais vendidos que continuam com desconto", ""]
    for i, d in enumerate(deals, start=1):
        nome = d.titulo if len(d.titulo) <= 60 else d.titulo[:59].rsplit(" ", 1)[0] + "…"
        linhas.append(f"#{i} {nome}: {brl(d.preco)} ({d.desconto}% OFF)")
    linhas += ["", "👉 Links na bio, seção \"Top 5 da semana\".", "",
               "Preços conferidos hoje; podem mudar a qualquer momento.",
               "Contém links de afiliado: posso ganhar comissão, sem custo extra para você.", "",
               " ".join(marca["hashtags_fixas"] + ["#mercadolivre", "#maisvendidos"])]
    return "\n".join(linhas)


def preparar(cfg: Settings, hoje: date) -> dict | None:
    from .sources import mercadolivre

    c = cfg["curadoria"]
    cand = [d for d in _publicadas(hoje) if marca_ok(d, c) and d.desconto <= c.get("desconto_maximo", 70)]
    cand.sort(key=lambda d: (posicao(d), -score(d)))
    atuais = [d for d in mercadolivre.atualizar(cand[:12])
              if c["desconto_minimo"] <= d.desconto <= c.get("desconto_maximo", 70)]
    atuais.sort(key=lambda d: (posicao(d), -score(d)))
    escolhidas = []
    for d in atuais:
        img = render.baixar_imagem(d.imagem)
        if img is not None:
            escolhidas.append((d, img))
        if len(escolhidas) == 5:
            break
    if len(escolhidas) < 3:
        log.warning("Carrossel da semana: só %s ofertas ainda com desconto — não vai sair.", len(escolhidas))
        dados = {"data": hoje.isoformat(), "deals": [], "slides": [], "post": "pulado:poucas ofertas"}
        state._write(arquivo(hoje), dados)
        return dados
    pasta = f"docs/posts/{hoje.isoformat()}"
    slides = [f"{pasta}/semana-0.jpg"]
    with carta.Fotografo() as f:
        render.salvar_jpeg(f.foto(_capa(escolhidas, hoje)), ROOT / slides[0])
        for i, (d, img) in enumerate(escolhidas, start=1):
            rel = f"{pasta}/semana-{i}.jpg"
            render.salvar_jpeg(carta.render(d, i, 5, "feed", d.extras.get("num_colecao") or i, hoje, img, f), ROOT / rel)
            slides.append(rel)
    dados = {"data": hoje.isoformat(), "deals": [d.to_dict() for d, _ in escolhidas], "slides": slides, "post": ""}
    state._write(arquivo(hoje), dados)
    log.info("Carrossel da semana preparado: %s", ", ".join(html.unescape(d.titulo[:30]) for d, _ in escolhidas))
    return dados


def publicar(cfg: Settings, hoje: date, dry_run: bool = False) -> bool:
    from .publish import instagram

    dados = carregar(hoje)
    if not dados or not dados.get("slides") or str(dados.get("post", "")).startswith(("ok:", "pulado")):
        return True
    deals = [Deal.from_dict(r) for r in dados["deals"]]
    texto = legenda(deals, cfg["marca"])
    versao = cfg["publicar"]["instagram_api_versao"]
    if dry_run:
        log.info("[dry-run] publicaria o carrossel da semana (%s slides)", len(dados["slides"]))
        return True
    ja = instagram.ja_publicado(texto.split("\n", 1)[0], versao)
    try:
        rid = ja or instagram.post_carousel([cfg.raw_url(s) for s in dados["slides"]], texto, versao)
        dados["post"] = f"ok:{rid}"
        log.info("Carrossel da semana publicado → %s", rid)
        ok = True
    except Exception as e:  # noqa: BLE001
        dados["post"] = f"erro:{str(e)[:300]}"
        log.error("Carrossel da semana falhou: %s", e)
        ok = False
    state._write(arquivo(hoje), dados)
    return ok
