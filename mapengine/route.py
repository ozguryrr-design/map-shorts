"""Animated routes (ships / travellers) along a lon/lat polyline."""
import math

import cairo
import numpy as np

from .geo import merc

R_EARTH = 6371.0


class Route:
    def __init__(self, lonlat, labels=None):
        self.ll = np.asarray(lonlat, float)
        self.labels = labels or {}
        lo, la = np.radians(self.ll[:, 0]), np.radians(self.ll[:, 1])
        # haversine segment lengths (km)
        dlo, dla = np.diff(lo), np.diff(la)
        a = np.sin(dla / 2) ** 2 + np.cos(la[:-1]) * np.cos(la[1:]) * np.sin(dlo / 2) ** 2
        seg = 2 * R_EARTH * np.arcsin(np.sqrt(np.clip(a, 0, 1)))
        self.cum = np.concatenate([[0], np.cumsum(seg)])
        self.total = float(self.cum[-1])
        mx, my = merc(self.ll[:, 0], self.ll[:, 1])
        self.m = np.stack([mx, my], 1)  # unwrapped mercator (x may be <0)

    def km(self, label):
        return float(self.cum[self.labels[label]])

    def _idx(self, d):
        d = min(max(d, 0.0), self.total)
        i = int(np.searchsorted(self.cum, d, side="right") - 1)
        i = min(i, len(self.cum) - 2)
        seg = self.cum[i + 1] - self.cum[i]
        f = 0.0 if seg <= 0 else (d - self.cum[i]) / seg
        return i, f

    def merc_at(self, d):
        i, f = self._idx(d)
        return self.m[i] * (1 - f) + self.m[i + 1] * f

    def lonlat_at(self, d):
        i, f = self._idx(d)
        return self.ll[i] * (1 - f) + self.ll[i + 1] * f

    def merc_upto(self, d, d0=0.0):
        """mercator polyline from distance d0 to d."""
        if d <= d0:
            return np.zeros((0, 2))
        i0, f0 = self._idx(d0)
        i1, f1 = self._idx(d)
        a = self.m[i0] * (1 - f0) + self.m[i0 + 1] * f0
        b = self.m[i1] * (1 - f1) + self.m[i1 + 1] * f1
        return np.vstack([a, self.m[i0 + 1:i1 + 1], b])

    def lonlat_upto(self, d, d0=0.0):
        if d <= d0:
            return np.zeros((0, 2))
        i0, f0 = self._idx(d0)
        i1, f1 = self._idx(d)
        a = self.ll[i0] * (1 - f0) + self.ll[i0 + 1] * f0
        b = self.ll[i1] * (1 - f1) + self.ll[i1 + 1] * f1
        return np.vstack([a, self.ll[i0 + 1:i1 + 1], b])

    def heading_merc(self, d, window=250.0):
        a = self.merc_at(d - window)
        b = self.merc_at(d + window)
        return b - a


class Timeline:
    """Monotone cubic interpolation of a value through keyframes.

    keys: [(t, value, stop_bool), ...]; at stop keys velocity is zero.
    """

    def __init__(self, keys):
        self.t = np.array([k[0] for k in keys], float)
        self.v = np.array([k[1] for k in keys], float)
        stop = [bool(k[2]) if len(k) > 2 else False for k in keys]
        n = len(keys)
        d = np.diff(self.v) / np.diff(self.t)
        m = np.zeros(n)
        for i in range(n):
            if stop[i] or i == 0 or i == n - 1:
                m[i] = 0.0
            else:
                if d[i - 1] * d[i] <= 0:
                    m[i] = 0.0
                else:  # harmonic mean (Fritsch-Carlson style)
                    w1 = 2 * (self.t[i + 1] - self.t[i]) + (self.t[i] - self.t[i - 1])
                    w2 = (self.t[i + 1] - self.t[i]) + 2 * (self.t[i] - self.t[i - 1])
                    m[i] = (w1 + w2) / (w1 / d[i - 1] + w2 / d[i])
        self.m = m

    def __call__(self, t):
        if t <= self.t[0]:
            return float(self.v[0])
        if t >= self.t[-1]:
            return float(self.v[-1])
        i = int(np.searchsorted(self.t, t) - 1)
        h = self.t[i + 1] - self.t[i]
        s = (t - self.t[i]) / h
        h00 = 2 * s ** 3 - 3 * s ** 2 + 1
        h10 = s ** 3 - 2 * s ** 2 + s
        h01 = -2 * s ** 3 + 3 * s ** 2
        h11 = s ** 3 - s ** 2
        return float(h00 * self.v[i] + h10 * h * self.m[i] + h01 * self.v[i + 1] + h11 * h * self.m[i + 1])


# ------------------------------------------------------------------- icons
HULL = (0.36, 0.21, 0.11)
SAIL = (0.97, 0.94, 0.86)


