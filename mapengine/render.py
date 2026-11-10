"""Parallel frame renderer -> ffmpeg (H.264), plus preview stills.

A scene module must define:
    W, H, FPS, DURATION
    setup() -> state            (called once per worker process)
    camera(t) -> View
    draw(frame, state)          (frame: mapengine.draw.Frame, basemap already drawn)
optional: TILE_PROVIDER ("s2" default | "nasa" | "esri"), MAX_LEVEL,
          ATTRIBUTION (True = imagery credit drawn on every frame | False | "text" | ["line", ...])
"""
import importlib.util
import math
import os
import subprocess
import sys
import time
from multiprocessing import get_context

import cairo

from . import tiles as T
from .draw import Frame
from .tiles import TileSource


def load_scene(path):
    spec = importlib.util.spec_from_file_location("scene", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["scene"] = mod
    spec.loader.exec_module(mod)
    # Globe() without an explicit provider follows the scene's map imagery
    T.ACTIVE_PROVIDER = T.provider_name(getattr(mod, "TILE_PROVIDER", None))
    return mod


def _tiles(scene):
    return TileSource(getattr(scene, "TILE_PROVIDER", None), getattr(scene, "MAX_LEVEL", 12))


def license_warning(scene):
    p = T.provider_name(getattr(scene, "TILE_PROVIDER", None))
    if not T.PROVIDERS[p]["commercial"]:
        print(f"[license] TILE_PROVIDER={p!r} ({T.PROVIDERS[p]['license']}) is for personal / "
              f"non-commercial use. For monetized videos use TILE_PROVIDER = \"s2\" or \"nasa\".", flush=True)


def credit_lines(scene):
    """Imagery credit drawn on the video (EOX's CC BY terms require it to be visible)."""
    a = getattr(scene, "ATTRIBUTION", True)
    if a is False or a is None:
        return []
    if isinstance(a, str):
        return [a]
    if isinstance(a, (list, tuple)):
        return list(a)
    used = T.USED_PROVIDERS or [T.provider_name(getattr(scene, "TILE_PROVIDER", None))]
    lines = []
    for p in used:
        lines += T.PROVIDERS[p]["credit"]
    return lines


def draw_credit(ctx, scene):
    from .text import draw_text
    lines = credit_lines(scene)
    # small, top-left: clear of Shorts/Reels/TikTok UI (bottom 25 %, right 10 %) and of titles (y 220+)
    for k, line in enumerate(lines):
        draw_text(ctx, line, 34, 44 + k * 27, size=21, anchor="left", alpha=0.78, weight="SemiBold",
                  tracking=0.01, shadow=0.9, shadow_blur=3)


def credits_report(scene_path):
    """Text for the video description: imagery + data credits and licence notes."""
    scene = load_scene(scene_path)
    _tiles(scene)
    scene.setup()  # registers the globe's imagery too
    out = ["Credits / Kaynaklar", ""]
    for p in T.USED_PROVIDERS:
        info = T.PROVIDERS[p]
        out.append(" ".join(info["credit"]) + f"  [{info['license']}]")
        if not info["commercial"]:
            out.append(f"  ! {p}: personal / non-commercial use only - check the provider's terms "
                       f"before monetizing (use TILE_PROVIDER = \"s2\" or \"nasa\").")
    out.append("Borders: Natural Earth (public domain)")
    out.append("Font: Montserrat (SIL Open Font License)")
    vo = [f for f, _ in getattr(scene, "VO", [])]
    if any("placeholder" in os.path.basename(f) for f in vo):
        out += ["", "! The voice is the PLACEHOLDER edge-tts voice (Microsoft neural voice, unofficial).",
                "  Replace it with your own recording (vo/voice.mp3 + make.py align) before publishing."]
    return "\n".join(out) + "\n"


def render_frame(scene, state, tiles, t, res=1.0):
    W, H = scene.W, scene.H
    pw, ph = int(round(W * res)), int(round(H * res))
    surf = cairo.ImageSurface(cairo.FORMAT_RGB24, pw, ph)
    ctx = cairo.Context(surf)
    ctx.scale(res, res)
    view = scene.camera(t)
    if getattr(scene, "basemap_visible", lambda t: True)(t):
        tiles.draw(ctx, view, W, H)
    fr = Frame(ctx, surf, view, W, H, t)
    scene.draw(fr, state)
    draw_credit(ctx, scene)
    surf.flush()
    return surf


def prefetch(scene, tiles):
    need = set()
    n = int(scene.DURATION * scene.FPS)
    vis = getattr(scene, "basemap_visible", lambda t: True)
    for i in range(0, n, 2):
        if vis(i / scene.FPS):
            need.update(tiles.tiles_for(scene.camera(i / scene.FPS), scene.W, scene.H))
    tiles.prefetch(need)


def _worker(args):
    scene_path, i0, i1, out, res, crf = args
    scene = load_scene(scene_path)
    state = scene.setup()
    tiles = _tiles(scene)
    pw, ph = int(round(scene.W * res)), int(round(scene.H * res))
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgra",
           "-s", f"{pw}x{ph}", "-r", str(scene.FPS), "-i", "-",
           "-c:v", "libx264", "-preset", "medium", "-crf", str(crf), "-threads", "2",
           "-pix_fmt", "yuv420p", "-x264-params", "keyint=60:min-keyint=60:scenecut=0",
           "-f", "mp4", out + ".tmp"]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for i in range(i0, i1):
        s = render_frame(scene, state, tiles, i / scene.FPS, res)
        stride = s.get_stride()
        data = s.get_data()
        if stride == pw * 4:
            p.stdin.write(bytes(data))
        else:
            mv = memoryview(data)
            for row in range(ph):
                p.stdin.write(mv[row * stride: row * stride + pw * 4])
    p.stdin.close()
    if p.wait() != 0:
        raise RuntimeError("ffmpeg failed for " + out)
    os.replace(out + ".tmp", out)
    return out


