"""Alpha Card v2: a arte dos posts como carta colecionável (aprovada no Claude Design).

A carta é montada em HTML e fotografada pelo Chrome headless (Playwright), com
as fontes locais de assets/fonts. A raridade vem do desconto real:
    Comum até 44% · Rara 45–54% · Épica 55–62% · Lendária 63% ou mais.

Formatos: "feed" 1080×1350 e "tiktok" (Stories/Reel) 1080×1920.
Para o Reel, `vitrine=True` devolve também a caixa branca onde entram as fotos.
"""
from __future__ import annotations

import base64
import calendar
import html
import io
import logging
import subprocess
import sys
from datetime import date

from PIL import Image

from .config import ROOT
from .models import Deal, brl

log = logging.getLogger(__name__)
FONTS = ROOT / "assets" / "fonts"
MESES = ["JAN", "FEV", "MAR", "ABR", "MAI", "JUN", "JUL", "AGO", "SET", "OUT", "NOV", "DEZ"]

TIERS = {
    "comum": dict(nome="COMUM", simbolo="circulo",
                  moldura="linear-gradient(135deg,#F1ECE6 0%,#D6CEC4 35%,#FAF7F3 55%,#CFC6BB 100%)",
                  superficie="linear-gradient(160deg,#FCFAF7 0%,#F1ECE5 100%)", tinta="#6B6F7E", barra="#B9B0A5", holo=0.0),
    "rara": dict(nome="RARA", simbolo="losango",
                 moldura="linear-gradient(135deg,#EAF4F0 0%,#A9C7BD 30%,#F7FBFA 52%,#93B7AB 78%,#E2EFEA 100%)",
                 superficie="linear-gradient(160deg,#F5FAF8 0%,#E1EDE8 100%)", tinta="#4F7F74", barra="#93B7AB", holo=0.35),
    "epica": dict(nome="ÉPICA", simbolo="brilho",
                  moldura="linear-gradient(135deg,#F1EDFB 0%,#C3B7EA 30%,#FAF8FE 52%,#AFA0DF 78%,#EAE4F8 100%)",
                  superficie="linear-gradient(160deg,#F8F6FD 0%,#E9E3F7 100%)", tinta="#6656A6", barra="#AFA0DF", holo=0.5),
    "lendaria": dict(nome="LENDÁRIA", simbolo="estrela",
                     moldura="linear-gradient(135deg,#FFF6DD 0%,#E3C47E 26%,#FFFBEF 48%,#CDA457 72%,#F6E3B0 100%)",
                     superficie="linear-gradient(160deg,#FFFBF1 0%,#F5E8C9 100%)", tinta="#9A6F1C", barra="#CDA457", holo=0.55),
}

# símbolos desenhados em SVG (não dependem de fonte instalada no servidor)
_SVG = {
    "circulo": '<circle cx="12" cy="12" r="6.5"/>',
    "losango": '<path d="M12 3.5 20.5 12 12 20.5 3.5 12Z"/>',
    "brilho": '<path d="M12 2.5c.9 5.2 3.3 7.6 9.5 9.5-6.2 1.9-8.6 4.3-9.5 9.5-.9-5.2-3.3-7.6-9.5-9.5 6.2-1.9 8.6-4.3 9.5-9.5Z"/>',
    "estrela": '<path d="m12 2.8 2.8 6 6.5.7-4.9 4.4 1.4 6.4L12 17l-5.8 3.3 1.4-6.4-4.9-4.4 6.5-.7Z"/>',
}


def raridade(desconto: int) -> str:
    if desconto >= 63:
        return "lendaria"
    if desconto >= 55:
        return "epica"
    if desconto >= 45:
        return "rara"
    return "comum"


def colecao(dia: date) -> tuple[str, int]:
    """('OUT/26', 155): nome da coleção do mês e total previsto de cartas (5 por dia)."""
    return f"{MESES[dia.month - 1]}/{dia.strftime('%y')}", calendar.monthrange(dia.year, dia.month)[1] * 5


def _simbolo(t: dict, px: int) -> str:
    return f'<svg width="{px}" height="{px}" viewBox="0 0 24 24" fill="{t["tinta"]}">{_SVG[t["simbolo"]]}</svg>'


def _data_uri(img: Image.Image | None) -> str:
    if img is None:
        return ""
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "JPEG", quality=92)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def _nome_curto(titulo: str, n: int = 58) -> str:
    t = " ".join(titulo.split())
    return t if len(t) <= n else t[: n - 1].rsplit(" ", 1)[0] + "…"


def _sem_rs(valor: float) -> str:
    return brl(valor).replace("R$", "").strip()


_CSS_FONTES = ""


