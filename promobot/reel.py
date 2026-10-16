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

from PIL import Image

from . import render
from .models import Deal

log = logging.getLogger(__name__)
FPS = 30
SEG = 2.2        # segundos por foto
FADE = 0.4       # transição entre fotos
FINAL = 1.6      # segura a última foto no fim
ZOOM = 0.10      # zoom total de cada foto


def _encaixar(foto: Image.Image, caixa: tuple[int, int], escala: float) -> Image.Image:
    """Foto centralizada na caixa (sem cortar o produto), com zoom `escala`, fundo branco."""
    bw, bh = caixa
    f = foto.copy()
    f.thumbnail((int(bw * escala), int(bh * escala)), Image.LANCZOS)
    tela = Image.new("RGB", (bw, bh), render.BRANCO)
    tela.paste(f, ((bw - f.width) // 2, (bh - f.height) // 2))
    return tela


def frames(deal: Deal, numero: int, fotos: list[Image.Image]):
    fundo, camada, inner = render.render_post(deal, numero, "tiktok", None, partes=True)
    bw, bh = inner[2] - inner[0], inner[3] - inner[1]
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
        q.paste(atual, (inner[0], inner[1]))
        q.paste(camada, (0, 0), camada)
        yield q


def montar(deal: Deal, numero: int, fotos: list[Image.Image], destino: Path) -> Path:
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg não encontrado")
    fotos = [f for f in fotos if f is not None][:4]
    if not fotos:
        raise RuntimeError("sem fotos para o reel")
    if len(fotos) == 1:  # uma foto só: alterna com um zoom maior para ter movimento
        fotos = fotos * 2
    destino.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        for k, q in enumerate(frames(deal, numero, fotos)):
            q.save(f"{tmp}/{k:04d}.jpg", "JPEG", quality=88)
        cmd = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-framerate", str(FPS), "-i", f"{tmp}/%04d.jpg",
            "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
            "-shortest", "-c:v", "libx264", "-profile:v", "high", "-pix_fmt", "yuv420p",
            "-crf", "21", "-preset", "medium", "-r", str(FPS),
            "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(destino),
        ]
        subprocess.run(cmd, check=True)
    log.info("Reel da oferta #%s: %s (%.1f MB)", numero, destino, destino.stat().st_size / 1e6)
    return destino
