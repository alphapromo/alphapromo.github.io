"""Página "link na bio" (GitHub Pages, pasta docs/)."""
from __future__ import annotations

import shutil
from datetime import date, timedelta

from jinja2 import Template

from . import state
from .affiliate import amazon_ofertas_do_dia
from .config import ROOT
from .models import Deal, brl

DOCS = ROOT / "docs"

TEMPLATE = Template(
    """<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Alpha Promo · ofertas do dia</title>
<meta name="description" content="As 5 ofertas mais quentes do dia no Mercado Livre e na Amazon.">
<link rel="icon" href="brand/simbolo.png">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Outfit:wght@700;800&family=DM+Sans:wght@400;500;700&display=swap">
<style>
:root{--creme:#FBF7F2;--coral:#E07A62;--coral-txt:#B85A44;--areia:#F3DFCC;--salvia:#5E8C81;--tinta:#24283B;--cinza:#5B6072;--card:#fff;--linha:#EAE1D6}
@media (prefers-color-scheme:dark){:root{--creme:#1C1E29;--card:#262938;--tinta:#F4EEE7;--cinza:#B5B8C4;--areia:#3A3330;--linha:#343748;--coral-txt:#F0A08B}}
*{box-sizing:border-box}
body{margin:0;background:var(--creme);color:var(--tinta);font-family:'DM Sans',system-ui,sans-serif}
main{max-width:560px;margin:0 auto;padding:28px 16px 48px}
header{display:flex;flex-direction:column;align-items:center;gap:10px;text-align:center;margin-bottom:24px}
header img{width:84px;height:84px;border-radius:50%}
h1{font-family:Outfit,sans-serif;font-weight:800;font-size:30px;margin:0;letter-spacing:-.5px}
h1 span{color:var(--coral-txt)}
header p{margin:0;color:var(--cinza)}
h2{font-family:Outfit,sans-serif;font-size:20px;margin:28px 0 12px}
.deal{display:flex;gap:14px;align-items:center;background:var(--card);border:1px solid var(--linha);border-radius:18px;padding:12px;margin-bottom:12px;text-decoration:none;color:inherit}
.deal:hover{border-color:var(--coral)}
.num{flex:none;width:40px;height:40px;border-radius:50%;background:var(--tinta);color:var(--creme);display:grid;place-items:center;font-family:Outfit,sans-serif;font-weight:800}
.deal img{flex:none;width:76px;height:76px;object-fit:contain;background:#fff;border-radius:12px}
.info{min-width:0;flex:1}
.t{font-weight:500;line-height:1.3;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.p{margin-top:4px;font-size:14px;color:var(--cinza);display:flex;flex-wrap:wrap;align-items:baseline;gap:2px 8px}
.p b{font-family:Outfit,sans-serif;font-size:19px;color:var(--tinta);white-space:nowrap}
.p s{white-space:nowrap}
.tag{display:inline-block;font-size:12px;font-weight:700;padding:2px 8px;border-radius:8px;background:var(--areia);color:var(--tinta)}
.num{width:32px!important;height:32px!important;font-size:14px}
.off{flex:none;font-family:Outfit,sans-serif;font-weight:800;color:#fff;background:var(--coral);border-radius:12px;padding:6px 8px;font-size:15px}
.amz{display:block;text-align:center;padding:16px;border-radius:16px;background:var(--tinta);color:var(--creme);font-weight:700;text-decoration:none;margin-top:8px}
.velho .deal{opacity:.9}
.aviso{color:var(--cinza);font-size:14px;margin:-4px 0 10px}
#busca{width:100%;padding:12px 14px;border-radius:14px;border:1px solid var(--linha);background:var(--card);color:var(--tinta);font:inherit;margin-bottom:6px}
footer{margin-top:36px;font-size:13px;color:var(--cinza);line-height:1.5;text-align:center}
</style>
</head>
<body>
<main>
<header>
<img src="brand/avatar.png" alt="Alpha Promo">
<h1>alpha <span>promo</span></h1>
<p>As ofertas mais quentes do dia. Atualizado {{ atualizado }}.</p>
</header>

{% if lancamentos %}
<h2>Lançamentos e pré-vendas</h2>
{% for d in lancamentos %}
<a class="deal" href="{{ d.link }}" rel="nofollow sponsored noopener" target="_blank">
<span class="num">L{{ d.numero }}</span>
<img src="{{ d.imagem }}" alt="" loading="lazy">
<span class="info"><span class="t">{{ d.titulo }}</span>
<span class="p">{% if d.desconto >= 5 %}<s>{{ d.de }}</s>{% endif %}<b>{{ d.por }}</b><span class="tag">{{ d.loja }}</span></span></span>
{% if d.desconto >= 5 %}<span class="off">-{{ d.desconto }}%</span>{% endif %}
</a>
{% endfor %}
{% endif %}

<h2>Ofertas de hoje</h2>
{% for d in hoje %}
<a class="deal" href="{{ d.link }}" rel="nofollow sponsored noopener" target="_blank">
<span class="num">#{{ d.numero }}</span>
<img src="{{ d.imagem }}" alt="" loading="lazy">
<span class="info"><span class="t">{{ d.titulo }}</span>
<span class="p"><s>{{ d.de }}</s><b>{{ d.por }}</b><span class="tag">{{ d.loja }}</span></span></span>
<span class="off">-{{ d.desconto }}%</span>
</a>
{% else %}
<p>As ofertas de hoje saem logo cedo. Volte em instantes.</p>
{% endfor %}

{% if semana %}
<h2>Top 5 da semana</h2>
{% for d in semana %}
<a class="deal" href="{{ d.link }}" rel="nofollow sponsored noopener" target="_blank">
<span class="num">#{{ d.numero }}</span>
<img src="{{ d.imagem }}" alt="" loading="lazy">
<span class="info"><span class="t">{{ d.titulo }}</span>
<span class="p"><s>{{ d.de }}</s><b>{{ d.por }}</b><span class="tag">{{ d.loja }}</span></span></span>
<span class="off">-{{ d.desconto }}%</span>
</a>
{% endfor %}
{% endif %}

<a class="amz" href="{{ amazon }}" rel="nofollow sponsored noopener" target="_blank">Ver todas as ofertas do dia na Amazon</a>

<h2 id="anteriores">Ofertas anteriores</h2>
<p class="aviso">Procurando a oferta de um post antigo? Ache pelo dia do post ou pelo nome do produto. O preço é o do dia do post e pode ter mudado.</p>
<input id="busca" type="search" placeholder="Buscar produto ou código (ex.: 25103)" oninput="filtrar(this.value)">
{% for dia in anteriores %}
<section class="velho dia">
<h2>{{ dia.titulo }}</h2>
{% for d in dia.deals %}
<a class="deal" data-k="{{ (d.titulo ~ ' ' ~ d.codigo)|lower }}" href="{{ d.link }}" rel="nofollow sponsored noopener" target="_blank">
<span class="num">#{{ d.numero }}</span>
<img src="{{ d.imagem }}" alt="" loading="lazy">
<span class="info"><span class="t">{{ d.titulo }}</span>
<span class="p"><s>{{ d.de }}</s><b>{{ d.por }}</b><span class="tag">{{ d.loja }}</span></span></span>
<span class="off">-{{ d.desconto }}%</span>
</a>
{% endfor %}
</section>
{% endfor %}
<script>
function filtrar(q){q=q.toLowerCase().trim();document.querySelectorAll('.dia').forEach(function(s){var vis=0;s.querySelectorAll('.deal').forEach(function(a){var ok=!q||a.dataset.k.indexOf(q)>=0;a.style.display=ok?'':'none';if(ok)vis++});s.style.display=vis?'':'none'})}
</script>

<footer>Preços conferidos no início de cada dia; preço e estoque podem mudar a qualquer momento.<br>
Esta página contém links de afiliado: posso receber comissão pelas compras, sem custo extra para você.<br>
Como Associado da Amazon, recebo por compras qualificadas.</footer>
</main>
</body>
</html>
"""
)


