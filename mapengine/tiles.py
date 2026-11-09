"""Satellite basemap from XYZ tiles (cached on disk) rendered with cairo."""
import math
import os
import threading
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import cairo
from PIL import Image

from .geo import ROOT

PROVIDERS = {
    # Esri World Imagery - check Esri terms / attribution for commercial use.
    "esri": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    # EOX Sentinel-2 cloudless 2016 (CC BY 4.0) - attribution required.
    "s2": "https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless_3857/default/g/{z}/{y}/{x}.jpg",
}
TS = 256


class TileSource:
    def __init__(self, provider="esri", max_level=13, cache_size=600):
        self.provider = provider
        self.url = PROVIDERS[provider]
        self.max_level = max_level
        self.dir = os.path.join(ROOT, "data", "tiles", provider)
        self.mem = {}
        self.order = []
        self.cache_size = cache_size
        self._mosaics = {}  # level -> (range, surface)

    # ------------------------------------------------------------ disk/net
    def path(self, z, x, y):
        return os.path.join(self.dir, str(z), str(x), f"{y}.jpg")

    def download(self, z, x, y):
        p = self.path(z, x, y)
        if os.path.exists(p):
            return True
        os.makedirs(os.path.dirname(p), exist_ok=True)
        req = urllib.request.Request(self.url.format(z=z, x=x, y=y),
                                     headers={"User-Agent": "mapengine/1.0"})
        for _ in range(3):
            try:
                with urllib.request.urlopen(req, timeout=20) as r:
                    data = r.read()
                with open(p + ".tmp", "wb") as f:
                    f.write(data)
                os.replace(p + ".tmp", p)
                return True
            except Exception:
                continue
        return False

    def prefetch(self, tiles, workers=16):
        todo = [t for t in set(tiles) if not os.path.exists(self.path(*t))]
        if not todo:
            return
        print(f"[tiles] downloading {len(todo)} tiles ({self.provider})...", flush=True)
        with ThreadPoolExecutor(workers) as ex:
            ok = sum(ex.map(lambda t: self.download(*t), todo))
        print(f"[tiles] done ({ok}/{len(todo)})", flush=True)

    # ------------------------------------------------------------ geometry
    def level_for(self, scale):
        """scale = screen pixels per world unit."""
        z = math.log2(max(scale, 1e-9) / TS)
        return z

    def tile_range(self, view, W, H, L):
        n = 2 ** L
        h = view.w * H / W
        x0, x1 = view.cx - view.w / 2, view.cx + view.w / 2
        y0, y1 = view.cy - h / 2, view.cy + h / 2
        tx0, tx1 = math.floor(x0 * n), math.floor(x1 * n)
        ty0, ty1 = max(0, math.floor(y0 * n)), min(n - 1, math.floor(y1 * n))
        return tx0, tx1, ty0, ty1

    def levels(self, view, W):
        z = self.level_for(W / view.w)
        L = min(self.max_level, max(0, math.ceil(z - 1e-6)))
        out = [(L, 1.0)]
        # cross-fade window just after a level switch hides imagery "pops"
        frac = z - (L - 1)
        if L >= 1 and L <= self.max_level and 0 <= frac < 0.25 and math.ceil(z - 1e-6) == L:
            out = [(L - 1, 1.0), (L, frac / 0.25)]
        return out

    def tiles_for(self, view, W, H):
        res = []
        for L, _ in self.levels(view, W):
            n = 2 ** L
            tx0, tx1, ty0, ty1 = self.tile_range(view, W, H, L)
            for tx in range(tx0, tx1 + 1):
                for ty in range(ty0, ty1 + 1):
                    res.append((L, tx % n, ty))
        return res

    # ------------------------------------------------------------ drawing
    def _tile_surface(self, z, x, y):
        k = (z, x, y)
        s = self.mem.get(k)
        if s is not None:
            return s
        p = self.path(z, x, y)
        if not os.path.exists(p):
            self.download(z, x, y)
        try:
            im = Image.open(p).convert("RGBA").resize((TS, TS)) if os.path.exists(p) else None
        except Exception:
            im = None
        if im is None:
            im = Image.new("RGBA", (TS, TS), (8, 18, 30, 255))
        buf = bytearray(im.tobytes("raw", "BGRA"))
        s = cairo.ImageSurface.create_for_data(buf, cairo.FORMAT_RGB24, TS, TS, TS * 4)
        self.mem[k] = s
        self.order.append(k)
        if len(self.order) > self.cache_size:
            old = self.order.pop(0)
            self.mem.pop(old, None)
        return s

    def _mosaic_for(self, L, rng):
        hit = self._mosaics.get(L)
        if hit and hit[0] == rng:
            return hit[1]
        tx0, tx1, ty0, ty1 = rng
        n = 2 ** L
        surf = cairo.ImageSurface(cairo.FORMAT_RGB24, (tx1 - tx0 + 1) * TS, (ty1 - ty0 + 1) * TS)
        c = cairo.Context(surf)
        for tx in range(tx0, tx1 + 1):
            for ty in range(ty0, ty1 + 1):
                c.set_source_surface(self._tile_surface(L, tx % n, ty), (tx - tx0) * TS, (ty - ty0) * TS)
                c.paint()
        if len(self._mosaics) >= 3:
            self._mosaics.pop(next(iter(self._mosaics)))
        self._mosaics[L] = (rng, surf)
        return surf

    def draw(self, ctx, view, W, H):
        ctx.set_source_rgb(0.02, 0.05, 0.08)
        ctx.paint()
        scale = W / view.w
        for L, alpha in self.levels(view, W):
            rng = self.tile_range(view, W, H, L)
            if rng[2] > rng[3]:
                continue
            surf = self._mosaic_for(L, rng)
            tx0, _, ty0, _ = rng
            wpx = TS * 2 ** L
            k = scale / wpx
            ctx.save()
            ctx.translate(W / 2, H / 2)
            ctx.scale(k, k)
            ctx.translate(tx0 * TS - view.cx * wpx, ty0 * TS - view.cy * wpx)
            pat = cairo.SurfacePattern(surf)
            pat.set_filter(cairo.FILTER_GOOD)
            pat.set_extend(cairo.EXTEND_PAD)
            ctx.set_source(pat)
            if alpha >= 1.0:
                ctx.paint()
            else:
                ctx.paint_with_alpha(alpha)
            ctx.restore()
