"""High-level, reusable effects for map stories.

Everything here works in "map space" (lon/lat or mercator) and handles the
unwrapped-longitude world copies automatically, so scenes stay short.
"""
import math
import os
import urllib.request

import cairo
import numpy as np
from PIL import Image

from . import ease as E
from .draw import hex2rgb
from .geo import ROOT, merc
from .text import draw_text, title_anim

GOLD = (1.0, 0.82, 0.36)
WHITE = (1.0, 1.0, 1.0)
ACCENT_RGB255 = (255, 210, 92)


def _rgb(c):
    return hex2rgb(c) if isinstance(c, str) else c


# ------------------------------------------------------------------ positions
def ll_screen(fr, lon, lat):
    """lon/lat -> screen xy, using the world copy nearest to the camera."""
    x, y = merc(lon, lat)
    k = fr.nearest_copy(float(x))
    return fr.pt(float(x) + k, float(y))


def wrap_rings(fr, merc_rings):
    """Shift a shape's mercator rings to the world copy nearest the camera."""
    ref = float(np.mean([r[:, 0].mean() for r in merc_rings]))
    k = fr.nearest_copy(ref)
    return [r + (k, 0) for r in merc_rings] if k else merc_rings


# ------------------------------------------------------------------ shapes
def highlight(fr, shape, color="#c8102e", alpha=1.0, border=1.0, solid=0.4,
              border_color="#ffffff", border_w=2.6, glow=True, rings=None):
    """Tinted-texture country/region fill + (draw-on) glowing border.
    border: 0..1 draw-on progress of the outline."""
    if alpha <= 0:
        return
    sr = fr.screen_rings(rings if rings is not None else wrap_rings(fr, shape.merc_rings))
    fr.fill_tint(sr, color, alpha, solid=solid)
    if border > 0:
        if glow:
            fr.glow_stroke(sr, border_w, border_color, alpha, progress=border, glow=9, glow_alpha=0.3)
        else:
            fr.stroke(sr, border_w, border_color, alpha, progress=border)
    return sr


# ------------------------------------------------------------------ lines
def polyline(fr, merc_pts, color=GOLD, width=4.2, alpha=1.0, glow=True, copies=True, dash=None):
    """Glowing polyline in mercator coords (unwrapped x allowed)."""
    if alpha <= 0 or len(merc_pts) < 2:
        return
    c = fr.ctx
    col = _rgb(color)
    for k in (fr.world_copies() if copies else [0]):
        s = fr.to_screen(merc_pts + (k, 0)) if k else fr.to_screen(merc_pts)
        if s[:, 0].max() < -40 or s[:, 0].min() > fr.W + 40:
            continue
        c.new_path()
        c.move_to(*s[0])
        for x, y in s[1:]:
            c.line_to(x, y)
        c.set_line_cap(cairo.LINE_CAP_ROUND)
        c.set_line_join(cairo.LINE_JOIN_ROUND)
        if dash:
            c.set_dash(dash)
        layers = ((width * 3.3, 0.10), (width * 1.9, 0.22), (width, 1.0)) if glow else ((width, 1.0),)
        for wdt, a in layers:
            c.set_source_rgba(*col, a * alpha)
            c.set_line_width(wdt)
            c.stroke_preserve()
        c.set_dash([])
        c.new_path()


def route_progress(fr, route, d, color=GOLD, width=4.2, alpha=1.0, d0=0.0):
    """Draw a mapengine.route.Route from km d0 up to km d."""
    polyline(fr, route.merc_upto(d, d0), color, width, alpha)


def arc_points(a_ll, b_ll, bend=0.22, n=80):
    """Curved arc (quadratic bezier in mercator) from a to b. bend>0 bends left."""
    ax, ay = merc(*a_ll)
    bx, by = merc(*b_ll)
    a = np.array([float(ax), float(ay)])
    b = np.array([float(bx), float(by)])
    m = (a + b) / 2
    d = b - a
    nrm = np.array([d[1], -d[0]])
    ctrl = m + nrm * bend
    t = np.linspace(0, 1, n)[:, None]
    return (1 - t) ** 2 * a + 2 * (1 - t) * t * ctrl + t ** 2 * b