def _itens(plan: dict, lista: str = "deals") -> list[dict]:
    out = []
    for i, raw in enumerate(plan.get(lista, []), start=1):
        d = Deal.from_dict(raw)
        out.append(
            {
                "numero": i,
                "titulo": d.titulo,
                "de": brl(d.preco_original),
                "por": brl(d.preco),
                "loja": d.loja,
                "desconto": d.desconto,
                "imagem": d.imagem,
                "link": d.link_afiliado or d.url,
            }
        )
    return out


def _lancamentos(hoje: date) -> list[dict]:
    """Lançamentos publicados nos últimos 7 dias (os mais novos primeiro)."""
    out = []
    for k in range(7):
        p = state.load_plan(hoje - timedelta(days=k)) or {}
        feitos = p.get("posts_avulsos", {})
        for item in _itens(p, "avulsos"):
            if any(str(v).startswith("ok:") for v in feitos.get(str(item["numero"]), {}).values()):
                out.append(item)
    for i, item in enumerate(out, start=1):
        item["numero"] = i
    return out


def _semana(hoje: date) -> dict:
    from . import carrossel

    c = carrossel.mais_recente(hoje)
    return c if c and str(c.get("post", "")).startswith("ok:") else {}


def codigo_curto(dia: date, n: int, avulso: bool = False) -> str:
    """Código do link curto da oferta: 0611-3 vira alphapromo.github.io/o/06113 (L = lançamento)."""
    return f"{dia:%d%m}{'L' if avulso else ''}{n}"


