"""Sea routing: turns rough waypoints into a smooth path that never crosses land.

For each consecutive waypoint pair whose straight line touches land, an A*
search runs on a rasterized land mask (with a coast-distance penalty), then the
result is simplified and smoothed. Longitudes may be unwrapped (< -180 / > 180).
"""
import hashlib
import heapq
import json
import math
import os
import pickle

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from .geo import CACHE, _load_json, _ring_area

_LAND = None


def _land():
    global _LAND
    if _LAND is None:
        rings = []
        for p, rs in _load_json("ne_10m_admin_0_countries"):
            for r in rs:
                a = np.asarray(r)
                if len(a) > 3:
                    rings.append((a, a[:, 0].min(), a[:, 1].min(), a[:, 0].max(), a[:, 1].max()))
        _LAND = rings
    return _LAND


def land_mask(x0, y0, x1, y1, res):
    """bool grid [ny, nx], True = land. Cell (j,i) centre = (x0+(i+.5)res, y1-(j+.5)res)."""
    nx, ny = int(math.ceil((x1 - x0) / res)), int(math.ceil((y1 - y0) / res))
    im = Image.new("L", (nx, ny), 0)
    d = ImageDraw.Draw(im)
    for a, ax0, ay0, ax1, ay1 in _land():
        if ay1 < y0 or ay0 > y1:
            continue
        for sh in (-720, -360, 0, 360):
            if ax1 + sh < x0 or ax0 + sh > x1:
                continue
            px = (a[:, 0] + sh - x0) / res
            py = (y1 - a[:, 1]) / res
            d.polygon(list(zip(px.tolist(), py.tolist())), fill=255)
    return np.asarray(im) > 0, nx, ny


def _seg_hits_land(a, b, res=0.02):
    x0, x1 = min(a[0], b[0]) - 0.05, max(a[0], b[0]) + 0.05
    y0, y1 = min(a[1], b[1]) - 0.05, max(a[1], b[1]) + 0.05
    m, nx, ny = land_mask(x0, y0, x1, y1, res)
    n = max(2, int(math.hypot(b[0] - a[0], b[1] - a[1]) / (res * 0.5)))
    t = np.linspace(0, 1, n)
    xs = a[0] + (b[0] - a[0]) * t
    ys = a[1] + (b[1] - a[1]) * t
    i = np.clip(((xs - x0) / res).astype(int), 0, nx - 1)
    j = np.clip(((y1 - ys) / res).astype(int), 0, ny - 1)
    return bool(m[j, i][3:-3].any()) if n > 8 else bool(m[j, i].any())


def _astar(a, b, res, margin=1.5, coast_px=4, coast_cost=6.0):
    x0, x1 = min(a[0], b[0]) - margin, max(a[0], b[0]) + margin
    y0, y1 = min(a[1], b[1]) - margin, max(a[1], b[1]) + margin
    m, nx, ny = land_mask(x0, y0, x1, y1, res)
    # coast proximity penalty via successive dilations
    pen = np.zeros(m.shape, np.float32)
    im = Image.fromarray((m * 255).astype(np.uint8))
    for k in range(1, coast_px + 1):
        im = im.filter(ImageFilter.MaxFilter(3))
        pen += (np.asarray(im) > 0)
    pen = pen / coast_px * coast_cost

    def cell(p):
        return (min(ny - 1, max(0, int((y1 - p[1]) / res))), min(nx - 1, max(0, int((p[0] - x0) / res))))

    def snap(c):  # nearest water cell
        if not m[c]:
            return c
        jj, ii = np.nonzero(~m)
        k = np.argmin((jj - c[0]) ** 2 + (ii - c[1]) ** 2)
        return (int(jj[k]), int(ii[k]))

    s, g = snap(cell(a)), snap(cell(b))
    nbr = [(-1, 0, 1), (1, 0, 1), (0, -1, 1), (0, 1, 1), (-1, -1, 1.414), (-1, 1, 1.414), (1, -1, 1.414), (1, 1, 1.414)]
    dist = {s: 0.0}
    prev = {}
    h = lambda c: math.hypot(c[0] - g[0], c[1] - g[1])
    pq = [(h(s), s)]
    seen = set()
    while pq:
        _, c = heapq.heappop(pq)
        if c == g:
            break
        if c in seen:
            continue
        seen.add(c)
        for dj, di, w in nbr:
            n_ = (c[0] + dj, c[1] + di)
            if not (0 <= n_[0] < ny and 0 <= n_[1] < nx) or m[n_]:
                continue
            nd = dist[c] + w * (1 + pen[n_])
            if nd < dist.get(n_, 1e18):
                dist[n_] = nd
                prev[n_] = c
                heapq.heappush(pq, (nd + h(n_), n_))
    if g not in prev and g != s:
        raise RuntimeError(f"no sea path {a} -> {b}")
    path = [g]
    while path[-1] != s:
        path.append(prev[path[-1]])
    path.reverse()
    pts = [(x0 + (i + 0.5) * res, y1 - (j + 0.5) * res) for j, i in path]
    return pts, (m, x0, y1, res)


