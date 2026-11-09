"""Geography helpers: data loading, Web-Mercator projection, true-size moves.

All map coordinates inside the engine are normalized Web Mercator:
x in [0,1] (west->east), y in [0,1] (north->south).
"""
import json
import math
import os
import pickle

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw")
CACHE = os.path.join(ROOT, "data", "cache")
MAX_LAT = 85.05112878


# ----------------------------------------------------------------- projection
def merc(lon, lat):
    lon = np.asarray(lon, dtype=np.float64)
    lat = np.clip(np.asarray(lat, dtype=np.float64), -MAX_LAT, MAX_LAT)
    x = (lon + 180.0) / 360.0
    r = np.radians(lat)
    y = (1.0 - np.log(np.tan(r) + 1.0 / np.cos(r)) / math.pi) / 2.0
    return x, y


def inv_merc(x, y):
    lon = np.asarray(x) * 360.0 - 180.0
    lat = np.degrees(np.arctan(np.sinh(math.pi * (1.0 - 2.0 * np.asarray(y)))))
    return lon, lat


# ------------------------------------------------------------------- shapes
class Shape:
    """A (multi)polygon as a flat list of rings in lon/lat (even-odd fill)."""

    def __init__(self, rings, name=""):
        self.name = name
        self.rings = [np.asarray(r, dtype=np.float64) for r in rings if len(r) >= 3]
        self._merc = None
        self.centroid = self._centroid()

    # area-weighted centroid computed on an equal-area-ish local projection
    def _centroid(self):
        lat0 = np.mean(np.concatenate([r[:, 1] for r in self.rings]))
        k = math.cos(math.radians(lat0))
        A = Cx = Cy = 0.0
        for r in self.rings:
            x = r[:, 0] * k
            y = r[:, 1]
            x1, y1 = np.roll(x, -1), np.roll(y, -1)
            c = x * y1 - x1 * y
            a = c.sum() / 2.0
            A += a
            Cx += ((x + x1) * c).sum() / 6.0
            Cy += ((y + y1) * c).sum() / 6.0
        if abs(A) < 1e-12:
            allp = np.concatenate(self.rings)
            return float(allp[:, 0].mean()), float(allp[:, 1].mean())
        return float(Cx / A / k), float(Cy / A)

    @property
    def merc_rings(self):
        if self._merc is None:
            self._merc = [np.stack(merc(r[:, 0], r[:, 1]), axis=1) for r in self.rings]
        return self._merc

    def bbox_merc(self):
        allp = np.concatenate(self.merc_rings)
        return allp[:, 0].min(), allp[:, 1].min(), allp[:, 0].max(), allp[:, 1].max()

    def moved_to(self, lon1, lat1):
        """Return mercator rings of this shape moved on the sphere so that its
        centroid sits at (lon1, lat1) - keeps true size (thetruesize.com style)."""
        lon0, lat0 = self.centroid
        out = []
        for r in self.rings:
            lo, la = true_size_move(r[:, 0], r[:, 1], lon0, lat0, lon1, lat1)
            out.append(np.stack(merc(lo, la), axis=1))
        return out


def true_size_move(lon, lat, lon0, lat0, lon1, lat1):
    """Rotate points on the sphere: shift longitude, then slide along the
    meridian so that (lon0,lat0) -> (lon1,lat1). North stays (almost) up."""
    lam = np.radians(lon - lon0)  # relative longitude, centred on meridian 0
    phi = np.radians(lat)
    x = np.cos(phi) * np.cos(lam)
    y = np.cos(phi) * np.sin(lam)
    z = np.sin(phi)
    # rotate about the y axis (east axis at meridian 0) by d = lat1-lat0
    d = math.radians(lat1 - lat0)
    cd, sd = math.cos(d), math.sin(d)
    x2 = x * cd - z * sd
    z2 = x * sd + z * cd
    lat2 = np.degrees(np.arcsin(np.clip(z2, -1, 1)))
    lon2 = np.degrees(np.arctan2(y, x2)) + lon1  # left unwrapped: stays continuous
    return lon2, lat2


# ------------------------------------------------------------------ loading
def _geom_rings(geom):
    t = geom["type"]
    c = geom["coordinates"]
    if t == "Polygon":
        return [r for r in c]
    if t == "MultiPolygon":
        return [r for poly in c for r in poly]
    return []


def _load_json(name):
    os.makedirs(CACHE, exist_ok=True)
    pk = os.path.join(CACHE, name + ".pkl")
    if os.path.exists(pk):
        with open(pk, "rb") as f:
            return pickle.load(f)
    with open(os.path.join(RAW, name + ".geojson"), encoding="utf-8") as f:
        d = json.load(f)
    feats = [(ft["properties"], _geom_rings(ft["geometry"])) for ft in d["features"] if ft["geometry"]]
    with open(pk, "wb") as f:
        pickle.dump(feats, f, protocol=pickle.HIGHEST_PROTOCOL)
    return feats


