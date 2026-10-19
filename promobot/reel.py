"""Monta um Reel vertical (9:16, ~10 s) com as fotos do produto e o card de preço.

Cada foto aparece com zoom suave e transição em fade; a moldura (logo, preço,
desconto, "Link na bio") fica fixa. Precisa do ffmpeg (já vem no GitHub Actions).
"""
from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

from datetime import date

from PIL import Image, ImageDraw

from . import carta, render
from .models import Deal

log = logging.getLogger(__name__)
FPS = 30
SEG = 2.2        # segundos por foto
FADE = 0.4       # transição entre fotos
FINAL = 1.6      # segura a última foto no fim
ZOOM = 0.10      # zoom total de cada foto
GANCHO = 1.3     # segundos da frase de impacto no começo (antes das fotos)
TRILHA = Path(__file__).resolve().parent.parent / "assets" / "audio" / "trilha.m4a"


def _encaixar(foto: Image.Image, caixa: tuple[int, int], escala: float) -> Image.Image:
    """Foto centralizada na vitrine (sem cortar o produto), com zoom `escala`, fundo branco."""
    bw, bh = caixa
    f = foto.copy()
    f.thumbnail((int(bw * 0.82 * escala), int(bh * 0.86 * escala)), Image.LANCZOS)
    tela = Image.new("RGB", (bw, bh), render.BRANCO)
    tela.paste(f, ((bw - f.width) // 2, (bh - f.height) // 2))
    return tela


def _gancho(deal: Deal, caixa: tuple[int, int]) -> Image.Image:
    """Frase de impacto do primeiro segundo: '#2 mais vendido / em Games hoje'."""
    bw, bh = caixa
    tela = Image.new("RGB", (bw, bh), render.BRANCO)
    d = ImageDraw.Draw(tela)
    pos = deal.extras.get("posicao")
    if pos and int(pos) <= 20:
        l1, l2 = f"#{int(pos)} mais vendido", f"em {deal.categoria} hoje"
    else:
        l1, l2 = f"{deal.desconto}% OFF", "só hoje, olha isso"
    f1 = render.font("outfit", 96, 800)
    while d.textlength(l1, font=f1) > bw - 80 and f1.size > 50:
        f1 = render.font("outfit", f1.size - 6, 800)
    f2 = render.font("dm", 44, 600)
    while d.textlength(l2, font=f2) > bw - 80 and f2.size > 26:
        f2 = render.font("dm", f2.size - 4, 600)
    d.text((bw / 2, bh / 2 - 40), l1, font=f1, fill=render.TINTA, anchor="mm")
    d.text((bw / 2, bh / 2 + 60), l2, font=f2, fill=render.CORAL_TXT, anchor="mm")
    return tela


def frames(deal: Deal, numero: int, fotos: list[Image.Image], total_dia: int = 5, dia: date | None = None):
    """Quadros do Reel: a Alpha Card vertical fixa e as fotos passando na vitrine branca."""
    fundo, inner = carta.render(deal, numero, total_dia, "tiktok", deal.extras.get("num_colecao") or 1,
                                dia or date.today(), None, vitrine=True)
    bw, bh = inner[2] - inner[0], inner[3] - inner[1]
    mascara = Image.new("L", (bw, bh), 0)
    ImageDraw.Draw(mascara).rounded_rectangle([0, 0, bw - 1, bh - 1], radius=30, fill=255)
    n_seg = int(SEG * FPS)
    n_fade = int(FADE * FPS)
    total = n_seg * len(fotos) + int(FINAL * FPS)

    def quadro_foto(i: int, t: int) -> Image.Image:
        i = min(i, len(fotos) - 1)
        prog = min(t / (n_seg + n_fade), 1.0)
        return _encaixar(fotos[i], (bw, bh), 1.0 + ZOOM * prog)

    for k in range(total):
        i, t = divmod(k, n_seg)
        atual = quadro_foto(i, t)
        if i + 1 < len(fotos) and t >= n_seg - n_fade:  # fade para a próxima foto
            alfa = (t - (n_seg - n_fade)) / n_fade
            atual = Image.blend(atual, quadro_foto(i + 1, 0), alfa)
        q = fundo.copy()
        q.paste(atual, (inner[0], inner[1]), mascara)
        yield q


def montar(deal: Deal, numero: int, fotos: list[Image.Image], destino: Path, total_dia: int = 5,
           dia: date | None = None) -> Path:
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg não encontrado")
    fotos = [f for f in fotos if f is not None][:4]
    if not fotos:
        raise RuntimeError("sem fotos para o reel")
    if len(fotos) == 1:  # uma foto só: alterna com um zoom maior para ter movimento
        fotos = fotos * 2
    destino.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        for k, q in enumerate(frames(deal, numero, fotos, total_dia, dia)):
            q.save(f"{tmp}/{k:04d}.jpg", "JPEG", quality=88)
        n_quadros = len(list(Path(tmp).glob("*.jpg")))
        dur = n_quadros / FPS
        if TRILHA.exists():  # trilha original da Alpha Promo, com fade no fim
            audio = ["-stream_loop", "-1", "-i", str(TRILHA)]
            filtro = ["-af", f"volume=0.85,afade=t=in:d=0.15,afade=t=out:st={max(dur - 0.8, 0):.2f}:d=0.8"]
        else:
            audio = ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000"]
            filtro = []
        cmd = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-framerate", str(FPS), "-i", f"{tmp}/%04d.jpg",
            *audio, *filtro, "-t", f"{dur:.2f}",
            "-c:v", "libx264", "-profile:v", "high", "-pix_fmt", "yuv420p",
            "-crf", "21", "-preset", "medium", "-r", str(FPS),
            "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-movflags", "+faststart", str(destino),
        ]
        subprocess.run(cmd, check=True)
    log.info("Reel da oferta #%s: %s (%.1f MB)", numero, destino, destino.stat().st_size / 1e6)
    return destino
