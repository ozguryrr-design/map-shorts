"""Parallel frame renderer -> ffmpeg (H.264), plus preview stills.

A scene module must define:
    W, H, FPS, DURATION
    setup() -> state            (called once per worker process)
    camera(t) -> View
    draw(frame, state)          (frame: mapengine.draw.Frame, basemap already drawn)
optional: TILE_PROVIDER, MAX_LEVEL
"""
import importlib.util
import math
import os
import subprocess
import sys
import time
from multiprocessing import get_context

import cairo

from .draw import Frame
from .tiles import TileSource


def load_scene(path):
    spec = importlib.util.spec_from_file_location("scene", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["scene"] = mod
    spec.loader.exec_module(mod)
    return mod


def _tiles(scene):
    return TileSource(getattr(scene, "TILE_PROVIDER", "esri"), getattr(scene, "MAX_LEVEL", 12))


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