def arc(fr, a_ll, b_ll, progress=1.0, color=GOLD, width=5, alpha=1.0, bend=0.22,
        arrow=True, dash=None, head=22):
    """Animated arrow arc between two lon/lat points (migrations, trade, attacks...)."""
    if progress <= 0 or alpha <= 0:
        return
    pts = arc_points(a_ll, b_ll, bend)
    k = fr.nearest_copy(float(pts[:, 0].mean()))
    pts = pts + (k, 0)
    n = max(2, int(len(pts) * min(1.0, progress)))
    part = pts[:n]
    polyline(fr, part, color, width, alpha, copies=False, dash=dash)
    if arrow and n >= 2:
        s = fr.to_screen(part[-2:])
        dx, dy = s[1] - s[0]
        ang = math.atan2(dy, dx)
        c = fr.ctx
        c.save()
        c.translate(*s[1])
        c.rotate(ang)
        c.move_to(head * 0.35, 0)
        c.line_to(-head * 0.75, -head * 0.55)
        c.line_to(-head * 0.45, 0)
        c.line_to(-head * 0.75, head * 0.55)
        c.close_path()
        c.set_source_rgba(*_rgb(color), alpha)
        c.fill()
        c.restore()


# ------------------------------------------------------------------ markers
def dot(c, x, y, r=6, color=WHITE, alpha=1.0):
    c.set_source_rgba(*_rgb(color), alpha)
    c.arc(x, y, r, 0, 6.283)
    c.fill()


def cross_marker(c, x, y, t, t0, color=(0.75, 0.05, 0.05)):
    """Death / disaster marker: red disc with a white latin cross + pulses."""
    if t < t0:
        return
    p = max(0.01, E.out_back(min(1, (t - t0) / 0.4), 2.2))
    for k in range(2):
        ph = ((t - t0) * 0.8 + k * 0.5) % 1.0
        c.set_source_rgba(0.9, 0.12, 0.12, 0.8 * (1 - ph))
        c.set_line_width(3)
        c.arc(x, y, 18 + 50 * ph, 0, 6.283)
        c.stroke()
    c.set_source_rgba(*color, 0.95)
    c.arc(x, y, 22 * p, 0, 6.283)
    c.fill()
    c.set_source_rgb(1, 1, 1)
    s = 13 * p
    c.rectangle(x - s * 0.17, y - s, s * 0.34, s * 2)
    c.rectangle(x - s * 0.62, y - s * 0.48, s * 1.24, s * 0.34)
    c.fill()


def burst_marker(c, x, y, t, t0, color=(1.0, 0.45, 0.1)):
    """Battle / explosion marker: spiky star + pulse."""
    if t < t0:
        return
    p = max(0.01, E.out_back(min(1, (t - t0) / 0.35), 2.4))
    ph = ((t - t0) * 0.9) % 1.0
    c.set_source_rgba(*color, 0.7 * (1 - ph))
    c.set_line_width(3)
    c.arc(x, y, 20 + 46 * ph, 0, 6.283)
    c.stroke()
    R, r = 24 * p, 11 * p
    for i in range(16):
        a = i * math.pi / 8 + (t - t0) * 0.6
        rr = R if i % 2 == 0 else r
        (c.move_to if i == 0 else c.line_to)(x + rr * math.cos(a), y + rr * math.sin(a))
    c.close_path()
    c.set_source_rgba(*color, 1)
    c.fill_preserve()
    c.set_source_rgba(1, 1, 1, 0.9)
    c.set_line_width(2)
    c.stroke()


def rrect(c, x, y, w_, h_, r):
    c.new_sub_path()
    c.arc(x + w_ - r, y + r, r, -math.pi / 2, 0)
    c.arc(x + w_ - r, y + h_ - r, r, 0, math.pi / 2)
    c.arc(x + r, y + h_ - r, r, math.pi / 2, math.pi)
    c.arc(x + r, y + r, r, math.pi, 1.5 * math.pi)
    c.close_path()


