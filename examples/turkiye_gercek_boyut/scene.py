"""Türkiye'nin gerçek boyutu - örnek Shorts (1080x1920, 60 fps).

Zamanlamalar seslendirmeye göre CUE sözlüğünde. Yeni bir seslendirme gelince
sadece bu değerleri (kelime zamanlarına göre) güncellemek yeterli.
"""
import math

import numpy as np

from mapengine import ease as E
from mapengine.camera import CameraPath, View
from mapengine.draw import scale_about, rings_bbox
from mapengine.geo import admin1, all_borders, country, merc, inv_merc
from mapengine.text import draw_text, title_anim, flag_turkey

W, H, FPS = 1080, 1920, 60
DURATION = 29.2
TILE_PROVIDER = "esri"
MAX_LEVEL = 10

RED = "#9e1010"
YELLOW = "#f7d548"

# ---- cue sheet (seconds) - derived from voiceover word timings ----------
CUE = dict(
    intro_fly=(0.0, 2.1),
    tr_title=(0.45, 4.15),
    tr_border=(0.45, 1.7),
    tr_fill=(1.2, 2.0),
    counter=(1.5, 2.7),
    flag_wipe=(2.55, 3.35),
    lift1=4.35,
    fly_de=(4.6, 6.6),
    de_title=(4.85, 9.95),
    de_fill=(5.6, 6.4),
    land_de=6.6,
    stat_x2=(7.3, 9.95),
    lift2=10.3,
    fly_tx=(10.45, 13.25),
    tx_fill=(12.6, 13.4),
    land_tx=13.25,
    tx_title=(13.9, 16.9),
    tx_sub=(14.75, 16.9),
    zoom_out=(17.3, 19.7),
    ghost=(19.75, 25.2),
    lift3=19.8,
    go_north=(20.15, 22.55),
    land_n=22.55,
    fly_home=(24.45, 26.85),
    land_home=26.85,
    end_title=(25.0, DURATION + 1),
    end_sub=(26.8, DURATION + 1),
)

# ---- geography ----------------------------------------------------------
_TUR = country("TUR", min_area=0.002)
_DEU = country("DEU", min_area=0.002)
_TEX = admin1("Texas", "USA", min_area=0.002)
NORTH = (-60.0, 71.0)


def _centre(shape):
    x, y = merc(*shape.centroid)
    return float(x), float(y)


def _view_on(lonlat, w_deg):
    x, y = merc(*lonlat)
    return View(float(x), float(y), w_deg / 360.0)


V_START = View.at(31, 43, 62)
V_TR = _view_on(_TUR.centroid, 23.5)
V_DE = _view_on(_DEU.centroid, 29.0)
V_TX = _view_on(_TEX.centroid, 25.0)
V_N = View.at(-74, 57, 88)

cam = CameraPath(V_START)
cam.fly(*CUE["intro_fly"], V_TR, ease=E.in_out_cubic)
cam.drift(CUE["intro_fly"][1], CUE["fly_de"][0], zoom=1.05)
cam.fly(*CUE["fly_de"], V_DE)
cam.drift(CUE["fly_de"][1], CUE["fly_tx"][0], zoom=1.05)
cam.fly(*CUE["fly_tx"], V_TX, rho=1.5)
cam.drift(CUE["fly_tx"][1], CUE["zoom_out"][0], zoom=1.04)
cam.move(*CUE["zoom_out"], V_N, ease=E.in_out_quint)
cam.drift(CUE["zoom_out"][1], CUE["fly_home"][0], zoom=1.04)
V_HOME = V_TR.zoomed(1.03)
cam.fly(*CUE["fly_home"], V_HOME, ease=E.in_out_cubic, rho=1.2)
cam.drift(CUE["fly_home"][1], DURATION, zoom=1.06)


def camera(t):
    return cam(t)


# ---- where is Türkiye (lon/lat of its centroid) at time t ----------------
def _follow(t):
    v = cam(t)
    return v.lonlat()


def turkey_pos(t):
    fd, ft, gn, fh = CUE["fly_de"], CUE["fly_tx"], CUE["go_north"], CUE["fly_home"]
    if t <= fd[0]:
        return _TUR.centroid
    if t <= fd[1]:
        return _follow(t)
    if t <= ft[0]:
        return _DEU.centroid
    if t <= ft[1]:
        return _follow(t)
    if t <= gn[0]:
        return _TEX.centroid
    if t <= gn[1]:
        p = E.prog(t, *gn, E.in_out_cubic)
        a, b = _TEX.centroid, NORTH
        return (a[0] + (b[0] - a[0]) * p, a[1] + (b[1] - a[1]) * p)
    if t <= fh[0]:
        return NORTH
    if t <= fh[1]:
        # follow the camera with a decaying offset so it ends exactly home
        p = E.prog(t, *fh, E.in_out_cubic)
        v0, v = cam(fh[0]), cam(t)
        nx, ny = merc(*NORTH)
        ox, oy = float(nx) - v0.cx, float(ny) - v0.cy
        k = 1 - E.smoother(E.prog(t, *fh))
        lo, la = inv_merc(v.cx + ox * k, v.cy + oy * k)
        return float(lo), float(la)
    return _TUR.centroid


