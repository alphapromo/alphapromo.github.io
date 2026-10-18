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
.velho .deal{opacity:.8}
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

{% for dia in anteriores %}
<section class="velho">
<h2>{{ dia.titulo }}</h2>
{% for d in dia.deals %}
<a class="deal" href="{{ d.link }}" rel="nofollow sponsored noopener" target="_blank">
<span class="num">#{{ d.numero }}</span>
<img src="{{ d.imagem }}" alt="" loading="lazy">
<span class="info"><span class="t">{{ d.titulo }}</span>
<span class="p"><s>{{ d.de }}</s><b>{{ d.por }}</b><span class="tag">{{ d.loja }}</span></span></span>
<span class="off">-{{ d.desconto }}%</span>
</a>
{% endfor %}
</section>
{% endfor %}

<footer>Preços conferidos no início de cada dia; preço e estoque podem mudar a qualquer momento.<br>
Esta página contém links de afiliado: posso receber comissão pelas compras, sem custo extra para você.<br>
Como Associado da Amazon, recebo por compras qualificadas.</footer>
</main>
</body>
</html>
"""
)


def _itens(plan: dict) -> list[dict]:
    out = []
    for i, raw in enumerate(plan.get("deals", []), start=1):
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


def _semana(hoje: date) -> dict:
    from . import carrossel

    c = carrossel.mais_recente(hoje)
    return c if c and str(c.get("post", "")).startswith("ok:") else {}


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
    anteriores = []
    nomes = {1: "Ofertas de ontem", 2: "Anteontem"}
    for k in (1, 2):
        dia = hoje - timedelta(days=k)
        p = state.load_plan(dia)
        if p:
            anteriores.append({"titulo": nomes[k] + f" ({dia.strftime('%d/%m')})", "deals": _itens(p)})
    html = TEMPLATE.render(
        hoje=_itens(plano), anteriores=anteriores, semana=_itens(_semana(hoje)), atualizado=atualizado, amazon=amazon_ofertas_do_dia()
    )
    (DOCS / "index.html").write_text(html, encoding="utf-8")
