"""Macellan-Elcano: Dünyayı dolaşan ilk yolculuk (1519-1522).

Tüm zamanlamalar seslendirmedeki kelimelere bağlı (vo/words.json).
Gerçek seslendirme gelince: vo/voice.(wav|mp3) + yeni words.json -> render.
"""
import math
import os

import numpy as np

from mapengine import ease as E
from mapengine.camera import CameraPath, View, _lerp_view
from mapengine.geo import country, merc, inv_merc
from mapengine.globe import Globe, R_for_view, w_for_R
from mapengine.route import Route, Timeline, draw_ship, draw_pin
from mapengine.seapath import sea_route
from mapengine.text import draw_text, title_anim
from mapengine import fx
from mapengine.timing import Words

HERE = os.path.dirname(os.path.abspath(__file__))
import importlib.util as _ilu
_spec = _ilu.spec_from_file_location("macellan_route", os.path.join(HERE, "route.py"))
_RD = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_RD)

W, H, FPS = 1080, 1920, 60
TILE_PROVIDER = "s2"
MAX_LEVEL = 10

# ---- voiceover ----------------------------------------------------------
VO_FILE = "vo/voice.mp3" if os.path.exists(os.path.join(HERE, "vo/voice.mp3")) else "vo/placeholder.mp3"
VO_OFFSET = 0.4
VW = Words(os.path.join(HERE, "vo/words.json"), offset=VO_OFFSET)
w = VW.at
DURATION = round(VW.last_end + 2.2, 2)
VO = [(VO_FILE, VO_OFFSET)]

GOLD = (1.0, 0.82, 0.36)
SPAIN_C = "#c8102e"

# ---- geography ----------------------------------------------------------
_pts, _lab = sea_route(_RD.ROUTE)
ROUTE = Route(_pts, _lab)
KM = ROUTE.km
SPAIN = country("ESP", min_area=0.05)
PHIL = country("PHL", min_area=0.01)

STOPS = ["tenerife", "rio", "plata", "san_julian", "guam", "homonhon", "brunei", "timor", "cape", "cape_verde"]
TIDORE = tuple(ROUTE.ll[_lab["tidore"]])
MACTAN = tuple(ROUTE.ll[_lab["mactan"]])

# ---- key times (all derived from words) ---------------------------------
T = dict(
    date1=w("20"), year1=w("1519"),
    ships=w("Beş"), sail=w("yola"),
    target=w("Hedef"), spice=w("Baharat"),
    atlantic=w("Atlantik"), found=w("buluyorlar"),
    strait_title=w("Macellan"),
    then=w("Sonra"), pacific=w("Pasifik"), three=w("Üç"),
    april=w("Nisan"), phil=w("Filipinler"), killed=w("öldürülüyor"),
    juan=w("Juan"), elcano=w("Elcano"), done=w("tamamlıyor"),
    date3=w("6"), victoria=w("Victoria"), spain=w("İspanya"), back=w("dönüyor"),
    inside=w("İçinde"), only=w("sadece"), n18=w("18"),
    world=w("Dünyayı"), finished=w("tamamlanmıştı"),
    calendar=w("takvimleri"), oneday=w("bir gün"), behind=w("geriydi"),
)
T["intro_x"] = (T["year1"] + 0.75, T["ships"] - 0.15)        # globe -> map crossfade
T["fly_spice"] = (T["target"] - 0.15, T["spice"] + 0.75)
T["fly_back"] = (T["atlantic"] - 0.2, T["atlantic"] + 1.7)
T["to_strait"] = (T["found"] + 0.1, T["found"] + 1.3)
T["to_pacific"] = (T["then"] + 0.1, T["pacific"] - 0.15)
T["to_phil"] = (T["three"] + 3.0, T["april"] + 1.2)
T["to_sea"] = (T["killed"] + 0.9, T["juan"] + 0.2)
T["follow_home"] = (T["done"] + 1.0, T["back"] + 0.5)
T["outro_x"] = (T["world"] - 0.1, T["world"] + 1.4)           # map -> globe

