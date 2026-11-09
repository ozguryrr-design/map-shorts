"""Downloads the data map-shorts needs (idempotent).

* Natural Earth 10m countries + states/provinces (public domain)
* Montserrat fonts (SIL Open Font License)
"""
import os
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NE = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/{}.geojson"
FONT = "https://github.com/JulietaUla/Montserrat/raw/master/fonts/ttf/Montserrat-{}.ttf"

FILES = [(NE.format(n), os.path.join(ROOT, "data", "raw", n + ".geojson"))
         for n in ("ne_10m_admin_0_countries", "ne_10m_admin_1_states_provinces")]
FILES += [(FONT.format(w), os.path.join(ROOT, "assets", "fonts", f"Montserrat-{w}.ttf"))
          for w in ("SemiBold", "Bold", "ExtraBold", "Black")]


def main():
    for url, path in FILES:
        if os.path.exists(path) and os.path.getsize(path) > 1000:
            continue
        os.makedirs(os.path.dirname(path), exist_ok=True)
        print("downloading", os.path.basename(path), "...", flush=True)
        req = urllib.request.Request(url, headers={"User-Agent": "map-shorts/1.0"})
        with urllib.request.urlopen(req, timeout=120) as r, open(path + ".tmp", "wb") as f:
            while True:
                b = r.read(1 << 20)
                if not b:
                    break
                f.write(b)
        os.replace(path + ".tmp", path)
    print("data ok")


if __name__ == "__main__":
    main()