def draw_ship(ctx, x, y, size=44, facing=1.0, alpha=1.0, t=0.0, phase=0.0, burn=0.0):
    """Small caravel/nao silhouette. facing in [-1,1] (sign = direction,
    magnitude <1 gives a turning squash). burn 0..1 tints orange/dark."""
    if alpha <= 0.01:
        return
    bob = math.sin(t * 2.6 + phase) * 0.06 * size
    rot = math.sin(t * 2.0 + phase * 1.3) * 0.05
    ctx.save()
    ctx.translate(x, y + bob)
    # soft halo for readability on any background
    g = cairo.RadialGradient(0, -size * 0.25, 0, 0, -size * 0.25, size * 0.95)
    g.add_color_stop_rgba(0, 0, 0, 0, 0.35 * alpha)
    g.add_color_stop_rgba(1, 0, 0, 0, 0)
    ctx.set_source(g)
    ctx.arc(0, -size * 0.25, size * 0.95, 0, 6.283)
    ctx.fill()
    ctx.rotate(rot)
    sx = facing if abs(facing) > 0.08 else math.copysign(0.08, facing or 1)
    ctx.scale(size * sx, size)
    ctx.push_group()
    hull = tuple(HULL[i] * (1 - burn) + (0.15, 0.08, 0.05)[i] * burn for i in range(3))
    sail = tuple(SAIL[i] * (1 - burn) + (1.0, 0.55, 0.15)[i] * burn for i in range(3))
    # hull
    ctx.move_to(-0.62, -0.10)
    ctx.line_to(0.66, -0.06)
    ctx.curve_to(0.55, 0.12, 0.45, 0.22, 0.30, 0.24)
    ctx.line_to(-0.38, 0.24)
    ctx.curve_to(-0.52, 0.18, -0.6, 0.05, -0.62, -0.10)
    ctx.close_path()
    ctx.set_source_rgb(*hull)
    ctx.fill_preserve()
    ctx.set_source_rgba(0, 0, 0, 0.6)
    ctx.set_line_width(0.035)
    ctx.stroke()
    # masts
    ctx.set_source_rgb(*hull)
    ctx.set_line_width(0.04)
    for mx, top in ((-0.30, -0.78), (0.05, -1.02), (0.38, -0.74)):
        ctx.move_to(mx, -0.08)
        ctx.line_to(mx, top)
        ctx.stroke()
    # sails (slightly billowed toward the bow = +x)
    def sail_rect(x0, x1, y0, y1, bulge=0.06):
        ctx.move_to(x0, y0)
        ctx.curve_to((x0 + x1) / 2, y0 + bulge * 0.3, (x0 + x1) / 2, y0 + bulge * 0.3, x1, y0)
        ctx.curve_to(x1 + bulge, (y0 + y1) / 2, x1 + bulge, (y0 + y1) / 2, x1, y1)
        ctx.line_to(x0, y1)
        ctx.curve_to(x0 + bulge, (y0 + y1) / 2, x0 + bulge, (y0 + y1) / 2, x0, y0)
        ctx.close_path()
    ctx.set_source_rgb(*sail)
    sail_rect(-0.16, 0.26, -0.95, -0.62)
    ctx.fill()
    sail_rect(-0.22, 0.32, -0.56, -0.14)
    ctx.fill()
    sail_rect(0.22, 0.54, -0.68, -0.20)
    ctx.fill()
    ctx.move_to(-0.30, -0.74)  # lateen mizzen
    ctx.line_to(-0.55, -0.14)
    ctx.line_to(-0.06, -0.16)
    ctx.close_path()
    ctx.fill()
    # cross of Burgundy on the main course
    ctx.set_source_rgba(0.75, 0.08, 0.08, 1 - burn)
    ctx.set_line_width(0.05)
    ctx.move_to(-0.12, -0.50)
    ctx.line_to(0.22, -0.20)
    ctx.move_to(0.22, -0.50)
    ctx.line_to(-0.12, -0.20)
    ctx.stroke()
    # pennant
    ctx.set_source_rgb(0.8, 0.1, 0.1)
    ctx.move_to(0.05, -1.02)
    ctx.line_to(0.30, -0.97 + 0.03 * math.sin(t * 6 + phase))
    ctx.line_to(0.05, -0.92)
    ctx.close_path()
    ctx.fill()
    ctx.pop_group_to_source()
    ctx.paint_with_alpha(alpha)
    ctx.restore()


def draw_pin(ctx, x, y, t, t0, color=(1.0, 0.83, 0.3), size=1.0, alpha=1.0):
    """Pulsing location marker that pops in at t0."""
    if t < t0 or alpha <= 0:
        return
    from . import ease as E
    p = E.out_back(min(1.0, (t - t0) / 0.45), 2.0)
    r = 9 * size * p
    for k in range(2):
        ph = ((t - t0) * 0.9 + k * 0.5) % 1.0
        ctx.set_source_rgba(*color, alpha * 0.7 * (1 - ph))
        ctx.set_line_width(2.5)
        ctx.arc(x, y, r + 34 * size * ph, 0, 6.283)
        ctx.stroke()
    ctx.set_source_rgba(0, 0, 0, 0.35 * alpha)
    ctx.arc(x, y + 2, r + 3, 0, 6.283)
    ctx.fill()
    ctx.set_source_rgba(1, 1, 1, alpha)
    ctx.arc(x, y, r + 2.5, 0, 6.283)
    ctx.fill()
    ctx.set_source_rgba(*color, alpha)
    ctx.arc(x, y, r, 0, 6.283)
    ctx.fill()
