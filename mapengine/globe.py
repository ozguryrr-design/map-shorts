"""Orthographic 3D globe with the satellite texture (numpy ray-mapping)."""
import math
import os

import cairo
import numpy as np
from PIL import Image

from .geo import CACHE, merc
from .tiles import TileSource, TS, provider_name

_TEX = {}


def texture(provider=None, level=4):
    """Equirectangular texture (H=2^L*256/2*... ) built once from map tiles."""
    provider = provider_name(provider)
    key = (provider, level)
    if key in _TEX:
        return _TEX[key]
    path = os.path.join(CACHE, f"globe_{provider}_{level}.jpg")
    if not os.path.exists(path):
        ts = TileSource(provider)
        n = 2 ** level
        ts.prefetch([(level, x, y) for x in range(n) for y in range(n)])
        mos = np.zeros((n * TS, n * TS, 3), np.uint8)
        for x in range(n):
            for y in range(n):
                im = Image.open(ts.path(level, x, y)).convert("RGB").resize((TS, TS))
                mos[y * TS:(y + 1) * TS, x * TS:(x + 1) * TS] = np.asarray(im)
        TW, TH = n * TS, n * TS // 2
        lat = 90 - (np.arange(TH) + 0.5) * 180 / TH
        _, my = merc(np.zeros_like(lat), lat)
        fy = np.clip(my * n * TS - 0.5, 0, n * TS - 1.001)
        i0 = fy.astype(int)
        w = (fy - i0)[:, None, None]
        eq = mos[i0] * (1 - w) + mos[np.minimum(i0 + 1, n * TS - 1)] * w
        Image.fromarray(eq.astype(np.uint8)).save(path, quality=93)
    tex = np.asarray(Image.open(path).convert("RGB"))  # uint8, gathered per pixel
    _TEX[key] = tex
    return tex


def _stars(W, H, n=260, seed=3):
    r = np.random.default_rng(seed)
    return r.uniform(0, W, n), r.uniform(0, H, n), r.uniform(0.3, 1.0, n), r.uniform(0, 6.28, n)


