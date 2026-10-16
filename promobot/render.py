"""Gera as artes dos posts (feed 4:5 e TikTok/Stories 9:16) e as imagens da marca."""
from __future__ import annotations

import io
import logging
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont, ImageOps

from .config import ROOT
from .models import Deal, brl

log = logging.getLogger(__name__)
FONTS = ROOT / "assets" / "fonts"

CREME = "#FBF7F2"
CORAL = "#E07A62"
CORAL_TXT = "#C8644D"
AREIA = "#F3DFCC"
SALVIA = "#7FA89E"
TINTA = "#24283B"
CINZA = "#6B6F7E"
CINZA_CLARO = "#8A8E9C"
MARROM = "#5B4A3E"
BRANCO = "#FFFFFF"
COR_LOJA = {"Mercado Livre": SALVIA, "Amazon": "#7E8FC9"}


def font(nome: str, size: int, peso: int) -> ImageFont.FreeTypeFont:
    arquivo = {"outfit": "Outfit.ttf", "dm": "DMSans.ttf", "noto": "NotoSans.ttf"}[nome]
    f = ImageFont.truetype(str(FONTS / arquivo), size)
    eixos = {"outfit": [peso], "dm": [14, peso], "noto": [peso, 100]}[nome]
    f.set_variation_by_axes(eixos)
    return f


# ------------------------------------------------------------------ símbolo
def mark(size: int, fill: str = CORAL, fundo: str = CREME) -> Image.Image:
    """Etiqueta de preço com α, girada -10° (igual ao design)."""
    s = 8  # supersampling
    W = 200 * s
    img = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([60 * s, 38 * s, 182 * s, 162 * s], radius=18 * s, fill=fill)
    d.polygon([(72 * s, 38 * s), (14 * s, 100 * s), (72 * s, 162 * s)], fill=fill)
    d.ellipse([40 * s, 90 * s, 60 * s, 110 * s], fill=fundo)
    f = font("noto", 112 * s, 800)  # Outfit e DM Sans não têm a letra grega α
    d.text((121 * s, 100 * s), "α", font=f, fill=fundo, anchor="mm")
    img = img.rotate(10, resample=Image.BICUBIC)
    return img.resize((size, size), Image.LANCZOS)


def _paste(base: Image.Image, im: Image.Image, xy):
    base.paste(im, xy, im if im.mode == "RGBA" else None)


def _wordmark(d: ImageDraw.ImageDraw, x: int, y_center: int, size: int):
    f = font("outfit", size, 800)
    d.text((x, y_center), "alpha ", font=f, fill=TINTA, anchor="lm")
    w = d.textlength("alpha ", font=f)
    d.text((x + w, y_center), "promo", font=f, fill=CORAL_TXT, anchor="lm")