def render(scene_path, out, res=1.0, workers=4, crf=16, t0=0.0, t1=None, chunk_s=2.0):
    """Renders in small chunks (resumable: finished chunks are kept)."""
    scene = load_scene(scene_path)
    license_warning(scene)
    tiles = _tiles(scene)
    prefetch(scene, tiles)
    t1 = scene.DURATION if t1 is None else t1
    f0, f1 = int(t0 * scene.FPS), int(math.ceil(t1 * scene.FPS))
    n = f1 - f0
    chunk = max(1, int(chunk_s * scene.FPS))
    tmp = out + ".parts"
    os.makedirs(tmp, exist_ok=True)
    jobs, parts = [], []
    for k, a in enumerate(range(f0, f1, chunk)):
        b = min(f1, a + chunk)
        p_ = os.path.join(tmp, f"part{a:06d}_{b:06d}_{res}.mp4")
        parts.append(p_)
        if not os.path.exists(p_):
            jobs.append((scene_path, a, b, p_, res, crf))
    st = time.time()
    print(f"[render] {len(jobs)}/{len(parts)} chunks to render", flush=True)
    if jobs:
        import multiprocessing as _mp
        ctxname = "fork" if "fork" in _mp.get_all_start_methods() else "spawn"
        with get_context(ctxname).Pool(workers, maxtasksperchild=4) as pool:
            for i, _ in enumerate(pool.imap_unordered(_worker, jobs)):
                print(f"[render] chunk {i + 1}/{len(jobs)} done ({time.time() - st:.0f}s)", flush=True)
    lst = os.path.join(tmp, "list.txt")
    # ffmpeg reads the concat list as UTF-8 (paths like C:\Users\Özgür\... break with the
    # Windows default code page); forward slashes avoid backslash escaping on Windows.
    with open(lst, "w", encoding="utf-8") as f:
        for p_ in parts:
            ap_ = os.path.abspath(p_).replace("\\", "/").replace("'", "'\\''")
            f.write(f"file '{ap_}'\n")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst,
                    "-c", "copy", out], check=True)
    print(f"[render] {n} frames in {time.time() - st:.1f}s -> {out}", flush=True)
    return out


def stills(scene_path, times, outdir, res=0.5):
    scene = load_scene(scene_path)
    state = scene.setup()
    tiles = _tiles(scene)
    os.makedirs(outdir, exist_ok=True)
    paths = []
    for t in times:
        if getattr(scene, "basemap_visible", lambda t: True)(t):
            tiles.prefetch(tiles.tiles_for(scene.camera(t), scene.W, scene.H))
        s = render_frame(scene, state, tiles, t, res)
        p = os.path.join(outdir, f"still_{t:06.2f}.png")
        s.write_to_png(p)
        paths.append(p)
    return paths