# ---- fleet progress (km along the route) ----------------------------------
FLEET = Timeline([
    (T["sail"] - 0.1, 0, True),
    (T["fly_spice"][1] + 0.3, KM("tenerife")),
    (T["fly_back"][1], KM("rio")),
    (T["found"] + 0.35, KM("san_julian")),
    (T["to_strait"][1] - 0.1, KM("strait_e")),
    (T["strait_title"] + 0.8, KM("froward")),
    (T["to_pacific"][0] + 0.9, KM("strait_w")),
    (T["to_phil"][0] + 0.1, KM("guam")),
    (T["to_phil"][1] - 0.2, KM("homonhon")),
    (T["phil"] + 0.3, KM("mactan"), True),
    (T["killed"] + 0.6, KM("mactan"), True),
    (T["juan"] + 0.3, KM("brunei")),
    (T["done"] + 0.6, KM("tidore"), True),
    (T["done"] + 1.0, KM("tidore"), True),
    (T["date3"] + 1.2, KM("timor")),
    (T["victoria"] - 0.2, KM("cape")),
    (T["spain"] - 0.3, KM("cape_verde")),
    (T["back"] + 0.4, KM("sanlucar_end"), True),
])
_tt = np.arange(0, 80, 0.01)
_ss = np.array([FLEET(x) for x in _tt])


def time_at_km(km):
    i = int(np.searchsorted(_ss, km))
    return float(_tt[min(i, len(_tt) - 1)])


T_LOSS = {
    4: time_at_km(KM("san_julian")),        # Santiago sinks
    3: time_at_km(KM("froward")),           # San Antonio turns back
    2: T["killed"] + 0.8,                   # Concepción burnt
    1: T["done"] + 1.0,                     # Trinidad stays at Tidore
}

# ---- views ---------------------------------------------------------------
def view_ll(lon, lat, w_deg):
    x, y = merc(lon, lat)
    return View(float(x), float(y), w_deg / 360.0)


V_SP = view_ll(-5.0, 38.0, 26)
V_SPICE = view_ll(127.4, -1.0, 34)
V_STRAIT = view_ll(-71.6, -53.05, 8.6)
V_PAC = view_ll(-147, -8, 165)
V_PH = view_ll(-235.4, 10.4, 15)
V_SEA = view_ll(-239.0, 4.8, 29)
V_SP2 = View(V_SP.cx - 1.0, V_SP.cy, 24 / 360)

# globe parameters
GLOBE_CY = H * 0.53
R_FINAL = 440


def fleet_view(t, w_deg):
    x, y = ROUTE.merc_at(FLEET(t))
    # look slightly ahead along the route for a calmer follow
    x2, y2 = ROUTE.merc_at(FLEET(t + 0.35))
    return View((x + x2) / 2, (y + y2) / 2, w_deg / 360.0)


def _intro_globe(t):
    """(lon0, lat0, R) for the opening globe shot."""
    lo_sp, la_sp = V_SP.lonlat()
    p = E.prog(t, 0.0, T["intro_x"][1], E.in_out_cubic)
    lon0 = 32 + (lo_sp - 32) * p
    lat0 = 12 + (la_sp - 12) * p
    Rm = R_for_view(W, V_SP.w, la_sp)
    z = E.prog(t, 0.5, T["intro_x"][1], E.in_out_quint)
    R = math.exp(math.log(400) + (math.log(Rm) - math.log(400)) * z)
    return lon0, lat0, R


def _comet_km(t):
    return ROUTE.total * E.prog(t, T["outro_x"][1] - 0.3, T["calendar"] - 0.2, E.in_out_sine)


def _outro_globe(t):
    lo_sp, la_sp = V_SP.lonlat()
    R_start = R_for_view(W, V_SP2.w * 1.06, la_sp)
    z = E.prog(t, T["outro_x"][0], T["outro_x"][1] + 0.4, E.in_out_cubic)
    R = math.exp(math.log(R_start) + (math.log(R_FINAL) - math.log(R_start)) * z)
    lon_c, lat_c = ROUTE.lonlat_at(_comet_km(t))
    f = E.prog(t, T["outro_x"][0] + 0.2, T["outro_x"][1] + 0.5, E.smooth)
    lon0 = lo_sp + (lon_c + 18 - lo_sp) * f          # keep comet a bit right of centre
    lat0 = la_sp + (lat_c * 0.45 + 10 - la_sp) * f
    # gentle drift once the loop is done
    lon0 -= 6 * max(0.0, t - T["calendar"])
    return lon0, lat0, R


