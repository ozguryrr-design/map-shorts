# mapengine API reference

Coordinates: lon/lat in degrees; internally normalized Web Mercator
(`x` 0..1 west->east, `y` 0..1 north->south). Longitudes may be **unwrapped**
(e.g. -235 = 125E one world to the west) so a route around the world stays
continuous; the renderer draws world copies automatically.
Screen: 1080x1920, origin top-left.

## Scene module contract (`projects/<name>/scene.py`)
| name | required | meaning |
|---|---|---|
| `W, H, FPS, DURATION` | yes | 1080, 1920, 60, seconds |
| `camera(t) -> View` | yes | flat-map camera |
| `setup() -> state` | yes | per worker (load borders, Globe...) |
| `draw(fr, state)` | yes | draws everything on top of the basemap |
| `basemap_visible(t)` | no | return False when the globe covers the frame (faster) |
| `VO = [(path, start)]` | no | voice clips, relative to project |
| `SFX = [(t, kind, kwargs)]` | no | procedural sound effects |
| `MUSIC = (path, gain_db)` | no | background bed, looped |
| `TILE_PROVIDER`, `MAX_LEVEL` | no | `"esri"` (default) or `"s2"`, max tile zoom (10) |

## timing — `from mapengine.timing import Words, find_vo`
* `VW = Words(path_words_json, offset=0.4)`; `VW.at("Pasifik")` start time (prefix match,
  case/Turkish-insensitive, apostrophe suffixes ignored); `VW.at("beş", 2)` 2nd occurrence;
  `VW.at("bir gün")` phrases; `VW.end(...)`; `VW.sentence(i)` -> (start, end); `VW.n_sentences`;
  `VW.last_end`.
* `find_vo(project_dir)` -> `"vo/voice.mp3"` if present else placeholder.

## ease — `from mapengine import ease as E`
`linear smooth smoother in_out_cubic in_out_quint in_out_sine out_cubic out_quint out_expo
in_cubic out_back(t, s) in_out_expo`; `E.prog(t, t0, t1, ease)` -> 0..1;
`E.window(t, t_in, t_out, fade_in, fade_out)` -> 0..1..0; `E.lerp`.

## geo — `from mapengine.geo import ...`
* `country(code_or_name, min_area=0.002)` -> `Shape` (`"TUR"`, `"Almanya"`, `"Germany"`).
* `admin1(name, adm0_a3=None)` states/provinces (`admin1("Texas","USA")`).
* `find_country(q)`, `find_admin1(q)` -> candidate codes; `union(*shapes)`.
* `Shape`: `.rings` (lon/lat), `.merc_rings`, `.centroid` (lon, lat), `.bbox_merc()`,
  `.moved_to(lon, lat)` -> mercator rings of the shape moved on the sphere (true size).
* `merc(lon, lat)`, `inv_merc(x, y)`, `all_borders()` (faint context layer).

## camera — `from mapengine.camera import View, CameraPath`
* `View(cx, cy, w)` (w = visible width in mercator units, 1.0 = whole world);
  `View.at(lon, lat, width_deg)`; `View.fit(bbox_merc, W, H, pad=0.12, offset_y=0)`;
  `.zoomed(f)`; `.lonlat()`.
* `cam = CameraPath(start_view)` then sequential segments (each starts from the previous end):
  * `.fly(t0, t1, view, ease=in_out_cubic, rho=1.35, max_w=None)` — optimal zoom-out/pan/zoom-in
    (van Wijk). Use for any long distance. `max_w≈0.52` keeps portrait frames inside the map.
  * `.move(t0, t1, view, ease)` — direct move (short distances / pure zooms).
  * `.drift(t0, t1, zoom=1.04, dx=0, dy=0)` — slow push-in; use between all events.
  * `.custom(t0, t1, fn)` — `fn(t) -> View` (follow a ship, globe-matched view...).
  * `cam(t)`; `cam.last` = view at the end of the last segment.

## draw.Frame `fr` (passed to `draw`)
`fr.t, fr.ctx (cairo), fr.view, fr.W, fr.H`
* `fr.screen_rings(merc_rings, xform=None)` project + cull.
* `fr.fill_tint(rings, color, alpha, solid=0.45)` textured colour (relief stays visible).
* `fr.fill_solid`, `fr.fill_with(rings, painter, alpha, clip_circle)`.
* `fr.stroke(rings, width, color, alpha, progress, dash)`; `fr.glow_stroke(...)` (progress = draw-on).
* `fr.shadow(rings, dx, dy, blur, alpha)` soft drop shadow (for "lifted" shapes).
* `fr.grade(darken, desat)`, `fr.vignette(s)`, `fr.borders(all_borders(), alpha)`,
  `fr.graticule(alpha, step)`, `fr.pt(mx, my)`, `fr.nearest_copy(mx)`, `fr.world_copies()`.
