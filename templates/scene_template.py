"""SCENE TEMPLATE  -  copy of templates/scene_template.py (make.py new <name>)

Works out of the box with any narration (beats are bound to sentences) so you
can render immediately, then rewrite the STORY section for the real topic.

Conventions (see references/API.md and references/STYLE.md):
  * every time comes from the voiceover:  w("kelime")  or  S(i) = sentence i
  * camera is a CameraPath: fly (cinematic), move, drift (never fully static)
  * <= 3 words of on-screen text at a time; titles live in the top area (y 220-520)
  * keep the bottom ~25% and the right edge free (Shorts UI)
"""
import math
import os

from mapengine import ease as E
from mapengine import fx
from mapengine.camera import CameraPath, View
from mapengine.geo import country, merc
from mapengine.globe import Globe, R_for_view, matched_view, state_for_view, zoom_state
from mapengine.timing import Words, find_vo

HERE = os.path.dirname(os.path.abspath(__file__))
W, H, FPS = 1080, 1920, 60
TILE_PROVIDER = "s2"        # "s2" Sentinel-2 2016 (CC BY 4.0, commercial OK) | "nasa" Blue Marble (public domain, low-res) | "esri" (non-commercial)
ATTRIBUTION = True          # imagery credit on every frame - required by CC BY for "s2"; keep it on
MAX_LEVEL = 10

# ---- voiceover & timing --------------------------------------------------
VO_OFFSET = 0.4
VO = [(find_vo(HERE), VO_OFFSET)]
VW = Words(os.path.join(HERE, "vo", "words.json"), offset=VO_OFFSET)
w = VW.at                                   # w("Pasifik") -> start time of that word


def S(i):
    """(start, end) of sentence i  (negative = from the end, clamped)."""
    return VW.sentence(i)


DURATION = round(VW.last_end + 2.0, 2)

# =========================================================================
# STORY  (rewrite this section for the topic)
# =========================================================================
A = country("TUR", min_area=0.002)          # any name works too: country("Almanya")
B = country("DEU", min_area=0.002)
A_FLAG, B_FLAG = "tr", "de"                 # ISO2 for fx.flag()
A_NAME, B_NAME = "TÜRKİYE", "ALMANYA"
COLOR_A, COLOR_B = "#9e1010", "#f7d548"

n = VW.n_sentences
T_INTRO_END = S(0)[0] + 2.4                 # globe -> map handover
T_A = S(0)[0] + 0.3                         # A title
T_FLAG = S(min(1, n - 1))[0]                # flag wipe on A
T_FLY = S(min(2, n - 1))[0] if n > 2 else S(-1)[0] + 0.5
T_FLY_END = T_FLY + 2.2
T_OUT = max(T_FLY_END + 1.5, S(-1)[0])      # back to the globe on the last sentence

# views: centre on a shape and show w_deg degrees of longitude
def view_on(shape, w_deg, dy=0.0):
    x, y = merc(*shape.centroid)
    return View(float(x), float(y) + dy, w_deg / 360.0)


def fit(shape, pad=0.14):
    return View.fit(shape.bbox_merc(), W, H, pad=pad)


V_A = fit(A)
V_B = fit(B, 0.18)

# ---- globe (intro & outro) ----------------------------------------------
GLOBE_CY = H * 0.53
LON_A, LAT_A = V_A.lonlat()
G_START = (LON_A + 40, 15, 380)                         # lon, lat, radius(px)
G_MATCH = state_for_view(W, H, V_A, GLOBE_CY)          # globe that lines up with V_A
LON_B, LAT_B = V_B.lonlat()
G_END = (LON_B - 25, LAT_B * 0.5, 430)


_G_OUT0 = None  # set after the camera is built (globe that matches the last map view)


def globe_state(t):
    if t < T_OUT:
        return zoom_state(t, 0.0, T_INTRO_END, G_START, G_MATCH, E.in_out_quint)
    return zoom_state(t, T_OUT, T_OUT + 1.8, _G_OUT0, G_END, E.in_out_cubic)