def globe_alpha(t):
    a_in = 1 - E.prog(t, *T["intro_x"], E.smooth)
    a_out = E.prog(t, T["outro_x"][0] + 0.15, T["outro_x"][0] + 0.85, E.smooth)
    return max(a_in, a_out)


def globe_state(t):
    if t < T["intro_x"][1] + 0.01:
        lon0, lat0, R = _intro_globe(t)
    else:
        lon0, lat0, R = _outro_globe(t)
    return lon0, lat0, R


def basemap_visible(t):
    return globe_alpha(t) < 0.999


# ---- camera ----------------------------------------------------------------
def _globe_matched_view(t):
    lon0, lat0, R = globe_state(t)
    x, y = merc(lon0, lat0)
    # globe centre is at GLOBE_CY, flat map centre at H/2 -> shift map
    wv = w_for_R(W, R, lat0)
    return View(float(x), float(y) + (H / 2 - GLOBE_CY) * wv / W, wv)


cam = CameraPath(_globe_matched_view(0))
cam.custom(0, T["intro_x"][1], _globe_matched_view)
cam.drift(T["intro_x"][1], T["fly_spice"][0], zoom=1.07)
cam.fly(*T["fly_spice"], V_SPICE, rho=1.25, max_w=0.52)
cam.drift(T["fly_spice"][1], T["fly_back"][0], zoom=1.04)
cam.fly(*T["fly_back"], fleet_view(T["fly_back"][1], 52), rho=1.25, max_w=0.52)
cam.custom(T["fly_back"][1], T["to_strait"][0],
           lambda t: fleet_view(t, 52 - 22 * E.prog(t, T["fly_back"][1], T["to_strait"][0], E.smooth)))
cam.move(*T["to_strait"], V_STRAIT, ease=E.in_out_cubic)
cam.drift(T["to_strait"][1], T["to_pacific"][0], zoom=1.06, dx=-0.08)
cam.fly(*T["to_pacific"], V_PAC, ease=E.in_out_cubic, rho=1.0)
cam.drift(T["to_pacific"][1], T["to_phil"][0], zoom=1.05, dx=-0.05)
cam.fly(*T["to_phil"], V_PH, rho=1.1)
cam.drift(T["to_phil"][1], T["to_sea"][0], zoom=1.05)
cam.move(*T["to_sea"], V_SEA, ease=E.in_out_cubic)
cam.drift(T["to_sea"][1], T["follow_home"][0], zoom=1.03)
_V_SEA_END = cam.last


def _home_follow(t):
    t0, t1 = T["follow_home"]
    p = (t - t0) / (t1 - t0)
    wdeg = 34 + 30 * math.sin(math.pi * min(1, max(0, p))) ** 0.8
    fv = fleet_view(t, wdeg)
    a = E.prog(t, t0, t0 + 1.0, E.in_out_cubic)
    b = E.prog(t, t1 - 1.1, t1, E.in_out_cubic)
    v = _lerp_view(_V_SEA_END, fv, a)
    return _lerp_view(v, V_SP2, b)


cam.custom(*T["follow_home"], _home_follow, end=V_SP2)
cam.drift(T["follow_home"][1], T["outro_x"][0], zoom=1.06)
_V_PRE_OUT = cam.last


def _outro_view(t):
    return _globe_matched_view(t) if t > T["outro_x"][0] else _V_PRE_OUT


cam.custom(T["outro_x"][0], DURATION, _outro_view)


def camera(t):
    return cam(t)


# ---- per-worker state --------------------------------------------------------
def setup():
    from mapengine.geo import all_borders
    return dict(borders=all_borders(), globe=Globe(W, H))


# ---- helpers -------------------------------------------------------------------
def ship_size(fr):
    wdeg = fr.view.w * 360
    return float(np.interp(wdeg, [10, 40, 170], [54, 46, 34]))


FORMATION = [(16, 2), (-20, -20), (-22, 22), (-56, -4), (-60, 30)]


def facing_at(d):
    h = ROUTE.heading_merc(d, window=500)
    n = math.hypot(*h) or 1
    return math.tanh(5 * h[0] / n)


