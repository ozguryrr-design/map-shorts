"""Camera: views, smooth zoom+pan flights (van Wijk & Nuij 2003) and drifts."""
import math

import numpy as np

from . import ease as E
from .geo import merc, inv_merc


class View:
    """cx, cy: normalized Mercator centre; w: visible world width (mercator units)."""

    __slots__ = ("cx", "cy", "w")

    def __init__(self, cx, cy, w):
        self.cx, self.cy, self.w = float(cx), float(cy), float(w)

    @classmethod
    def at(cls, lon, lat, w_deg):
        """Centre on lon/lat showing w_deg degrees of longitude across the screen."""
        x, y = merc(lon, lat)
        return cls(x, y, w_deg / 360.0)

    @classmethod
    def fit(cls, bbox, W, H, pad=0.12, offset_y=0.0):
        """Fit a mercator bbox (x0,y0,x1,y1) into a WxH screen."""
        x0, y0, x1, y1 = bbox
        bw, bh = (x1 - x0), (y1 - y0)
        w = max(bw, bh * W / H) / (1 - 2 * pad)
        return cls((x0 + x1) / 2, (y0 + y1) / 2 + offset_y * w * H / W, w)

    def zoomed(self, f):
        return View(self.cx, self.cy, self.w / f)

    def lonlat(self):
        lo, la = inv_merc(self.cx, self.cy)
        return float(lo), float(la)

    def __repr__(self):
        return f"View({self.cx:.5f},{self.cy:.5f},{self.w:.5f})"


def vanwijk(v0, v1, rho=1.35):
    """Return (S, f) where f(s)->View for s in [0,S] is the optimal zoom/pan path."""
    c0 = np.array([v0.cx, v0.cy])
    c1 = np.array([v1.cx, v1.cy])
    w0, w1 = v0.w, v1.w
    dv = c1 - c0
    d = float(np.hypot(*dv))
    if d < 1e-9 * max(w0, w1):
        k = 1 if w1 > w0 else -1
        S = abs(math.log(w1 / w0)) / rho

        def f(s):
            return View(*(c0 + (c1 - c0) * (s / S if S else 1)), w0 * math.exp(k * rho * s))

        return S, f
    r2, r4 = rho * rho, rho ** 4
    b0 = (w1 * w1 - w0 * w0 + r4 * d * d) / (2 * w0 * r2 * d)
    b1 = (w1 * w1 - w0 * w0 - r4 * d * d) / (2 * w1 * r2 * d)
    r0 = math.log(-b0 + math.sqrt(b0 * b0 + 1))
    r1 = math.log(-b1 + math.sqrt(b1 * b1 + 1))
    S = (r1 - r0) / rho
    u_dir = dv / d

    def f(s):
        u = w0 / r2 * (math.cosh(r0) * math.tanh(rho * s + r0) - math.sinh(r0))
        w = w0 * math.cosh(r0) / math.cosh(rho * s + r0)
        c = c0 + u_dir * u
        return View(c[0], c[1], w)

    return S, f


def _lerp_view(a, b, t):
    # zoom interpolated in log space -> perceptually constant speed
    return View(a.cx + (b.cx - a.cx) * t, a.cy + (b.cy - a.cy) * t,
                math.exp(math.log(a.w) + (math.log(b.w) - math.log(a.w)) * t))


class CameraPath:
    """Sequential camera builder.

        cam = CameraPath(start_view)
        cam.fly(0.0, 2.5, target_view)      # cinematic zoom-out/pan/zoom-in
        cam.move(3.0, 4.0, other_view)      # direct eased move
        cam.drift(4.0, 7.0, zoom=1.05)      # slow push-in keeps frames alive
        view = cam(t)
    Gaps between segments hold the last view.
    """

    def __init__(self, start):
        self.start = start
        self.segs = []  # (t0, t1, fn(p)->View)
        self.last = start
        self.t_last = 0.0

    def _add(self, t0, t1, fn, end):
        assert t0 >= self.t_last - 1e-9, "segments must be sequential"
        self.segs.append((t0, t1, fn))
        self.last, self.t_last = end, t1
        return self

    def fly(self, t0, t1, target, ease=E.in_out_cubic, rho=1.35, max_w=None):
        S, f = vanwijk(self.last, target, rho)
        if max_w is None:
            return self._add(t0, t1, lambda p: f(S * ease(p)), target)

        def g(p):
            v = f(S * ease(p))
            # soft clamp of the zoom-out (keeps portrait frames inside the map)
            a = 0.6 * max_w
            if v.w > a:
                v.w = a + (max_w - a) * math.tanh((v.w - a) / (max_w - a))
            return v
        return self._add(t0, t1, g, target)

    def custom(self, t0, t1, fn, end=None):
        """fn(t) -> View for absolute time t (e.g. following a moving object)."""
        e = end if end is not None else fn(t1)
        return self._add(t0, t1, lambda p: fn(t0 + (t1 - t0) * p), e)

    def move(self, t0, t1, target, ease=E.in_out_cubic):
        a = self.last
        return self._add(t0, t1, lambda p: _lerp_view(a, target, ease(p)), target)

    def drift(self, t0, t1, zoom=1.04, dx=0.0, dy=0.0, ease=E.in_out_sine):
        a = self.last
        b = View(a.cx + dx * a.w, a.cy + dy * a.w, a.w / zoom)
        return self._add(t0, t1, lambda p: _lerp_view(a, b, ease(p)), b)

    def __call__(self, t):
        v = self.start
        for t0, t1, fn in self.segs:
            if t < t0:
                return v
            if t <= t1:
                return fn((t - t0) / (t1 - t0) if t1 > t0 else 1.0)
            v = fn(1.0)
        return v