def lift_amount(t):
    """0 = resting on the map, 1 = picked up."""
    def bump(t_up, t_down):
        up = E.prog(t, t_up, t_up + 0.35, E.out_cubic)
        down = E.prog(t, t_down - 0.1, t_down + 0.25, E.in_cubic)
        return up * (1 - down)
    return max(bump(CUE["lift1"], CUE["land_de"]),
               bump(CUE["lift2"], CUE["land_tx"]),
               bump(CUE["lift3"], CUE["land_n"]),
               bump(CUE["fly_home"][0] - 0.05, CUE["land_home"]))


def land_ripple(t):
    for key in ("land_de", "land_tx", "land_n", "land_home"):
        t0 = CUE[key] + 0.12
        if t0 <= t <= t0 + 0.9:
            return (t - t0) / 0.9
    return None


# ---- per-worker state ------------------------------------------------------
def setup():
    return dict(borders=all_borders())


def fmt_int(n):
    return f"{n:,}".replace(",", ".")


def draw(fr, st):
    t = fr.t
    c = fr.ctx
    fr.grade(darken=0.2, desat=0.2)
    fr.borders(st["borders"], alpha=0.13)

    # graticule appears when we talk about map distortion
    g = E.window(t, CUE["zoom_out"][0] + 0.6, CUE["fly_home"][0] + 1.0, 0.8, 0.8)
    fr.graticule(alpha=0.16 * g, step=10)

    # ---- comparison targets (yellow)
    for shape, key, out in ((_DEU, "de_fill", CUE["fly_tx"][0] + 0.6),
                            (_TEX, "tx_fill", CUE["zoom_out"][0] + 1.2)):
        t_in, t_full = CUE[key]
        a = E.window(t, t_in, out, t_full - t_in, 0.6)
        if a > 0:
            rings = fr.screen_rings(shape.merc_rings)
            fr.fill_tint(rings, YELLOW, a, solid=0.55)

    # ---- ghost outline: Türkiye's true footprint left at Texas
    ga = E.window(t, CUE["ghost"][0], CUE["ghost"][1], 0.5, 0.6)
    if ga > 0:
        ghost = fr.screen_rings(_TUR.moved_to(*_TEX.centroid))
        fr.fill_solid(ghost, "#ffffff", 0.16 * ga)
        fr.stroke(ghost, 3.5, "#ffffff", 0.95 * ga, dash=[12, 9])

    # ---- Türkiye
    lon, lat = turkey_pos(t)
    lift = lift_amount(t)
    tr_m = _TUR.moved_to(lon, lat) if (lon, lat) != _TUR.centroid else _TUR.merc_rings
    base = fr.screen_rings(tr_m)
    if base:
        x0, y0, x1, y1 = rings_bbox(base)
        cx, cy = fr.pt(*merc(lon, lat))
        cx, cy = float(cx), float(cy)
        k = 1 + 0.035 * lift
        rings = [scale_about(cx, cy - 10 * lift, k)(s) for s in base] if lift > 0 else base
        x0, y0, x1, y1 = rings_bbox(rings)

        b0, b1 = CUE["tr_border"]
        border_p = E.prog(t, b0, b1, E.in_out_cubic)
        fill_a = E.prog(t, *CUE["tr_fill"], E.smooth)

        # shadow (stronger when lifted)
        if fill_a > 0:
            fr.shadow(rings, dy=8 + 26 * lift, blur=10 + 22 * lift, alpha=(0.35 + 0.25 * lift) * fill_a)

        # red tinted texture first, then the flag wipes in
        wipe = E.prog(t, *CUE["flag_wipe"], E.in_out_cubic)
        if wipe < 1:
            fr.fill_tint(rings, RED, fill_a, solid=0.5)
        comparing = max(E.window(t, CUE["de_fill"][0], CUE["fly_tx"][0] + 0.3, 0.8, 0.5),
                        E.window(t, CUE["tx_fill"][0], CUE["lift3"] + 0.3, 0.8, 0.5))
        flag_alpha = 1 - 0.3 * comparing
        if wipe > 0:
            R = math.hypot(x1 - x0, y1 - y0) * 0.6 * wipe
            fx, fy = (x0 + x1) / 2, (y0 + y1) / 2
            fr.fill_with(rings, lambda cc: flag_turkey(cc, x0, y0, x1 - x0, y1 - y0),
                         flag_alpha, clip_circle=None if wipe >= 1 else (fx, fy, R))
            # soft top-light shading gives the flat flag some depth
            def shade(cc, y0=y0, y1=y1):
                import cairo
                g = cairo.LinearGradient(0, y0, 0, y1)
                g.add_color_stop_rgba(0, 1, 1, 1, 0.10)
                g.add_color_stop_rgba(1, 0, 0, 0, 0.22)
                cc.set_source(g)
                cc.paint()
            fr.fill_with(rings, shade, flag_alpha * wipe)
        fr.glow_stroke(rings, 3.2, "#ffffff", 1.0, progress=border_p, glow=10, glow_alpha=0.35)

        # yellow outline of the target drawn ON TOP so the overlap reads
        for shape, key, out in ((_DEU, "de_fill", CUE["fly_tx"][0] + 0.6),
                                (_TEX, "tx_fill", CUE["zoom_out"][0] + 1.2)):
            a = E.window(t, CUE[key][0], out, 0.8, 0.6)
            if a > 0:
                fr.stroke(fr.screen_rings(shape.merc_rings), 3.0, YELLOW, a)

        rp = land_ripple(t)
        if rp is not None:
            rr = [scale_about(cx, cy, 1 + 0.22 * E.out_cubic(rp))(s) for s in rings]
            fr.stroke(rr, 3 * (1 - rp) + 0.5, "#ffffff", 0.7 * (1 - rp))

    fr.vignette(0.5)

    # ---- titles (minimal)
    TY, SY = 300, 400
    for txt, key in (("TÜRKİYE", "tr_title"), ("ALMANYA", "de_title"),
                     ("TEKSAS", "tx_title"), ("TÜRKİYE", "end_title")):
        rv, al, dy = title_anim(t, *CUE[key])
        draw_text(c, txt, W / 2, TY + dy, size=104, alpha=al, reveal=rv, tracking=0.12)

    # counters / stats
    rv, al, dy = title_anim(t, CUE["counter"][0], CUE["tr_title"][1])
    if al > 0:
        n = int(783562 * E.prog(t, *CUE["counter"], E.out_expo))
        draw_text(c, f"{fmt_int(n)} km²", W / 2, SY + dy, size=54, weight="SemiBold",
                  alpha=al, reveal=rv, tracking=0.04, color=(255, 255, 255))
    rv, al, dy = title_anim(t, *CUE["stat_x2"])
    if al > 0:
        pop = E.out_back(E.prog(t, CUE["stat_x2"][0], CUE["stat_x2"][0] + 0.5), 2.2)
        draw_text(c, "×2,2", W / 2, SY + 40 + dy, size=150, weight="Black", alpha=al,
                  scale=0.6 + 0.4 * pop, color=(247, 213, 72), tracking=0.02)
    rv, al, dy = title_anim(t, *CUE["tx_sub"])
    draw_text(c, "695.662 km²", W / 2, SY + dy, size=54, weight="SemiBold", alpha=al,
              reveal=rv, tracking=0.04, color=(247, 213, 72))
    rv, al, dy = title_anim(t, *CUE["end_sub"])
    draw_text(c, "783.562 km²", W / 2, SY + dy, size=54, weight="SemiBold", alpha=al,
              reveal=rv, tracking=0.04)

    # fade in from black at start, short fade at end
    fade = max(1 - E.prog(t, 0, 0.35), E.prog(t, DURATION - 0.35, DURATION))
    if fade > 0:
        c.set_source_rgba(0, 0, 0, fade)
        c.paint()