def _fontes() -> str:
    """Fontes embutidas (data URI): a página não tem origem de arquivo, então file:// não carrega."""
    global _CSS_FONTES
    if not _CSS_FONTES:
        def ff(nome, arq):
            b64 = base64.b64encode((FONTS / arq).read_bytes()).decode()
            return (f"@font-face{{font-family:'{nome}';src:url(data:font/ttf;base64,{b64}) format('truetype');"
                    f"font-weight:100 900;font-style:normal}}")
        _CSS_FONTES = ff("Outfit", "Outfit.ttf") + ff("DM Sans", "DMSans.ttf")
    return _CSS_FONTES


def _carta_html(d: Deal, numero_colecao: str, nome_colecao: str, img_uri: str) -> str:
    t = TIERS[raridade(d.desconto)]
    produto = html.escape(_nome_curto(d.titulo))
    tam_nome = 46 if len(produto) <= 34 else 40 if len(produto) <= 46 else 36
    categoria = html.escape((d.extras.get("tema") or d.categoria or d.loja).upper())
    por = _sem_rs(d.preco)
    tam_por = 116 if len(por) <= 6 else 100 if len(por) <= 8 else 86
    economia = _sem_rs(d.preco_original - d.preco)
    foto = f'<img src="{img_uri}" style="max-width:82%;max-height:86%;object-fit:contain">' if img_uri else ""
    return f"""
<div style="position:absolute;left:70px;top:48px;width:940px;height:1254px;border-radius:44px;padding:12px;box-sizing:border-box;background:{t['moldura']};box-shadow:0 30px 70px rgba(80,60,40,.18),0 4px 14px rgba(80,60,40,.10)">
 <div style="position:relative;width:100%;height:100%;border-radius:34px;overflow:hidden;background:{t['superficie']}">
  <div style="position:absolute;inset:0;background:repeating-linear-gradient(115deg,rgba(255,255,255,.55) 0 1px,transparent 1px 7px);opacity:.35"></div>
  <div style="position:absolute;inset:0;background:linear-gradient(115deg,transparent 15%,#FFD3EC 30%,#CDEBFF 42%,#FFF4C9 54%,#D7FBE8 66%,transparent 85%);mix-blend-mode:multiply;opacity:{t['holo']}"></div>
  <div style="position:absolute;left:44px;right:44px;top:40px;height:140px;display:flex;justify-content:space-between;align-items:flex-start;gap:24px">
   <div style="display:flex;flex-direction:column;gap:8px;min-width:0">
    <span style="font-size:18px;font-weight:700;letter-spacing:4px;color:{t['tinta']}">{categoria}</span>
    <span style="font-family:Outfit;font-size:{tam_nome}px;font-weight:800;letter-spacing:-1px;line-height:1.05;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden">{produto}</span>
   </div>
   <span style="flex-shrink:0;padding:12px 22px;border-radius:999px;background:#E07A62;color:#fff;font-family:Outfit;font-size:44px;font-weight:800">-{d.desconto}%</span>
  </div>
  <div id="vitrine" style="position:absolute;left:44px;right:44px;top:200px;height:640px;border-radius:30px;background:#FFFFFF;box-shadow:inset 0 0 0 1px rgba(36,40,59,.06),0 10px 30px rgba(80,60,40,.08);display:flex;align-items:center;justify-content:center;overflow:hidden">{foto}</div>
  <div style="position:absolute;left:44px;right:44px;top:870px;display:flex;align-items:flex-end;justify-content:space-between;gap:20px">
   <div style="display:flex;flex-direction:column;gap:2px;min-width:0">
    <span style="font-size:26px;color:#6B6F7E;text-decoration:line-through">de R$ {_sem_rs(d.preco_original)}</span>
    <span style="font-family:Outfit;font-size:{tam_por}px;font-weight:800;letter-spacing:-3px;line-height:1;white-space:nowrap">R$ {por}</span>
   </div>
   <div style="display:flex;flex-direction:column;align-items:flex-end;gap:4px;padding-bottom:14px;flex-shrink:0">
    <span style="font-size:16px;font-weight:700;letter-spacing:3px;color:#6B6F7E">VOCÊ ECONOMIZA</span>
    <span style="font-family:Outfit;font-size:40px;font-weight:800;color:{t['tinta']};white-space:nowrap">R$ {economia}</span>
   </div>
  </div>
  <div style="position:absolute;left:44px;right:44px;top:1052px;font-size:21px;font-weight:500;color:#6B6F7E">{html.escape(d.loja)}{' · frete grátis' if d.frete_gratis else ''}</div>
  <div style="position:absolute;left:44px;right:44px;bottom:40px;display:flex;align-items:center;justify-content:space-between;padding-top:22px;border-top:1px solid rgba(36,40,59,.12);font-size:19px;font-weight:700;letter-spacing:2px">
   <span style="display:flex;align-items:center;gap:12px;color:{t['tinta']}"><span style="width:40px;height:40px;border-radius:50%;display:flex;align-items:center;justify-content:center;background:{t['moldura']}">{_simbolo(t, 20)}</span>{t['nome']}</span>
   <span style="color:#6B6F7E">ALPHA · {nome_colecao} · {numero_colecao}</span>
   <span style="font-family:Outfit;font-size:24px;font-weight:800;letter-spacing:0">alpha <span style="color:#C8644D">promo</span></span>
  </div>
 </div>
</div>"""