def _norm_name(s):
    tr = str.maketrans("İIıÇĞÖŞÜçğöşü", "iiicgosucgosu")
    return (s or "").translate(tr).lower().strip()


def find_country(name):
    """Look a country up by any name (any language Natural Earth knows, e.g.
    'Almanya', 'Germany', 'DEU', 'DE'). Returns list of (ADM0_A3, NAME, NAME_TR, ISO_A2)."""
    q = _norm_name(name)
    exact, part = [], []
    for p, _ in _load_json("ne_10m_admin_0_countries"):
        keys = [v for k, v in p.items() if (k.startswith("NAME") and isinstance(v, str))]
        keys += [p.get("ADMIN"), p.get("ADM0_A3"), p.get("ISO_A3"), p.get("ISO_A2")]
        names = [_norm_name(k) for k in keys if isinstance(k, str)]
        row = (p.get("ADM0_A3"), p.get("NAME"), p.get("NAME_TR"), p.get("ISO_A2"))
        if q in names:
            exact.append(row)
        elif any(q in n for n in names if len(q) >= 3):
            part.append(row)
    return exact or part


def find_admin1(name, adm0_a3=None):
    """Search states/provinces by any name. Returns (name, adm0_a3, name_tr)."""
    q = _norm_name(name)
    out = []
    for p, _ in _load_json("ne_10m_admin_1_states_provinces"):
        if adm0_a3 and p.get("adm0_a3") != adm0_a3:
            continue
        names = [_norm_name(v) for k, v in p.items() if k.startswith("name") and isinstance(v, str)]
        if q in names or any(q in n for n in names if len(q) >= 4):
            out.append((p.get("name"), p.get("adm0_a3"), p.get("name_tr")))
    return out


def country(a3, min_area=0.0):
    """Country by ISO A3 / ADM0_A3 code (or any name, see find_country).
    min_area (deg^2) drops tiny islands."""
    for p, rings in _load_json("ne_10m_admin_0_countries"):
        if a3 in (p.get("ADM0_A3"), p.get("ISO_A3"), p.get("SOV_A3")):
            return Shape(_filter(rings, min_area), p.get("NAME", a3))
    hits = find_country(a3)
    if hits:
        return country(hits[0][0], min_area)
    raise KeyError(a3)


def admin1(name, adm0_a3=None, min_area=0.0):
    for p, rings in _load_json("ne_10m_admin_1_states_provinces"):
        if p.get("name") == name and (adm0_a3 is None or p.get("adm0_a3") == adm0_a3):
            return Shape(_filter(rings, min_area), name)
    hits = find_admin1(name, adm0_a3)
    if hits:
        return admin1(hits[0][0], hits[0][1], min_area)
    raise KeyError(name)


def union(*shapes, name=""):
    """Combine several shapes (e.g. a group of countries) into one Shape."""
    return Shape([r for s in shapes for r in s.rings], name)


def _ring_area(r):
    r = np.asarray(r)
    x, y = r[:, 0], r[:, 1]
    return abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))) / 2


def _filter(rings, min_area):
    if min_area <= 0:
        return rings
    return [r for r in rings if _ring_area(r) >= min_area]


def all_borders(tol_deg=0.02):
    """Simplified rings of every country (for the faint context border layer)."""
    pk = os.path.join(CACHE, f"borders_{tol_deg}.pkl")
    if os.path.exists(pk):
        with open(pk, "rb") as f:
            return pickle.load(f)
    out = []
    for p, rings in _load_json("ne_10m_admin_0_countries"):
        for r in rings:
            r = np.asarray(r)
            if _ring_area(r) < 0.05:
                continue
            r = _rdp(r, tol_deg)
            mx, my = merc(r[:, 0], r[:, 1])
            m = np.stack([mx, my], 1)
            out.append((m, (mx.min(), my.min(), mx.max(), my.max())))
    with open(pk, "wb") as f:
        pickle.dump(out, f, protocol=pickle.HIGHEST_PROTOCOL)
    return out


def _rdp(pts, eps):
    """Iterative Ramer-Douglas-Peucker."""
    n = len(pts)
    if n < 4:
        return pts
    keep = np.zeros(n, bool)
    keep[0] = keep[-1] = True
    stack = [(0, n - 1)]
    while stack:
        a, b = stack.pop()
        if b <= a + 1:
            continue
        p, q = pts[a], pts[b]
        seg = pts[a + 1:b]
        d = q - p
        L = math.hypot(*d)
        if L == 0:
            dist = np.hypot(*(seg - p).T)
        else:
            dist = np.abs(d[0] * (seg[:, 1] - p[1]) - d[1] * (seg[:, 0] - p[0])) / L
        i = int(np.argmax(dist))
        if dist[i] > eps:
            k = a + 1 + i
            keep[k] = True
            stack += [(a, k), (k, b)]
    return pts[keep]