# ---- audio ---------------------------------------------------------------
VO = [("vo/l1.mp3", 0.30), ("vo/l2.mp3", 4.30), ("vo/l3.mp3", 10.30),
      ("vo/l4.mp3", 17.20), ("vo/l5.mp3", 24.40)]


def _sfx():
    ev = []
    def fly(key, gain=0.55):
        a, b = CUE[key]
        ev.append((a - 0.1, "whoosh", dict(dur=(b - a) + 0.3, gain=gain)))
    fly("intro_fly", 0.45)
    fly("fly_de")
    fly("fly_tx", 0.65)
    fly("zoom_out", 0.35)
    fly("go_north", 0.45)
    fly("fly_home", 0.6)
    for k in ("land_de", "land_tx", "land_n", "land_home"):
        ev.append((CUE[k] - 0.02, "thump", dict(gain=0.5)))
    for k in ("tr_title", "de_title", "tx_title", "end_title"):
        ev.append((CUE[k][0], "swish", dict(gain=0.22)))
    ev.append((CUE["flag_wipe"][0] + 0.1, "shimmer", dict(gain=0.2)))
    ev.append((CUE["stat_x2"][0], "pop", dict(gain=0.5)))
    ev.append((CUE["tr_fill"][0], "pop", dict(gain=0.3, f0=300, f1=120)))
    return ev


SFX = _sfx()
