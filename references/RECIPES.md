# Recipes - map a narration beat to a visual

Each recipe lists the narration pattern, the visual, and code. Times come from
`w("word")`. `examples/` contains complete working versions.

## 1. Globe intro -> map (hook)
*"In 1519..." / first sentence.* Spinning globe zooms into the first place, then
cross-fades into the satellite map at exactly the same scale.
See `templates/scene_template.py`: `globe_state`, `globe_alpha`, `basemap_visible`,
`cam.custom(0, T_INTRO_END, _globe_view)`, draw globe in a `push_group` with alpha.

## 2. Fly to a place + reveal
*"...Türkiye..."*
```python
cam.fly(w("Türkiye") - 0.2, w("Türkiye") + 1.8, View.fit(TUR.bbox_merc(), W, H, pad=0.14))
border = E.prog(t, t0, t0 + 1.2, E.in_out_cubic); fill = E.prog(t, t0 + .6, t0 + 1.4)
rings = fx.highlight(fr, TUR, "#9e1010", fill, border=border)
fx.flag_fill(fr, rings, "tr", wipe=E.prog(t, t1, t1 + .8, E.in_out_cubic))   # optional
fx.title(c, t, "TÜRKİYE", t0, t_next)
```

## 3. Size comparison / "true size" drag
*"Put Turkey over Germany..."* The hero shape lifts (shadow + scale 1.035), travels
with the camera, and lands on the target; its map size changes with latitude because
`Shape.moved_to(lon, lat)` re-projects it on the sphere. Target in yellow underneath,
its outline drawn on top; hero flag at 70 % alpha. Ripple on landing.
Full code: `examples/turkiye_gercek_boyut/scene.py` (`turkey_pos`, `lift_amount`).

## 4. Voyage / expedition (ships)
*"Five ships set sail..."* Waypoints -> `sea_route` -> `Route`; fleet position
`Timeline([(t, km, stop)...])` keyed to words; route drawn up to the fleet
(`fx.route_progress`); camera `custom` follow or region views; ships formation with
`draw_ship`; stop dots appear as passed. Losses: sink (fade + dy), turn back
(own distance decreasing), burn (`burn=` tint + orange glow), stay behind (fixed km).
Full code: `examples/macellan/scene.py`.

## 5. Movement on land / air / attack / migration / trade
*"The Mongols swept west..." / "flights from Istanbul to..."*
`fx.arc(fr, a.centroid, b.centroid, progress, color, bend=0.2)` - several arcs staggered
by 0.15 s for "spreading"; dashed (`dash=[14, 10]`) for planned/unsuccessful moves.
For an army along a real path: plain lon/lat list -> `Route` -> moving `fx.dot` or icon.

## 6. Territory / empire growth
*"By 1683 the empire stretched from..."* Several `country()`/`admin1()` shapes or
`union()`; reveal them one after another (border draw-on 0.4 s apart) in the same colour,
camera `move`s out to fit the union (`View.fit(union.bbox_merc(), ...)`).
Historical borders that don't exist in Natural Earth: build a `Shape([[(lon, lat), ...]])`
polygon from researched coordinates (keep it approximate, smooth with few points).

## 7. Dates
*"20 Eylül 1519"* -> `fx.date_title(c, t, "20 EYLÜL", "1519", w("20"), next_beat)`.

## 8. Numbers
*"...270 sailors... only 18..."* -> `fx.counter(c, t, w("sadece"), w("18"), 270, 18, suffix="")`
with a `pop` SFX on landing. Units small: `suffix=" km²"`.

## 9. Durations / waiting
*"For three months they saw no land"* -> wide view + day counter driven by progress
(`days = 98 * frac`), slow drift; nothing else.

## 10. Death / battle / disaster at a place
`fx.cross_marker` (death), `fx.burst_marker` (battle/explosion) at `fx.ll_screen(...)`,
offset so it does not cover icons; `thump` SFX on the word.

## 11. Explaining a concept (projection distortion, time zones, date line...)
Use geometry rather than words: graticule (`fr.graticule`), ghost outlines (dashed
`fr.stroke(..., dash=[12, 9])`), moving shapes, calendar flip (`fx.calendar`).

## 12. Finale
Zoom out to the globe (`state_for_view` -> `zoom_state` to R≈440) showing the whole
story at once (full route, all highlighted areas), optional comet light running along the
route, last number/claim as one short title.