class Globe:
    def __init__(self, W, H, provider=None, level=4):
        """provider=None -> the scene's TILE_PROVIDER (so the globe and the map match)."""
        self.W, self.H = W, H
        self.tex = texture(provider, level)
        self.TH, self.TW = self.tex.shape[:2]
        self.stars = _stars(W, H)
        L = np.array([-0.45, 0.55, 0.70])
        self.light = L / np.linalg.norm(L)

    # ------------------------------------------------------------ projection
    def project(self, lon, lat, st):
        """lon/lat arrays -> screen x, y, depth z (z>0 visible)."""
        lon0, lat0, R, cx, cy = st
        lam = np.radians(np.asarray(lon) - lon0)
        phi = np.radians(np.asarray(lat))
        p0 = math.radians(lat0)
        cphi = np.cos(phi)
        x = cphi * np.sin(lam)
        y = math.cos(p0) * np.sin(phi) - math.sin(p0) * cphi * np.cos(lam)
        z = math.sin(p0) * np.sin(phi) + math.cos(p0) * cphi * np.cos(lam)
        return cx + R * x, cy - R * y, z

    # ------------------------------------------------------------ drawing
    def draw_space(self, ctx, t, alpha=1.0):
        W, H = self.W, self.H
        g = cairo.RadialGradient(W / 2, H * 0.45, 0, W / 2, H * 0.45, H * 0.75)
        g.add_color_stop_rgb(0, 0.035, 0.07, 0.13)
        g.add_color_stop_rgb(1, 0.005, 0.01, 0.025)
        ctx.set_source(g)
        ctx.paint_with_alpha(alpha)
        xs, ys, b, ph = self.stars
        for x, y, bb, p in zip(xs, ys, b, ph):
            a = alpha * bb * (0.65 + 0.35 * math.sin(t * 1.7 + p))
            ctx.set_source_rgba(1, 1, 1, a * 0.8)
            ctx.arc(x, y, 1.1 + bb * 0.9, 0, 6.283)
            ctx.fill()

    def draw(self, ctx, st, alpha=1.0):
        lon0, lat0, R, cx, cy = st
        W, H = self.W, self.H
        x0, x1 = max(0, int(cx - R) - 1), min(W, int(cx + R) + 2)
        y0, y1 = max(0, int(cy - R) - 1), min(H, int(cy + R) + 2)
        if x1 <= x0 or y1 <= y0:
            return
        X = ((np.arange(x0, x1, dtype=np.float32) + 0.5 - cx) / R)[None, :]
        Y = ((cy - (np.arange(y0, y1, dtype=np.float32) + 0.5)) / R)[:, None]
        rho2 = X * X + Y * Y
        inside = rho2 < 1.0
        Z = np.sqrt(np.clip(1.0 - rho2, 0, 1))
        p0 = math.radians(lat0)
        sp, cp = math.sin(p0), math.cos(p0)
        Xb = np.broadcast_to(X, Z.shape)
        lat = np.arcsin(np.clip(Z * sp + Y * cp, -1, 1))
        lon = np.arctan2(Xb, Z * cp - Y * sp) + math.radians(lon0)
        u = (lon / (2 * math.pi) + 0.5) % 1.0 * self.TW - 0.5
        v = np.clip((0.5 - lat / math.pi) * self.TH - 0.5, 0, self.TH - 1.001)
        i0 = np.floor(u).astype(np.int32)
        j0 = v.astype(np.int32)
        fu = (u - i0)[..., None]
        fv = (v - j0)[..., None]
        i0 %= self.TW
        i1 = (i0 + 1) % self.TW
        j1 = np.minimum(j0 + 1, self.TH - 1)
        T = self.tex
        fu = fu.astype(np.float32)
        fv = fv.astype(np.float32)
        col = T[j0, i0] * ((1 - fu) * (1 - fv))
        col += T[j0, i1] * (fu * (1 - fv))
        col += T[j1, i0] * ((1 - fu) * fv)
        col += T[j1, i1] * (fu * fv)
        Lx, Ly, Lz = self.light
        d = np.clip(Xb * Lx + Y * Ly + Z * Lz, 0, 1)
        shade = 0.30 + 0.85 * d ** 0.8
        col *= shade[..., None]
        col[~inside] = 0
        rgb = np.clip(col, 0, 255).astype(np.uint8)
        h, w = rgb.shape[:2]
        stride = cairo.ImageSurface.format_stride_for_width(cairo.FORMAT_RGB24, w)
        buf = np.zeros((h, stride // 4, 4), np.uint8)
        buf[:, :w, 0] = rgb[..., 2]
        buf[:, :w, 1] = rgb[..., 1]
        buf[:, :w, 2] = rgb[..., 0]
        surf = cairo.ImageSurface.create_for_data(bytearray(buf.tobytes()), cairo.FORMAT_RGB24, w, h, stride)
        ctx.save()
        ctx.arc(cx, cy, R, 0, 2 * math.pi)
        ctx.clip()
        ctx.set_source_surface(surf, x0, y0)
        ctx.paint_with_alpha(alpha)
        # inner atmospheric rim
        g = cairo.RadialGradient(cx, cy, R * 0.80, cx, cy, R)
        g.add_color_stop_rgba(0, 0.45, 0.7, 1.0, 0)
        g.add_color_stop_rgba(1, 0.45, 0.7, 1.0, 0.35 * alpha)
        ctx.set_source(g)
        ctx.paint()
        ctx.restore()
        # outer glow
        g = cairo.RadialGradient(cx, cy, R * 0.99, cx, cy, R * 1.10)
        g.add_color_stop_rgba(0, 0.5, 0.75, 1.0, 0.45 * alpha)
        g.add_color_stop_rgba(1, 0.5, 0.75, 1.0, 0)
        ctx.set_source(g)
        ctx.arc(cx, cy, R * 1.10, 0, 2 * math.pi)
        ctx.arc_negative(cx, cy, R * 0.99, 2 * math.pi, 0)
        ctx.fill()

    def polyline(self, ctx, lon, lat, st, width=3, rgba=(1, 1, 1, 1), zmin=0.0):
        """Draw a lon/lat polyline on the visible hemisphere."""
        x, y, z = self.project(lon, lat, st)
        vis = z > zmin
        ctx.set_source_rgba(*rgba)
        ctx.set_line_width(width)
        ctx.set_line_cap(cairo.LINE_CAP_ROUND)
        ctx.set_line_join(cairo.LINE_JOIN_ROUND)
        ctx.new_path()
        pen = False
        for i in range(len(x)):
            if vis[i]:
                if pen:
                    ctx.line_to(x[i], y[i])
                else:
                    ctx.move_to(x[i], y[i])
                    pen = True
            else:
                pen = False
        ctx.stroke()


def R_for_view(W, view_w, lat):
    """Globe radius whose centre scale matches a flat mercator view width."""
    return W / (view_w * 2 * math.pi * max(0.05, math.cos(math.radians(lat))))


def w_for_R(W, R, lat):
    return W / (R * 2 * math.pi * max(0.05, math.cos(math.radians(lat))))


def matched_view(W, H, lon0, lat0, R, globe_cy=None):
    """Flat mercator View that lines up with a globe (lon0, lat0, R) drawn at
    (W/2, globe_cy). Use it as the camera while cross-fading globe <-> map."""
    from .camera import View
    globe_cy = H / 2 if globe_cy is None else globe_cy
    x, y = merc(lon0, lat0)
    wv = w_for_R(W, R, lat0)
    return View(float(x), float(y) + (H / 2 - globe_cy) * wv / W, wv)


def zoom_state(t, t0, t1, a, b, ease=None):
    """Interpolate globe states a=(lon,lat,R) -> b with log-zoom; returns (lon,lat,R)."""
    from . import ease as E
    ease = ease or E.in_out_cubic
    p = E.prog(t, t0, t1, ease)
    lon = a[0] + (b[0] - a[0]) * p
    lat = a[1] + (b[1] - a[1]) * p
    R = math.exp(math.log(a[2]) + (math.log(b[2]) - math.log(a[2])) * p)
    return lon, lat, R


def state_for_view(W, H, view, globe_cy=None):
    """Inverse of matched_view: globe (lon0, lat0, R) that lines up with a flat View."""
    from .geo import inv_merc
    globe_cy = H / 2 if globe_cy is None else globe_cy
    y = view.cy - (H / 2 - globe_cy) * view.w / W
    lon0, lat0 = inv_merc(view.cx, y)
    lon0, lat0 = float(lon0), float(lat0)
    return lon0, lat0, R_for_view(W, view.w, lat0)
