"""Compõe a trilha original da Alpha Promo (sem direitos de terceiros).

Batida pop/house animada, 120 BPM, 16 segundos em loop:
bumbo 4x4, palmas no 2 e 4, chimbal, baixo e acordes em pluck (Dó–Sol–Lá m–Fá).
Gera assets/audio/trilha.wav. Rode: python tools/compor_trilha.py
"""
from pathlib import Path

import numpy as np
from scipy.io import wavfile
from scipy.signal import butter, lfilter

SR = 48000
BPM = 120
BEAT = 60 / BPM
COMPASSOS = 8                      # 8 compassos de 4 tempos = 16 s
DUR = COMPASSOS * 4 * BEAT
N = int(DUR * SR)
rng = np.random.default_rng(7)


def t(seg):
    return np.arange(int(seg * SR)) / SR


def env(n, ataque=0.005, decai=0.2):
    x = np.arange(n) / SR
    a = np.clip(x / ataque, 0, 1)
    return a * np.exp(-x / decai)


def nota(midi):
    return 440.0 * 2 ** ((midi - 69) / 12)


def lowpass(x, fc):
    b, a = butter(2, fc / (SR / 2), "low")
    return lfilter(b, a, x)


def highpass(x, fc):
    b, a = butter(2, fc / (SR / 2), "high")
    return lfilter(b, a, x)


def por(buf, som, inicio, ganho=1.0):
    i = int(inicio * SR)
    j = min(len(buf), i + len(som))
    buf[i:j] += som[: j - i] * ganho


def kick():
    x = t(0.35)
    f = 50 + 110 * np.exp(-x * 35)
    fase = 2 * np.pi * np.cumsum(f) / SR
    return np.sin(fase) * np.exp(-x * 9)


def clap():
    x = rng.standard_normal(int(0.18 * SR))
    x = highpass(lowpass(x, 3000), 900)
    e = env(len(x), 0.001, 0.06)
    return x * e


def hat(aberto=False):
    x = highpass(rng.standard_normal(int((0.12 if aberto else 0.04) * SR)), 7000)
    return x * env(len(x), 0.001, 0.05 if aberto else 0.012)


def baixo(midi, dur):
    x = t(dur)
    f = nota(midi)
    s = 2 * ((x * f) % 1) - 1                  # dente de serra
    s = lowpass(s, 380)
    return s * env(len(x), 0.004, dur * 0.8)


def pluck(midis, dur):
    x = t(dur)
    s = np.zeros_like(x)
    for m in midis:
        f = nota(m)
        s += np.sin(2 * np.pi * f * x) + 0.35 * np.sin(4 * np.pi * f * x) + 0.12 * np.sin(6 * np.pi * f * x)
    s /= len(midis)
    return lowpass(s, 2600) * env(len(x), 0.003, 0.18)


def compor() -> np.ndarray:
    drums = np.zeros(N)
    bass = np.zeros(N)
    keys = np.zeros(N)
    # Dó – Sol – Lá menor – Fá (um acorde por compasso, repete)
    progressao = [([60, 64, 67], 36), ([59, 62, 67], 43), ([60, 64, 69], 45), ([60, 65, 69], 41)]
    for c in range(COMPASSOS):
        acorde, raiz = progressao[c % 4]
        base = c * 4 * BEAT
        for b in range(4):
            tb = base + b * BEAT
            por(drums, kick(), tb, 0.95)
            if b in (1, 3):
                por(drums, clap(), tb, 0.55)
            por(drums, hat(), tb + BEAT / 2, 0.35)          # contratempo
            por(drums, hat(), tb, 0.15)
            if c >= 2:                                       # baixo entra no 3º compasso
                por(bass, baixo(raiz, BEAT * 0.45), tb + BEAT / 2, 0.5)
        # pluck sincopado: 1, 1e, 2e, 3, 4
        for off in (0, 0.75, 1.5, 2.5, 3.25):
            por(keys, pluck(acorde, BEAT * 0.6), base + off * BEAT, 0.42)
        if c % 4 == 3:
            por(drums, hat(aberto=True), base + 3.5 * BEAT, 0.3)
    mix = drums * 0.8 + bass * 0.9 + keys * 0.8
    # "sidechain" leve: abaixa os teclados/baixo no bumbo, dá o balanço de house
    duck = np.ones(N)
    for k in range(int(DUR / BEAT)):
        i = int(k * BEAT * SR)
        n = int(0.18 * SR)
        duck[i:i + n] = np.minimum(duck[i:i + n], 0.55 + 0.45 * (np.arange(min(n, N - i)) / n))
    mix = drums * 0.8 + (bass * 0.9 + keys * 0.8) * duck
    mix /= np.max(np.abs(mix)) + 1e-9
    mix = np.tanh(mix * 1.4) / np.tanh(1.4) * 0.89    # cola e volume
    estereo = np.stack([mix, np.roll(mix, int(0.004 * SR)) * 0.98], axis=1)
    return estereo


if __name__ == "__main__":
    out = Path(__file__).resolve().parent.parent / "assets" / "audio" / "trilha.wav"
    out.parent.mkdir(parents=True, exist_ok=True)
    wavfile.write(out, SR, (compor() * 32767).astype(np.int16))
    print(out, f"{DUR:.1f}s")