def _pill(d, x_right: int, y: int, h: int, text: str, size: int):
    f = font("outfit", size, 700)
    w = d.textlength(text, font=f) + 52
    d.rounded_rectangle([x_right - w, y, x_right, y + h], radius=h // 2, fill=TINTA)
    d.text((x_right - w / 2, y + h / 2), text, font=f, fill=CREME, anchor="mm")


def _wrap(d, text: str, f, max_w: int, max_lines: int) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if d.textlength(t, font=f) <= max_w:
            cur = t
        else:
            lines.append(cur)
            cur = w
            if len(lines) == max_lines:
                break
    if len(lines) < max_lines and cur:
        lines.append(cur)
    if len(lines) == max_lines and " ".join(lines) != " ".join(words):
        last = lines[-1]
        while d.textlength(last + "…", font=f) > max_w and " " in last:
            last = last.rsplit(" ", 1)[0]
        lines[-1] = last + "…"
    return lines


def baixar_imagem(url: str) -> Image.Image | None:
    try:
        if url.startswith(("http://", "https://")):
            r = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
            r.raise_for_status()
            im = Image.open(io.BytesIO(r.content))
        else:
            im = Image.open((ROOT / url) if not url.startswith("/") else url)
        im = ImageOps.exif_transpose(im).convert("RGBA")
        bg = Image.new("RGBA", im.size, BRANCO)
        bg.alpha_composite(im)
        return bg.convert("RGB")
    except Exception as e:  # noqa: BLE001
        log.warning("Não consegui baixar a imagem %s: %s", url, e)
        return None


# ------------------------------------------------------------------ post
def render_post(deal: Deal, numero: int, formato: str, produto: Image.Image | None, partes: bool = False):
    """partes=True: devolve (fundo, camada de selos RGBA, caixa do produto) para montar vídeo."""
    vertical = formato == "tiktok"
    W, H = (1080, 1920) if vertical else (1080, 1350)
    pad_l, pad_r, pad_t, pad_b = (72, 140, 190, 270) if vertical else (64, 64, 56, 56)
    img = Image.new("RGB", (W, H), CREME)
    d = ImageDraw.Draw(img)
    x0, x1 = pad_l, W - pad_r

    # cabeçalho
    m = 80 if vertical else 72
    _paste(img, mark(m), (x0, pad_t))
    _wordmark(d, x0 + m + 16, pad_t + m // 2, 44 if vertical else 40)
    if vertical:
        y = pad_t + m + 22
        f = font("outfit", 30, 700)
        w = d.textlength(f"OFERTA #{numero} DO DIA", font=f) + 52
        d.rounded_rectangle([x0, y, x0 + w, y + 62], radius=31, fill=TINTA)
        d.text((x0 + w / 2, y + 31), f"OFERTA #{numero} DO DIA", font=f, fill=CREME, anchor="mm")
        card_top = y + 62 + 40
    else:
        _pill(d, x1, pad_t + 5, 62, f"OFERTA #{numero} DO DIA", 28)
        card_top = pad_t + m + 36

    # bloco inferior (de baixo para cima)
    bar_h = 104 if vertical else 96
    bar_top = H - pad_b - bar_h
    d.rounded_rectangle([x0, bar_top, x1, H - pad_b], radius=24, fill=AREIA)
    f_bar = font("outfit", 40 if vertical else 36, 700)
    d.text(((x0 + x1) / 2, bar_top + bar_h / 2), f"Link na bio · oferta #{numero}", font=f_bar, fill=TINTA, anchor="mm")

    f_title = font("dm", 40 if vertical else 38, 500)
    f_de = font("dm", 36 if vertical else 34, 400)
    f_por = font("outfit", 108 if vertical else 96, 800)
    linhas = _wrap(d, deal.titulo, f_title, x1 - x0, 2)
    lh = int(f_title.size * 1.25)
    por_h = f_por.size
    if vertical:
        bloco_h = len(linhas) * lh + 16 + f_de.size + 16 + por_h
    else:
        bloco_h = len(linhas) * lh + 14 + por_h
    bloco_top = bar_top - 40 - bloco_h
    y = bloco_top
    for ln in linhas:
        d.text((x0, y), ln, font=f_title, fill=TINTA)
        y += lh
    de_txt = brl(deal.preco_original)
    if vertical:
        y += 16
        d.text((x0, y), de_txt, font=f_de, fill=CINZA)
        tw = d.textlength(de_txt, font=f_de)
        d.line([x0, y + f_de.size * 0.62, x0 + tw, y + f_de.size * 0.62], fill=CINZA, width=3)
        y += f_de.size + 16
        d.text((x0, y), brl(deal.preco), font=f_por, fill=TINTA)
    else:
        y += 14
        por_y = y + por_h * 0.78
        d.text((x0, por_y), de_txt, font=f_de, fill=CINZA, anchor="ls")
        tw = d.textlength(de_txt, font=f_de)
        d.line([x0, por_y - f_de.size * 0.33, x0 + tw, por_y - f_de.size * 0.33], fill=CINZA, width=3)
        d.text((x0 + tw + 24, por_y), brl(deal.preco), font=f_por, fill=TINTA, anchor="ls")

    # cartão do produto
    card_bot = bloco_top - 40
    d.rounded_rectangle([x0, card_top, x1, card_bot], radius=40 if not vertical else 44, fill=BRANCO)
    d.line([x0 + 40, card_bot + 1, x1 - 40, card_bot + 1], fill="#EFE6DB", width=2)
    inner = (x0 + 70, card_top + 110, x1 - 70, card_bot - 60)
    if produto is not None and not partes:
        p = produto.copy()
        p.thumbnail((inner[2] - inner[0], inner[3] - inner[1]), Image.LANCZOS)
        px = inner[0] + (inner[2] - inner[0] - p.width) // 2
        py = inner[1] + (inner[3] - inner[1] - p.height) // 2
        img.paste(p, (px, py))
    elif not partes:
        d.text(((x0 + x1) / 2, (card_top + card_bot) / 2), deal.loja, font=font("dm", 32, 500), fill=CINZA_CLARO, anchor="mm")

    # selos (loja e desconto) numa camada própria, por cima do produto
    camada = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    o = ImageDraw.Draw(camada)
    f_loja = font("dm", 28 if vertical else 26, 700)
    lw = o.textlength(deal.loja, font=f_loja) + 44
    o.rounded_rectangle([x0 + 32, card_top + 32, x0 + 32 + lw, card_top + 32 + 54], radius=14, fill=COR_LOJA.get(deal.loja, SALVIA))
    o.text((x0 + 32 + lw / 2, card_top + 32 + 27), deal.loja, font=f_loja, fill=BRANCO, anchor="mm")
    r = 85 if vertical else 75
    cx, cy = (x1 - 32 - r, card_bot - 32 - r) if vertical else (x1 - 28 - r, card_top + 28 + r)
    o.ellipse([cx - r, cy - r, cx + r, cy + r], fill=CORAL)
    o.text((cx, cy), f"-{deal.desconto}%", font=font("outfit", 58 if vertical else 52, 800), fill=BRANCO, anchor="mm")
    if partes:
        return img, camada, inner
    img.paste(camada, (0, 0), camada)
    return img


def salvar_jpeg(img: Image.Image, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(path, "JPEG", quality=90, optimize=True, progressive=True)


# ------------------------------------------------------------------ marca
def brand_assets(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    av = Image.new("RGB", (1080, 1080), CORAL)
    m = mark(700, fill=CREME, fundo=CORAL)
    _paste(av, m, (190, 190))
    av.save(out / "avatar.png")

    logo = Image.new("RGBA", (1120, 360), (0, 0, 0, 0))
    _paste(logo, mark(300), (20, 30))
    d = ImageDraw.Draw(logo)
    f = font("outfit", 150, 800)
    d.text((340, 180), "alpha ", font=f, fill=TINTA, anchor="lm")
    w = d.textlength("alpha ", font=f)
    d.text((340 + w, 180), "promo", font=f, fill=CORAL_TXT, anchor="lm")
    bbox = logo.getbbox()
    logo = logo.crop(bbox)
    logo.save(out / "logo.png")
    mark(512).save(out / "simbolo.png")