# ---- main draw -------------------------------------------------------------------
def draw(fr, st):
    t = fr.t
    c = fr.ctx
    ga = globe_alpha(t)
    d = FLEET(t)

    if ga < 1:
        fr.grade(darken=0.2, desat=0.18)
        fr.borders(st["borders"], alpha=0.12)

        # Spain at start and at the end
        sa = max(E.window(t, T["ships"] - 0.2, T["fly_spice"][0] + 0.8, 0.6, 0.6),
                 E.window(t, T["back"] - 0.3, T["outro_x"][0] + 0.6, 0.6, 0.5))
        if sa > 0:
            rings = fr.screen_rings(fx.wrap_rings(fr, SPAIN.merc_rings))
            fr.fill_tint(rings, SPAIN_C, 0.75 * sa, solid=0.35)
            fr.stroke(rings, 2.5, "#ffffff", 0.9 * sa)
        pa = E.window(t, T["to_phil"][1] - 0.6, T["to_sea"][1], 0.6, 0.8)
        if pa > 0:
            rings = fr.screen_rings(fx.wrap_rings(fr, PHIL.merc_rings))
            fr.fill_tint(rings, "#e8a33d", 0.55 * pa, solid=0.3)
            fr.stroke(rings, 1.6, "#ffffff", 0.6 * pa)

        # sailed route
        fx.route_progress(fr, ROUTE, d)

        # stop dots
        for name in STOPS:
            kd = KM(name)
            if d >= kd:
                a = E.prog(d - kd, 0, 300)
                x, y = fx.ll_screen(fr, *ROUTE.ll[_lab[name]])
                c.set_source_rgba(1, 1, 1, 0.95 * a)
                c.arc(x, y, 5.5, 0, 6.283)
                c.fill()

        # spice islands pin (target), again when reached
        for t0, t1 in ((T["spice"] - 0.2, T["fly_back"][0] + 0.7), (T["juan"], T["follow_home"][0] + 1.5)):
            pa = E.window(t, t0, t1, 0.2, 0.5)
            if pa > 0:
                x, y = fx.ll_screen(fr, *TIDORE)
                draw_pin(c, x, y, t, t0, color=GOLD, size=1.3, alpha=pa)
        rv, al, dy = title_anim(t, T["spice"] + 0.1, T["fly_back"][0] + 0.5)
        if al > 0:
            x, y = fx.ll_screen(fr, *TIDORE)
            draw_text(c, "BAHARAT ADALARI", x, y + 74 + dy, size=46, weight="ExtraBold",
                      alpha=al, reveal=rv, tracking=0.08)

        # ships
        sz = ship_size(fr)
        face = facing_at(d)
        lead = None
        items = []
        for i in range(5):
            di, al, dy, burn, fi = d, 1.0, 0.0, 0.0, face
            pop = E.prog(t, T["ships"] + 0.13 * i, T["ships"] + 0.13 * i + 0.45)
            al = min(al, pop)
            sc = 0.5 + 0.5 * E.out_back(pop, 2.0)
            tl = T_LOSS.get(i)
            if tl is not None and t > tl:
                if i == 4:    # sinks
                    q = E.prog(t, tl, tl + 1.0)
                    al *= 1 - q
                    dy = 14 * q
                    di = KM("san_julian")
                elif i == 3:  # turns back
                    di = KM("froward") - 0.6 * (d - KM("froward"))
                    fi = -face if abs(face) > 0.2 else 1.0
                    al *= 1 - E.prog(t, tl + 0.3, tl + 1.4)
                elif i == 2:  # burnt
                    di = KM("mactan")
                    burn = E.prog(t, tl, tl + 0.5)
                    al *= 1 - E.prog(t, tl + 0.6, tl + 1.5)
                elif i == 1:  # stays
                    di = KM("tidore")
                    fi = facing_at(di)
                    al *= 1 - E.prog(t, tl + 0.8, tl + 1.8)
            if al <= 0.01:
                continue
            mx, my = ROUTE.merc_at(di)
            k = fr.nearest_copy(float(mx))
            x, y = fr.pt(float(mx) + k, float(my))
            ox, oy = FORMATION[i]
            items.append((y + oy, x + ox * (1 if fi >= 0 else -1) * sz / 46, y + oy * sz / 46 + dy,
                          sz * sc, fi, al, i, burn))
            if i == 0:
                lead = (x, y)
        for _, x, y, s_, fi, al, i, burn in sorted(items):
            if burn > 0:
                import cairo
                g = cairo.RadialGradient(x, y - s_ * 0.4, 0, x, y - s_ * 0.4, s_ * 1.3)
                g.add_color_stop_rgba(0, 1.0, 0.55, 0.1, 0.6 * al * burn)
                g.add_color_stop_rgba(1, 1.0, 0.3, 0.0, 0)
                c.set_source(g)
                c.arc(x, y - s_ * 0.4, s_ * 1.3, 0, 6.283)
                c.fill()
            draw_ship(c, x, y, s_, fi, al, t, phase=i * 1.7, burn=burn)

        # Magellan killed at Mactan
        ka = E.window(t, T["killed"] - 0.05, T["to_sea"][1], 0.1, 0.6)
        if ka > 0:
            x, y = fx.ll_screen(fr, *MACTAN)
            c.push_group()
            fx.cross_marker(c, x + 64, y - 110, t, T["killed"] - 0.05)
            c.pop_group_to_source()
            c.paint_with_alpha(ka)

        # Victoria label
        rv, al, dy = title_anim(t, T["victoria"], T["back"] + 1.0)
        if al > 0 and lead:
            draw_text(c, "VICTORIA", lead[0], lead[1] - sz * 1.55 + dy, size=38, weight="ExtraBold",
                      alpha=al, reveal=rv, tracking=0.14)

        fr.vignette(0.5)

    # ---- globe layer
    if ga > 0:
        G = st["globe"]
        lon0, lat0, R = globe_state(t)
        gs = (lon0, lat0, R, W / 2, GLOBE_CY)
        c.push_group()
        G.draw_space(c, t)
        G.draw(c, gs)
        fr.grade(darken=0.12, desat=0.1)
        if t > T["outro_x"][0]:
            ll = ROUTE.ll
            G.polyline(c, ll[:, 0], ll[:, 1], gs, 9, (*GOLD, 0.18))
            G.polyline(c, ll[:, 0], ll[:, 1], gs, 4, (*GOLD, 0.95))
            ck = _comet_km(t)
            if 0 < ck < ROUTE.total:
                seg = ROUTE.lonlat_upto(ck, max(0, ck - 3500))
                G.polyline(c, seg[:, 0], seg[:, 1], gs, 10, (1, 1, 1, 0.25))
                G.polyline(c, seg[:, 0], seg[:, 1], gs, 5, (1, 0.97, 0.85, 1.0))
            lo, la = ROUTE.lonlat_at(ck)
            x, y, z = G.project(lo, la, gs)
            if z > 0.05:
                draw_ship(c, float(x), float(y) - 4, 50, -1.0, min(1, float(z) * 4), t)
        c.pop_group_to_source()
        c.paint_with_alpha(ga)

    # ---- titles (screen space, minimal)
    fx.date_title(c, t, "20 EYLÜL", "1519", T["date1"] + 0.1, T["ships"] + 0.2)
    rv, al, dy = title_anim(t, T["ships"] + 0.5, T["target"] - 0.2)
    draw_text(c, "5 GEMİ  ·  270 DENİZCİ", W / 2, 330 + dy, size=50, weight="ExtraBold", alpha=al,
              reveal=rv, tracking=0.06)
    rv, al, dy = title_anim(t, T["strait_title"], T["then"] + 0.3)
    draw_text(c, "MACELLAN", W / 2, 290 + dy, size=104, weight="Black", alpha=al, reveal=rv, tracking=0.1)
    rv2, _, _ = title_anim(t, T["strait_title"] + 0.15, T["then"] + 0.3)
    draw_text(c, "BOĞAZI", W / 2, 395 + dy, size=60, weight="ExtraBold", alpha=al, reveal=rv2, tracking=0.32)
    rv, al, dy = title_anim(t, T["pacific"] - 0.05, T["to_phil"][0] + 0.4)
    draw_text(c, "PASİFİK", W / 2, 300 + dy, size=120, weight="Black", alpha=al, reveal=rv, tracking=0.22)
    rv, al, dy = title_anim(t, T["three"], T["to_phil"][0] + 0.4)
    if al > 0:
        frac = (d - KM("strait_w")) / (KM("guam") - KM("strait_w"))
        days = int(round(98 * min(1, max(0, frac))))
        draw_text(c, f"{days} GÜN", W / 2, 420 + dy, size=64, weight="ExtraBold", alpha=al,
                  reveal=rv, tracking=0.08, color=(255, 210, 92))
    fx.date_title(c, t, "NİSAN", "1521", T["april"], T["to_sea"][0] + 0.3)
    rv, al, dy = title_anim(t, T["juan"] - 0.1, T["date3"] - 0.4)
    draw_text(c, "JUAN SEBASTIÁN", W / 2, 240 + dy, size=46, weight="SemiBold", alpha=al, reveal=rv, tracking=0.18)
    rv2, _, _ = title_anim(t, T["elcano"] - 0.15, T["date3"] - 0.4)
    draw_text(c, "ELCANO", W / 2, 335 + dy, size=120, weight="Black", alpha=al, reveal=rv2, tracking=0.12)
    fx.date_title(c, t, "6 EYLÜL", "1522", T["date3"], T["victoria"] - 0.3)

    # 270 -> 18
    rv, al, dy = title_anim(t, T["only"] - 0.25, T["world"] + 0.2)
    if al > 0:
        q = E.prog(t, T["only"] - 0.1, T["n18"] + 0.05, E.out_cubic)
        n = int(round(270 + (18 - 270) * q))
        pop = 1 + 0.08 * math.sin(math.pi * E.prog(t, T["n18"], T["n18"] + 0.35))
        draw_text(c, str(n), W / 2, 330 + dy, size=200, weight="Black", alpha=al, scale=pop,
                  color=(255, 210, 92) if q >= 1 else (255, 255, 255), tracking=0.02)
        draw_text(c, "KİŞİ", W / 2, 470 + dy, size=56, weight="ExtraBold", alpha=al, reveal=rv, tracking=0.3)

    # finale: first circumnavigation + one day lost
    fx.calendar(c, t, T["calendar"] - 0.35, T["oneday"], "TEMMUZ", 9, 10, W / 2, 300)
    rv, al, dy = title_anim(t, T["behind"] - 0.1, DURATION + 1)
    draw_text(c, "−1 GÜN", W / 2, 510 + dy, size=96, weight="Black", alpha=al, reveal=rv,
              tracking=0.06, color=(255, 210, 92))

    fade = max(1 - E.prog(t, 0, 0.4), E.prog(t, DURATION - 0.5, DURATION))
    if fade > 0:
        c.set_source_rgba(0, 0, 0, fade)
        c.paint()


