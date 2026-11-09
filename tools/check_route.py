"""Rota noktalarını karaya çarpma açısından kontrol eder."""
import sys, os, importlib.util, numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shapely.geometry import Polygon, Point
from shapely.strtree import STRtree
from mapengine.geo import _load_json
spec = importlib.util.spec_from_file_location("route", sys.argv[1]); R = importlib.util.module_from_spec(spec); spec.loader.exec_module(R)
polys = []
for p, rings in _load_json("ne_10m_admin_0_countries"):
    for r in rings:
        if len(r) > 3:
            try:
                pg = Polygon(r).buffer(0)
                polys.append(pg)
            except Exception: pass
tree = STRtree(polys)
pts = R.ROUTE
bad = 0
for i in range(len(pts) - 1):
    a, b = np.array(pts[i][:2]), np.array(pts[i + 1][:2])
    n = max(2, int(np.hypot(*(b - a)) / 0.02))
    hits = []
    for t in np.linspace(0, 1, n):
        lo, la = a + (b - a) * t
        lo = (lo + 180) % 360 - 180
        q = Point(lo, la)
        for j in tree.query(q):
            if polys[j].contains(q):
                hits.append((round(lo, 2), round(la, 2))); break
    if hits:
        bad += 1
        print(f"seg {i}->{i+1} {pts[i]} -> {pts[i+1]}: {len(hits)} land pts, first {hits[0]} last {hits[-1]}")
print("bad segments:", bad)