def _simplify_safe(pts, mask_info):
    """Greedy line-of-sight simplification on the land mask."""
    m, x0, y1, res = mask_info
    ny, nx = m.shape

    def clear(p, q):
        n = max(2, int(math.hypot(q[0] - p[0], q[1] - p[1]) / (res * 0.5)))
        t = np.linspace(0, 1, n)
        i = np.clip(((p[0] + (q[0] - p[0]) * t - x0) / res).astype(int), 0, nx - 1)
        j = np.clip(((y1 - (p[1] + (q[1] - p[1]) * t)) / res).astype(int), 0, ny - 1)
        return not m[j, i].any()

    out = [pts[0]]
    i = 0
    while i < len(pts) - 1:
        k = len(pts) - 1
        while k > i + 1 and not clear(pts[i], pts[k]):
            k = max(i + 1, i + (k - i) // 2) if k - i > 40 else k - 1
        out.append(pts[k])
        i = k
    return out


def chaikin(pts, it=3):
    p = np.asarray(pts, float)
    for _ in range(it):
        q = 0.75 * p[:-1] + 0.25 * p[1:]
        r = 0.25 * p[:-1] + 0.75 * p[1:]
        mid = np.empty((len(q) * 2, 2))
        mid[0::2], mid[1::2] = q, r
        p = np.vstack([p[:1], mid, p[-1:]])
    return p


def sea_route(waypoints, res_fine=0.01, smooth=3, log=True):
    """waypoints: [(lon,lat[,label])...] -> (Nx2 array, {label: index})."""
    key = hashlib.md5(json.dumps([list(w) for w in waypoints]).encode() + b"v2").hexdigest()[:12]
    pk = os.path.join(CACHE, f"route_{key}.pkl")
    if os.path.exists(pk):
        with open(pk, "rb") as f:
            return pickle.load(f)
    pts, labels = [], {}
    for k in range(len(waypoints) - 1):
        a, b = waypoints[k][:2], waypoints[k + 1][:2]
        if len(waypoints[k]) > 2:
            labels[waypoints[k][2]] = len(pts)
        if _seg_hits_land(a, b):
            span = max(abs(b[0] - a[0]), abs(b[1] - a[1]))
            res = max(res_fine, span / 300)
            seg, info = _astar(a, b, res, margin=max(0.3, span * 0.4))
            seg = _simplify_safe(seg, info)
            if log:
                print(f"[seapath] rerouted {waypoints[k]} -> {waypoints[k+1]} ({len(seg)} pts)")
            seg[0], seg[-1] = tuple(a), tuple(b)
            pts.extend(seg[:-1])
        else:
            pts.append(tuple(a))
    pts.append(tuple(waypoints[-1][:2]))
    if len(waypoints[-1]) > 2:
        labels[waypoints[-1][2]] = len(pts) - 1
    raw = np.asarray(pts, float)
    # smooth, keeping label indices mapped to nearest smoothed vertex
    sm = chaikin(raw, smooth) if smooth else raw
    lab2 = {}
    for name, i in labels.items():
        d = np.hypot(*(sm - raw[i]).T)
        lab2[name] = int(np.argmin(d))
    res = (sm, lab2)
    with open(pk, "wb") as f:
        pickle.dump(res, f)
    return res