def globe_alpha(t):
    a_in = 1 - E.prog(t, T_INTRO_END - 0.9, T_INTRO_END, E.smooth)
    a_out = E.prog(t, T_OUT + 0.15, T_OUT + 0.9, E.smooth)
    return max(a_in, a_out)


def basemap_visible(t):
    return globe_alpha(t) < 0.999


def _globe_view(t):
    return matched_view(W, H, *globe_state(t), globe_cy=GLOBE_CY)


# ---- camera ----------------------------------------------------------------
cam = CameraPath(_globe_view(0))
cam.custom(0, T_INTRO_END, _globe_view)
cam.drift(T_INTRO_END, T_FLY, zoom=1.06)
cam.fly(T_FLY, T_FLY_END, V_B)
cam.drift(T_FLY_END, T_OUT, zoom=1.05)
_G_OUT0 = state_for_view(W, H, cam.last, GLOBE_CY)
cam.custom(T_OUT, DURATION, _globe_view)


def camera(t):
    return cam(t)


def setup():
    from mapengine.geo import all_borders
    return dict(borders=all_borders(), globe=Globe(W, H))


# ---- drawing ---------------------------------------------------------------
def draw(fr, st):
    t, c = fr.t, fr.ctx
    ga = globe_alpha(t)

    if ga < 1:
        fr.grade(darken=0.2, desat=0.18)
        fr.borders(st["borders"], alpha=0.12)

        # A: border draws on, tinted fill, then flag wipe
        border = E.prog(t, T_INTRO_END - 0.6, T_INTRO_END + 0.8, E.in_out_cubic)
        fill = E.prog(t, T_INTRO_END, T_INTRO_END + 0.8)
        rings = fx.highlight(fr, A, COLOR_A, fill, border=border, solid=0.5)
        fx.flag_fill(fr, rings, A_FLAG, wipe=E.prog(t, T_FLAG, T_FLAG + 0.8, E.in_out_cubic))

        # B appears when we fly there
        b = E.prog(t, T_FLY_END - 0.8, T_FLY_END)
        fx.highlight(fr, B, COLOR_B, b, border=b, solid=0.55)

        # arrow arc A -> B
        fx.arc(fr, A.centroid, B.centroid, E.prog(t, T_FLY - 0.3, T_FLY + 1.2, E.in_out_cubic),
               color=fx.GOLD, alpha=1 - E.prog(t, T_OUT - 0.5, T_OUT))
        fr.vignette(0.5)

    if ga > 0:
        G = st["globe"]
        gs = (*globe_state(t), W / 2, GLOBE_CY)
        c.push_group()
        G.draw_space(c, t)
        G.draw(c, gs)
        fr.grade(darken=0.12, desat=0.1)
        c.pop_group_to_source()
        c.paint_with_alpha(ga)

    # titles (minimal)
    fx.title(c, t, A_NAME, T_A, T_FLY)
    fx.title(c, t, B_NAME, T_FLY_END - 0.3, T_OUT + 0.3)

    fade = max(1 - E.prog(t, 0, 0.4), E.prog(t, DURATION - 0.5, DURATION))
    if fade > 0:
        c.set_source_rgba(0, 0, 0, fade)
        c.paint()


# ---- sound design -------------------------------------------------------------
SFX = [
    (0.1, "whoosh", dict(dur=T_INTRO_END, gain=0.4)),
    (T_A, "swish", dict(gain=0.2)),
    (T_FLAG, "shimmer", dict(gain=0.2)),
    (T_FLY - 0.1, "whoosh", dict(dur=T_FLY_END - T_FLY + 0.3, gain=0.55)),
    (T_FLY_END, "thump", dict(gain=0.35)),
    (T_OUT, "whoosh", dict(dur=2.0, gain=0.45)),
]