* `mapengine.draw.scale_about(cx, cy, k)` -> xform for screen rings; `rings_bbox(rings)`.

## fx — `from mapengine import fx`
* `fx.highlight(fr, shape, color, alpha, border=0..1, solid=0.4)` -> screen rings.
* `fx.flag_fill(fr, screen_rings, "tr", alpha, wipe=0..1)` flag clipped to the shape (flagcdn PNG).
  `fx.flag("de")` painter. Vector Turkish flag: `mapengine.text.flag_turkey`.
* `fx.polyline(fr, merc_pts, color, width, alpha)`; `fx.route_progress(fr, route, km)`.
* `fx.arc(fr, a_ll, b_ll, progress, color, width, bend=0.22, arrow=True, dash=None)`.
* `fx.ll_screen(fr, lon, lat)`, `fx.wrap_rings(fr, merc_rings)`.
* Markers: `fx.dot`, `fx.cross_marker(c, x, y, t, t0)`, `fx.burst_marker(...)`,
  `mapengine.route.draw_pin(c, x, y, t, t0, color, size)`.
* Text: `fx.title(c, t, text, t_in, t_out, y=300, size=110)`,
  `fx.title_sub(c, t, big, small, t_in, t_out, small_above=False, accent=False)`,
  `fx.date_title(c, t, "20 EYLÜL", "1519", t_in, t_out)`,
  `fx.counter(c, t, t0, t1, v0, v1, suffix=" km²", t_out=..)`,
  `fx.map_label(fr, text, lon, lat, t, t_in, t_out)`,
  `fx.calendar(c, t, t_in, t_flip, "TEMMUZ", 9, 10)`.
  Low level: `mapengine.text.draw_text(c, text, x, y, size, weight, alpha, scale, reveal,
  tracking, color)`, `title_anim(t, t_in, t_out)` -> (reveal, alpha, dy).
  Fonts: Montserrat `SemiBold | Bold | ExtraBold | Black`.

## routes — `from mapengine.route import Route, Timeline, draw_ship, draw_pin`
`from mapengine.seapath import sea_route`
* `pts, labels = sea_route([(lon, lat, "label"?), ...])` — A* around land, smoothed, cached.
  Put waypoints in water; for straits add a few waypoints inside the channel.
* `route = Route(pts, labels)`: `.km(label)`, `.total`, `.merc_at(km)`, `.lonlat_at(km)`,
  `.merc_upto(km)`, `.lonlat_upto(km)`, `.heading_merc(km)`.
* `Timeline([(t, value, stop_bool), ...])(t)` — smooth monotone motion; `stop=True` = rest.
* `draw_ship(c, x, y, size, facing(-1..1), alpha, t, phase, burn)` caravel icon.
* For land/air movement use `fx.arc` or a `Route` built from plain lon/lat points.

## globe — `from mapengine.globe import Globe, zoom_state, matched_view, state_for_view, R_for_view`
* `G = Globe(W, H)` (in `setup`); `G.draw_space(c, t)`, `G.draw(c, (lon0, lat0, R, cx, cy), alpha)`,
  `G.project(lon, lat, state)` -> x, y, z (z>0 visible), `G.polyline(c, lons, lats, state, width, rgba)`.
* `zoom_state(t, t0, t1, (lon, lat, R)a, b, ease)` log-zoom interpolation.
* `matched_view(W, H, lon0, lat0, R, globe_cy)` flat View equal to the globe -> use as camera
  while cross-fading; `state_for_view(W, H, view, globe_cy)` the inverse (for outros).
  Pattern: see `templates/scene_template.py` (`globe_alpha`, `basemap_visible`).

## audio — `mapengine/audio.py`
SFX kinds: `whoosh(dur, gain, f0, f1, peak)`, `swish(dur, gain)`, `pop(gain, f0, f1)`,
`thump(gain)`, `shimmer(gain)`. Mix: voice + SFX (−6 dB) (+ music), loudness −14 LUFS.

## CLI — `make.py`
`new, tts, align, words, find, stills, sheet, render, final` (see `make.py -h`).