def pagina(d: Deal, n_dia: int, total_dia: int, formato: str, num_colecao: int, dia: date, img: Image.Image | None) -> str:
    nome_col, total_col = colecao(dia)
    numero = f"{num_colecao:03d}/{max(total_col, num_colecao)}"
    t = TIERS[raridade(d.desconto)]
    carta = _carta_html(d, numero, nome_col, _data_uri(img))
    base = (f"<!doctype html><html><head><meta charset='utf-8'><style>{_fontes()}"
            "body{margin:0}*{-webkit-font-smoothing:antialiased}</style></head><body>")
    if formato != "tiktok":
        return (base + f'<div id="arte" style="width:1080px;height:1350px;position:relative;background:#FBF7F2;'
                f'font-family:\'DM Sans\';color:#24283B;overflow:hidden">{carta}</div></body></html>')
    barras = "".join(
        f'<span style="width:70px;height:8px;border-radius:4px;background:{t["barra"] if k <= n_dia else t["barra"] + "40"}"></span>'
        for k in range(1, max(total_dia, n_dia) + 1))
    return base + f"""
<div id="arte" style="width:1080px;height:1920px;position:relative;background:#FBF7F2;font-family:'DM Sans';color:#24283B;overflow:hidden">
 <div style="position:absolute;left:72px;right:140px;top:150px;display:flex;flex-direction:column;gap:14px">
  <span style="font-size:24px;font-weight:700;letter-spacing:6px;color:{t['tinta']}">PACOTE DE HOJE · CARTA {n_dia} DE {max(total_dia, n_dia)}</span>
  <div style="display:flex;gap:10px">{barras}</div>
 </div>
 <div style="position:absolute;left:0;top:250px;width:1080px;height:1350px">{carta}</div>
 <div style="position:absolute;left:72px;right:140px;top:1620px;display:flex;align-items:center;justify-content:space-between">
  <span style="font-family:Outfit;font-size:44px;font-weight:800">Link na bio · carta #{n_dia}</span>
  <span style="display:flex;align-items:center;gap:10px;font-size:22px;font-weight:700;letter-spacing:3px;color:{t['tinta']}">{_simbolo(t, 22)} {t['nome']}</span>
 </div>
</div></body></html>"""


# ------------------------------------------------------------------ navegador
class Fotografo:
    """Abre o Chrome headless uma vez e fotografa várias cartas."""

    def __enter__(self):
        from playwright.sync_api import sync_playwright

        self._pw = sync_playwright().start()
        self._browser = None
        for tentativa in ("padrao", "chrome", "instalar"):
            try:
                if tentativa == "chrome":
                    self._browser = self._pw.chromium.launch(channel="chrome")
                else:
                    if tentativa == "instalar":
                        log.info("Instalando o Chromium do Playwright…")
                        subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
                    self._browser = self._pw.chromium.launch()
                break
            except Exception as e:  # noqa: BLE001
                log.debug("Chrome (%s) indisponível: %s", tentativa, e)
        if self._browser is None:
            raise RuntimeError("não consegui abrir o Chrome headless")
        self._page = self._browser.new_page(viewport={"width": 1080, "height": 1920})
        return self

    def __exit__(self, *exc):
        self._browser.close()
        self._pw.stop()

    def foto(self, html_: str, vitrine: bool = False):
        self._page.set_content(html_, wait_until="load")
        self._page.evaluate("document.fonts.ready")
        arte = self._page.locator("#arte")
        png = arte.screenshot(type="png")
        img = Image.open(io.BytesIO(png)).convert("RGB")
        if not vitrine:
            return img
        b = self._page.locator("#vitrine").bounding_box()
        a = arte.bounding_box()
        caixa = tuple(int(round(v)) for v in (b["x"] - a["x"], b["y"] - a["y"],
                                              b["x"] - a["x"] + b["width"], b["y"] - a["y"] + b["height"]))
        return img, caixa


def render(d: Deal, n_dia: int, total_dia: int, formato: str, num_colecao: int, dia: date,
           img: Image.Image | None, fotografo: Fotografo | None = None, vitrine: bool = False):
    html_ = pagina(d, n_dia, total_dia, formato, num_colecao, dia, img)
    if fotografo is not None:
        return fotografo.foto(html_, vitrine)
    with Fotografo() as f:
        return f.foto(html_, vitrine)