# ---- audio ---------------------------------------------------------------------
def _sfx():
    ev = []

    def wh(a, b, g=0.5):
        ev.append((a - 0.1, "whoosh", dict(dur=(b - a) + 0.35, gain=g)))
    wh(0.2, T["intro_x"][1], 0.4)
    wh(*T["fly_spice"], 0.6)
    wh(*T["fly_back"], 0.6)
    wh(*T["to_strait"], 0.35)
    wh(*T["to_pacific"], 0.55)
    wh(*T["to_phil"], 0.5)
    wh(*T["to_sea"], 0.3)
    wh(T["follow_home"][0], T["follow_home"][0] + 2.5, 0.35)
    wh(T["follow_home"][1] - 2.5, T["follow_home"][1], 0.4)
    wh(*T["outro_x"], 0.55)
    for i in range(5):
        ev.append((T["ships"] + 0.13 * i, "pop", dict(gain=0.22, f0=520 + 40 * i, f1=200)))
    ev.append((T["spice"] - 0.2, "shimmer", dict(gain=0.2)))
    ev.append((T["juan"], "shimmer", dict(gain=0.15)))
    ev.append((T_LOSS[4], "thump", dict(gain=0.25)))
    ev.append((T["killed"] - 0.05, "thump", dict(gain=0.6)))
    ev.append((T["back"] + 0.4, "thump", dict(gain=0.4)))
    ev.append((T["n18"], "pop", dict(gain=0.45)))
    ev.append((T["oneday"], "swish", dict(gain=0.3)))
    ev.append((T["behind"], "shimmer", dict(gain=0.22)))
    for key in ("year1", "strait_title", "pacific", "april", "elcano", "date3"):
        ev.append((T[key], "swish", dict(gain=0.18)))
    return ev


SFX = _sfx()