# ------------------------------------------------------------------ titles
def title(c, t, text, t_in, t_out, x=540, y=300, size=110, weight="Black", tracking=0.1,
          color=(255, 255, 255)):
    rv, al, dy = title_anim(t, t_in, t_out)
    draw_text(c, text, x, y + dy, size=size, weight=weight, alpha=al, reveal=rv,
              tracking=tracking, color=color)


def title_sub(c, t, big, small, t_in, t_out, x=540, y=300, small_above=False, accent=False):
    """Big title + small line (above or below)."""
    rv, al, dy = title_anim(t, t_in, t_out)
    if al <= 0:
        return
    rv2, _, _ = title_anim(t, t_in + 0.12, t_out)
    if small_above:
        draw_text(c, small, x, y - 62 + dy, size=46, weight="SemiBold", alpha=al, reveal=rv, tracking=0.18)
        draw_text(c, big, x, y + 40 + dy, size=150, weight="Black", alpha=al, reveal=rv2, tracking=0.04)
    else:
        draw_text(c, big, x, y + dy, size=110, weight="Black", alpha=al, reveal=rv, tracking=0.1)
        draw_text(c, small, x, y + 100 + dy, size=56, weight="ExtraBold", alpha=al, reveal=rv2,
                  tracking=0.06, color=ACCENT_RGB255 if accent else (255, 255, 255))


def date_title(c, t, small, big, t_in, t_out, x=540, y=300):
    """'20 EYLÜL' small + '1519' big."""
    title_sub(c, t, big, small, t_in, t_out, x, y, small_above=True)


def fmt_int(n, sep="."):
    return f"{int(n):,}".replace(",", sep)


def counter(c, t, t0, t1, v0, v1, x=540, y=330, size=170, suffix="", prefix="", t_out=None,
            ease=E.out_expo, color=(255, 255, 255), end_color=ACCENT_RGB255, fmt=fmt_int):
    """Animated number (counts v0 -> v1 during [t0,t1])."""
    t_out = t_out if t_out is not None else t1 + 2.5
    rv, al, dy = title_anim(t, t0 - 0.2, t_out)
    if al <= 0:
        return
    q = E.prog(t, t0, t1, ease)
    v = v0 + (v1 - v0) * q
    col = end_color if q >= 1 and end_color else color
    pop = 1 + 0.07 * math.sin(math.pi * E.prog(t, t1, t1 + 0.35))
    draw_text(c, f"{prefix}{fmt(v)}{suffix}", x, y + dy, size=size, weight="Black", alpha=al,
              scale=pop, color=col, tracking=0.02)


def map_label(fr, text, lon, lat, t, t_in, t_out, dy=-60, size=40, color=(255, 255, 255)):
    """Small label pinned to a geographic point."""
    rv, al, ddy = title_anim(t, t_in, t_out)
    if al <= 0:
        return
    x, y = ll_screen(fr, lon, lat)
    draw_text(fr.ctx, text, x, y + dy + ddy, size=size, weight="ExtraBold", alpha=al, reveal=rv,
              tracking=0.1, color=color)


