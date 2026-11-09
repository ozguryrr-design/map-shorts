"""Procedural sound design (whoosh / pop / thump / swish) + final mix with VO.

Scene module may define:
    VO  = [("vo/l1.mp3", 0.30), ...]           # voiceover clips and start times
    SFX = [(t, "whoosh", dict(dur=2.0, gain=0.5)), (t, "pop", {}), ...]
    MUSIC = ("music.mp3", gain_db)             # optional background bed
"""
import math
import os
import subprocess
import wave

import numpy as np

SR = 48000
_rng = np.random.default_rng(7)


def _svf_bandpass(x, fc, q=0.9):
    """Time-varying state-variable band-pass; fc: array of cutoff (Hz)."""
    low = band = 0.0
    out = np.empty_like(x)
    f = 2 * np.sin(np.pi * np.clip(fc, 20, SR / 6) / SR)
    damp = 1.0 / q
    for i in range(len(x)):
        high = x[i] - low - damp * band
        band += f[i] * high
        low += f[i] * band
        out[i] = band
    return out


def whoosh(dur=1.6, gain=0.5, f0=250, f1=2200, peak=0.55):
    n = int(dur * SR)
    t = np.linspace(0, 1, n)
    env = np.where(t < peak, (t / peak) ** 2.2, ((1 - t) / (1 - peak)) ** 1.6)
    fc = f0 + (f1 - f0) * np.sin(np.pi * np.clip(t / (peak * 2), 0, 1)) ** 2
    L = _svf_bandpass(_rng.standard_normal(n) * 0.5, fc)
    R = _svf_bandpass(_rng.standard_normal(n) * 0.5, fc * 1.07)
    st = np.stack([L, R], 1) * env[:, None]
    # gentle stereo pan sweep
    pan = np.sin(np.pi * t) * 0.35
    st[:, 0] *= 1 - pan * (t < 0.5)
    st[:, 1] *= 1 - pan * (t >= 0.5)
    return _norm(st) * gain


def swish(dur=0.35, gain=0.25):
    return whoosh(dur, gain, f0=1500, f1=6000, peak=0.35)


def pop(gain=0.5, f0=420, f1=140, dur=0.22):
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = f1 + (f0 - f1) * np.exp(-t * 28)
    ph = 2 * np.pi * np.cumsum(f) / SR
    s = np.sin(ph) * np.exp(-t * 16)
    click = _rng.standard_normal(n) * np.exp(-t * 400) * 0.25
    m = (s + click)
    return _norm(np.stack([m, m], 1)) * gain


def thump(gain=0.6, dur=0.5):
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = 45 + 70 * np.exp(-t * 20)
    s = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 7)
    s += _svf_bandpass(_rng.standard_normal(n), np.full(n, 900.0)) * np.exp(-t * 35) * 0.3
    return _norm(np.stack([s, s], 1)) * gain


def shimmer(gain=0.18, dur=0.9):
    """soft bell-ish sparkle for a reveal"""
    n = int(dur * SR)
    t = np.arange(n) / SR
    s = sum(np.sin(2 * np.pi * f * t + k) * a for k, (f, a) in
            enumerate([(1318.5, 1), (1975.5, 0.6), (2637, 0.35), (3951, 0.2)]))
    s *= np.exp(-t * 5) * (1 - np.exp(-t * 300))
    return _norm(np.stack([s, s * 0.9], 1)) * gain


def _norm(x):
    m = np.abs(x).max()
    return x / m if m > 0 else x


GEN = dict(whoosh=whoosh, swish=swish, pop=pop, thump=thump, shimmer=shimmer)


def build_sfx(events, duration):
    out = np.zeros((int((duration + 2) * SR), 2))
    for t, kind, kw in events:
        s = GEN[kind](**kw)
        i = int(t * SR)
        if i < 0:
            s, i = s[-i:], 0
        j = min(len(out), i + len(s))
        out[i:j] += s[: j - i]
    return out[: int(duration * SR)]


def write_wav(path, x):
    x = np.clip(x, -1, 1)
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((x * 32767).astype("<i2").tobytes())


def mix_project(pdir, video, out, sfx_db=-6.0, with_vo=True):
    from .render import load_scene
    scene = load_scene(os.path.join(pdir, "scene.py"))
    dur = scene.DURATION
    sfx_path = os.path.join(pdir, "sfx.wav")
    write_wav(sfx_path, build_sfx(getattr(scene, "SFX", []), dur) * 0.9)
    inputs = ["-i", video, "-i", sfx_path]
    filt = [f"[1:a]volume={sfx_db}dB[s]"]
    labels = ["[s]"]
    vo = getattr(scene, "VO", []) if with_vo else []
    for k, (f, t0) in enumerate(vo):
        inputs += ["-i", os.path.join(pdir, f)]
        idx = k + 2
        ms = int(t0 * 1000)
        filt.append(f"[{idx}:a]aresample={SR},aformat=channel_layouts=stereo,adelay={ms}|{ms}[v{k}]")
        labels.append(f"[v{k}]")
    music = getattr(scene, "MUSIC", None)
    if music:
        idx = len(vo) + 2
        inputs += ["-stream_loop", "-1", "-i", os.path.join(pdir, music[0])]
        filt.append(f"[{idx}:a]volume={music[1]}dB,afade=t=out:st={dur - 1.5}:d=1.5[m]")
        labels.append("[m]")
    filt.append("".join(labels) + f"amix=inputs={len(labels)}:normalize=0:duration=longest,"
                f"atrim=0:{dur},loudnorm=I=-14:TP=-1.0:LRA=11[a]")
    cmd = ["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", ";".join(filt),
           "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
           "-ar", str(SR), "-movflags", "+faststart", "-shortest", out]
    subprocess.run(cmd, check=True)
    print(f"[mix] -> {out}")
    return out