_REDIRECT = """<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="robots" content="noindex">
<meta property="og:type" content="product"><meta property="og:site_name" content="Alpha Promo">
<meta property="og:title" content="{titulo}"><meta property="og:description" content="{descricao}">
<meta property="og:image" content="{imagem}"><meta name="twitter:card" content="summary_large_image">
<meta http-equiv="refresh" content="0; url={url}">
<title>{titulo}</title><script>location.replace({js})</script></head>
<body style="font-family:sans-serif;padding:24px">Abrindo a oferta… <a href="{url}" rel="nofollow sponsored">toque aqui</a></body></html>"""


def _pagina_redirect(pasta, url: str, titulo: str, preco: float, loja: str, imagem: str) -> None:
    import json as _json
    from html import escape

    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / "index.html").write_text(_REDIRECT.format(
        url=escape(url), js=_json.dumps(url), titulo=escape(titulo), imagem=escape(imagem or ""),
        descricao=escape(f"{brl(preco)} no {loja} · oferta da Alpha Promo")), encoding="utf-8")


def ofertas_por_post() -> None:
    """docs/ofertas-ig.json: id do post no Instagram -> oferta (usado pelo "eu quero" instantâneo)."""
    import json as _json

    mapa = {}
    for iso, itens in state.load_arquivo().items():
        for x in itens:
            oferta = {"titulo": x["titulo"], "preco": x["preco"], "loja": x["loja"],
                      "link": f"https://alphapromo.github.io/o/{codigo_curto(date.fromisoformat(iso), x['n'])}"}
            if x.get("story"):
                mapa[x["story"]] = oferta  # resposta ao story também acha a oferta
            if x.get("ig"):
                mapa[x["ig"]] = {"titulo": x["titulo"], "preco": x["preco"], "loja": x["loja"],
                                 "link": f"https://alphapromo.github.io/o/{codigo_curto(date.fromisoformat(iso), x['n'])}"}
    (DOCS / "ofertas-ig.json").write_text(_json.dumps(mapa, ensure_ascii=False), encoding="utf-8")


def links_curtos(dia: date) -> None:
    """Páginas /o/<código> que redirecionam para o link de afiliado (usadas no comentário do post)."""
    import json as _json
    from html import escape

    for iso, itens in state.load_arquivo().items():  # ofertas antigas também mantêm o link curto
        for x in itens:
            _pagina_redirect(DOCS / "o" / codigo_curto(date.fromisoformat(iso), x["n"]), x["link"], x["titulo"],
                             x["preco"], x["loja"], x["imagem"])
    plano = state.load_plan(dia) or {}
    for lista, avulso in (("deals", False), ("avulsos", True)):
        for n, raw in enumerate(plano.get(lista, []), start=1):
            d = Deal.from_dict(raw)
            _pagina_redirect(DOCS / "o" / codigo_curto(dia, n, avulso), d.link_afiliado or d.url, d.titulo,
                             d.preco, d.loja, d.imagem)


def build(hoje: date, atualizado: str) -> None:
    DOCS.mkdir(exist_ok=True)
    brand = DOCS / "brand"
    brand.mkdir(exist_ok=True)
    for f in ("avatar.png", "simbolo.png", "logo.png"):
        src = ROOT / "assets" / "brand" / f
        if src.exists():
            shutil.copy(src, brand / f)
    (DOCS / ".nojekyll").write_text("")

    plano = state.load_plan(hoje) or {}
    state.arquivar(hoje, plano)
    anteriores = []
    arq = state.load_arquivo()
    corte = (hoje - timedelta(days=90)).isoformat()
    for iso in sorted(arq, reverse=True):
        if iso >= hoje.isoformat() or iso < corte:
            continue
        dia = date.fromisoformat(iso)
        itens = [{"numero": x["n"], "titulo": x["titulo"], "de": brl(x["preco_original"]), "por": brl(x["preco"]),
                  "loja": x["loja"], "desconto": x["desconto"], "imagem": x["imagem"], "link": x["link"],
                  "codigo": codigo_curto(dia, x["n"])} for x in arq[iso]]
        rotulo = "Ontem" if (hoje - dia).days == 1 else f"Post de {dia.strftime('%d/%m')}"
        anteriores.append({"titulo": f"{rotulo} ({dia.strftime('%d/%m')})" if rotulo == "Ontem" else rotulo, "deals": itens})
    html = TEMPLATE.render(
        hoje=_itens(plano), anteriores=anteriores, semana=_itens(_semana(hoje)), lancamentos=_lancamentos(hoje), atualizado=atualizado, amazon=amazon_ofertas_do_dia()
    )
    (DOCS / "index.html").write_text(html, encoding="utf-8")
    links_curtos(hoje)
    ofertas_por_post()
