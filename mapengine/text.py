"""Text sprites (PIL -> cairo) with soft shadows + reveal animations, and flags."""
import math
import os
from functools import lru_cache

import cairo
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .geo import ROOT
from . import ease as E

FONTS = os.path.join(ROOT, "assets", "fonts")


def font_path(weight="ExtraBold"):
    return os.path.join(FONTS, f"Montserrat-{weight}.ttf")


def _to_cairo(im):
    a = np.asarray(im.convert("RGBA")).astype(np.float32)
    a[..., :3] *= a[..., 3:4] / 255.0  # premultiply
    bgra = a[..., [2, 1, 0, 3]].astype(np.uint8)
    h, w = bgra.shape[:2]
    stride = cairo.ImageSurface.format_stride_for_width(cairo.FORMAT_ARGB32, w)
    buf = np.zeros((h, stride), np.uint8)
    buf[:, :w * 4] = bgra.reshape(h, w * 4)
    data = bytearray(buf.tobytes())
    s = cairo.ImageSurface.create_for_data(data, cairo.FORMAT_ARGB32, w, h, stride)
    return s


@lru_cache(maxsize=96)
def text_sprite(text, size=90, weight="ExtraBold", color=(255, 255, 255), tracking=0.06,
                shadow=0.55, shadow_blur=14, stroke=0):
    """Returns (cairo_surface, w, h, pad). tracking = letter spacing in em."""
    f = ImageFont.truetype(font_path(weight), size)
    # measure with manual letter spacing
    adv = []
    for ch in text:
        adv.append(f.getlength(ch) + tracking * size)
    tw = int(sum(adv) - tracking * size) + 2
    asc, desc = f.getmetrics()
    th = asc + desc
    pad = shadow_blur * 3 + 8
    W, H = tw + 2 * pad, th + 2 * pad
    txt = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(txt)
    x = pad
    for ch, a in zip(text, adv):
        d.text((x, pad), ch, font=f, fill=255, stroke_width=stroke, stroke_fill=255)
        x += a
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    if shadow > 0:
        sh = txt.filter(ImageFilter.GaussianBlur(shadow_blur))
        sh = sh.point(lambda v: int(v * shadow))
        sl = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        sl.putalpha(sh)
        im = Image.alpha_composite(im, _offset(sl, 0, size // 18))
    col = Image.new("RGBA", (W, H), tuple(color) + (0,))
    col.putalpha(txt)
    im = Image.alpha_composite(im, col)
    return _to_cairo(im), W, H, pad


def _offset(im, dx, dy):
    out = Image.new("RGBA", im.size, (0, 0, 0, 0))
    out.paste(im, (dx, dy))
    return out


def draw_text(ctx, text, x, y, size=90, anchor="center", alpha=1.0, scale=1.0,
              reveal=1.0, rise=0.6, **kw):
    """Draw text centred at (x,y). reveal 0..1 = mask-slide-up animation."""
    if alpha <= 0.001 or reveal <= 0.001:
        return
    surf, W, H, pad = text_sprite(text, size, **kw)
    ctx.save()
    ctx.translate(x, y)
    scale = max(scale, 0.01)
    ctx.scale(scale, scale)
    ox = -W / 2 if anchor == "center" else (-pad if anchor == "left" else -W + pad)
    oy = -H / 2
    if reveal < 1.0:
        inner_h = H - 2 * pad
        ctx.rectangle(ox, oy, W, H - pad * 0.6)  # clip line just below baseline
        ctx.clip()
        oy += (1 - reveal) * inner_h * rise * 1.6
    ctx.set_source_surface(surf, ox, oy)
    ctx.paint_with_alpha(alpha * min(1.0, reveal * 1.5))
    ctx.restore()


def title_anim(t, t_in, t_out, dur_in=0.55, dur_out=0.4):
    """Returns (reveal, alpha, dy) for a title living in [t_in, t_out]."""
    if t < t_in or t > t_out:
        return 0.0, 0.0, 0.0
    rin = E.prog(t, t_in, t_in + dur_in, E.out_expo)
    rout = E.prog(t, t_out - dur_out, t_out, E.in_cubic)
    return rin, 1 - rout, -rout * 40


# ------------------------------------------------------------------- flags
def flag_turkey(ctx, x, y, w, h):
    """Official proportions (TS 2678): drawn as vectors, fitted to cover (x,y,w,h)."""
    G = max(h, w / 1.5)
    L = 1.5 * G
    ox, oy = x + (w - L) / 2, y + (h - G) / 2
    ctx.save()
    ctx.set_source_rgb(0.890, 0.039, 0.090)  # #E30A17
    ctx.rectangle(x, y, w, h)
    ctx.fill()
    ctx.translate(ox, oy)
    ctx.scale(G / 800.0, G / 800.0)  # SVG units, flag 1200x800
    ctx.set_source_rgb(1, 1, 1)
    ctx.arc(400, 400, 200, 0, 2 * math.pi)
    ctx.fill()
    ctx.set_source_rgb(0.890, 0.039, 0.090)
    ctx.arc(450, 400, 160, 0, 2 * math.pi)
    ctx.fill()
    # star: centre (583.334, 400), circumradius 100, one point to the hoist
    ctx.set_source_rgb(1, 1, 1)
    cx, cy, R = 583.334, 400, 100
    r = R * math.cos(math.radians(72)) / math.cos(math.radians(36))
    for i in range(10):
        a = math.pi + i * math.pi / 5
        rr = R if i % 2 == 0 else r
        px, py = cx + rr * math.cos(a), cy + rr * math.sin(a)
        (ctx.move_to if i == 0 else ctx.line_to)(px, py)
    ctx.close_path()
    ctx.fill()
    ctx.restore()


def flag_germany(ctx, x, y, w, h):
    for i, c in enumerate([(0, 0, 0), (0.867, 0, 0), (1, 0.808, 0)]):
        ctx.set_source_rgb(*c)
        ctx.rectangle(x, y + i * h / 3, w, h / 3 + 1)
        ctx.fill()