def calendar(c, t, t_in, t_flip, month, a, b, x=540, y=300, t_out=None):
    """Calendar tile that pops in and flips its number from a to b at t_flip."""
    if t < t_in or (t_out is not None and t > t_out):
        return
    p = max(0.02, E.out_back(E.prog(t, t_in, t_in + 0.5), 1.6))
    al = E.prog(t, t_in, t_in + 0.25)
    if t_out is not None:
        al *= 1 - E.prog(t, t_out - 0.3, t_out)
    wc, hc = 230, 250
    c.save()
    c.translate(x, y)
    c.scale(p, p)
    c.push_group()
    c.set_source_rgba(0, 0, 0, 0.35)
    rrect(c, -wc / 2 + 6, -hc / 2 + 12, wc, hc, 26)
    c.fill()
    c.set_source_rgb(0.98, 0.97, 0.94)
    rrect(c, -wc / 2, -hc / 2, wc, hc, 26)
    c.fill()
    c.save()
    rrect(c, -wc / 2, -hc / 2, wc, hc, 26)
    c.clip()
    c.set_source_rgb(*hex2rgb("#c8102e"))
    c.rectangle(-wc / 2, -hc / 2, wc, 66)
    c.fill()
    c.restore()
    for rx in (-50, 50):
        c.set_source_rgb(0.25, 0.25, 0.28)
        rrect(c, rx - 7, -hc / 2 - 16, 14, 34, 7)
        c.fill()
    draw_text(c, month, 0, -hc / 2 + 34, size=34, weight="ExtraBold", shadow=0, tracking=0.12)
    f = E.prog(t, t_flip, t_flip + 0.45, E.in_out_cubic)
    num, sy = (str(a), 1 - 2 * f) if f < 0.5 else (str(b), 2 * f - 1)
    c.save()
    c.translate(0, 38)
    c.scale(1, max(0.02, sy))
    draw_text(c, num, 0, 0, size=128, weight="Black", color=(30, 30, 34), shadow=0, tracking=0.0)
    c.restore()
    c.pop_group_to_source()
    c.paint_with_alpha(al)
    c.restore()


# ------------------------------------------------------------------ flags
_FLAGS = {}


def flag(iso2):
    """Returns painter(ctx, x, y, w, h) that covers the box with a country flag
    (PNG from flagcdn.com, cached in data/flags). iso2: 'tr', 'de', 'us'..."""
    iso2 = iso2.lower()
    if iso2 in _FLAGS:
        return _FLAGS[iso2]
    d = os.path.join(ROOT, "data", "flags")
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, f"{iso2}.png")
    if not os.path.exists(p):
        req = urllib.request.Request(f"https://flagcdn.com/w1280/{iso2}.png",
                                     headers={"User-Agent": "mapengine/1.0"})
        with urllib.request.urlopen(req, timeout=20) as r, open(p, "wb") as f:
            f.write(r.read())
    im = Image.open(p).convert("RGBA")
    a = np.asarray(im).astype(np.float32)
    a[..., :3] *= a[..., 3:4] / 255.0
    bgra = np.ascontiguousarray(a[..., [2, 1, 0, 3]].astype(np.uint8))
    h, w = bgra.shape[:2]
    surf = cairo.ImageSurface.create_for_data(bytearray(bgra.tobytes()), cairo.FORMAT_ARGB32, w, h, w * 4)

    def painter(ctx, x, y, bw, bh):
        s = max(bw / w, bh / h)
        ctx.save()
        ctx.translate(x + (bw - w * s) / 2, y + (bh - h * s) / 2)
        ctx.scale(s, s)
        pat = cairo.SurfacePattern(surf)
        pat.set_filter(cairo.FILTER_GOOD)
        ctx.set_source(pat)
        ctx.paint()
        ctx.restore()

    _FLAGS[iso2] = painter
    return painter


def flag_fill(fr, screen_rings, iso2_or_painter, alpha=1.0, wipe=1.0, shade=True):
    """Fill a shape with a flag; wipe 0..1 = circular reveal from the centre."""
    if alpha <= 0 or not screen_rings or wipe <= 0:
        return
    painter = flag(iso2_or_painter) if isinstance(iso2_or_painter, str) else iso2_or_painter
    a = np.concatenate(screen_rings)
    x0, y0 = a.min(0)
    x1, y1 = a.max(0)
    R = math.hypot(x1 - x0, y1 - y0) * 0.6 * wipe
    clip = None if wipe >= 1 else ((x0 + x1) / 2, (y0 + y1) / 2, R)
    fr.fill_with(screen_rings, lambda cc: painter(cc, x0, y0, x1 - x0, y1 - y0), alpha, clip_circle=clip)
    if shade:
        def sh(cc):
            g = cairo.LinearGradient(0, y0, 0, y1)
            g.add_color_stop_rgba(0, 1, 1, 1, 0.10)
            g.add_color_stop_rgba(1, 0, 0, 0, 0.22)
            cc.set_source(g)
            cc.paint()
        fr.fill_with(screen_rings, sh, alpha * wipe, clip_circle=clip)
