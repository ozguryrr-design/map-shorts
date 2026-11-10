---
name: map-shorts
description: >-
  Turn a narration (voiceover text or audio, any topic with a geographic angle:
  history, voyages, wars, empires, borders, country comparisons, migrations,
  "true size" facts...) into a fluid, professional vertical map video
  (YouTube Shorts / Reels / TikTok, 1080x1920 60fps) with satellite imagery,
  cinematic camera flights, a 3D globe, animated borders, routes, ships, flags,
  counters, minimal titles and sound design - then render it with ffmpeg.
  Use when the user gives a script/voiceover and wants a map animation video.
---

# map-shorts - narrated map animation videos

You (the agent) are the director **and** the animator. The user gives a narration
(text, and later or immediately an audio voiceover). You plan the visuals beat by
beat, write a `scene.py` with the `mapengine` Python library in this folder,
check preview frames, and render the final MP4. The look to match is
`examples/macellan` and `examples/turkiye_gercek_boyut`: dark satellite map,
glowing white borders, tinted textured countries, gold routes, smooth camera
flights, very little text.

All commands run from this skill's folder with its virtualenv:
`.venv/bin/python make.py ...`.
**Windows (native, no WSL needed):** the venv python is `.venv\Scripts\python.exe` -
in PowerShell `.venv\Scripts\python make.py ...`, in Git Bash `.venv/Scripts/python make.py ...`.
Substitute it in every command below.

## 0. One-time setup
```bash
bash scripts/setup.sh        # venv, python deps, Natural Earth data, fonts (Linux/macOS/WSL/Git Bash)
```
```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1 -InstallFfmpeg   # Windows PowerShell
```
Requires: Python 3.10+, ffmpeg, cairo (system library; on Windows pycairo's pip wheel
bundles it). The script tells you what is missing. Network access is needed (tiles,
data, placeholder TTS). On Windows, if ffmpeg was just installed, a new terminal may
be needed before `ffmpeg` is on PATH.

## 1. Create the project and get word timings
```bash
.venv/bin/python make.py new <name> --text-str "<full narration>"   # or --text file.txt
```
Then timings - every animation is bound to words of the voiceover:
* **User already has the voiceover** -> copy it to `projects/<name>/vo/voice.mp3`, then
  `.venv/bin/python make.py align <name>` (faster-whisper; snaps to the script words).
* **No voiceover yet** -> `.venv/bin/python make.py tts <name>` creates a placeholder
  voice (edge-tts, `--voice tr-TR-AhmetNeural`, `en-US-GuyNeural`, ...) and timings.
  When the real voice arrives later: put `vo/voice.mp3`, run `align`, re-render.
  Nothing else changes, because cues are words, not seconds.

`.venv/bin/python make.py words <name>` prints sentence and word times.

## 2. Plan the storyboard (write it down before coding)
Read the narration and make a beat table: one row per sentence/phrase.
| anchor word | what the viewer must understand | map action | on-screen text (<=3 words) |

Pick, for every beat, a visual from `references/RECIPES.md` (fly-to + reveal,
true-size drag, voyage with ships, arrow arc, counter, date title, death/battle
marker, globe intro/outro, calendar...). Rules from `references/STYLE.md`:
* the image tells the story; text only for names, dates, numbers
* something always moves (drift between flights), a new visual event every 2-4 s
* every change starts **on** its word: `w("Pasifik")`, `w("Pasifik") - 0.15` for camera
* open with a hook in the first second (globe spin + zoom, or immediate flight)
* keep titles in y 220-520; keep the bottom 25% and right 10% clear (Shorts UI)

Research geography you are unsure of (coordinates of ports, battle sites, routes,
historical borders). Use `.venv/bin/python make.py find <name>` to get country /
state codes (accepts Turkish/English/other names).

## 3. Write `projects/<name>/scene.py`
Start from the generated template (already runnable). The API is in
`references/API.md`; copy patterns from the two examples. Key pieces:
* `VW = Words(...)`, `w("word")`, `w("word", 2)` (2nd occurrence), `S(i)` sentence times
* shapes: `country("Almanya")`, `admin1("Texas","USA")`, `union(...)`, `Shape.moved_to(lon,lat)` (true size)
* camera: `CameraPath(start).fly(t0,t1,view).drift(...).move(...).custom(t0,t1,fn)`
* views: `View.fit(shape.bbox_merc(), W, H)`, `View.at(lon,lat,width_deg)`
* sea routes: `sea_route(waypoints)` (auto avoids land) + `Route` + `Timeline` + `draw_ship`
* effects: `fx.highlight`, `fx.flag_fill`, `fx.arc`, `fx.route_progress`, `fx.title`,
  `fx.date_title`, `fx.counter`, `fx.map_label`, `fx.cross_marker`, `fx.burst_marker`, `fx.calendar`
* globe: `Globe`, `zoom_state`, `matched_view`, `state_for_view` (seamless globe <-> map)
* `SFX = [(t, "whoosh"|"swish"|"pop"|"thump"|"shimmer", {...}), ...]` for each flight/reveal

## 4. Check frames - always, before the full render
```bash
.venv/bin/python make.py sheet <name> --every 1.0      # projects/<name>/contact_sheet.png
.venv/bin/python make.py stills <name> 12.4 30.1       # exact moments, half res
```
Look at the images (if you can view images) and fix: empty/ocean-only frames during
moves (use `fly` instead of `move` for long distances), text overlapping the
highlighted area, things off-screen, ships hidden by markers, titles not matching
the spoken word, too much text. Iterate until every beat reads clearly.
For sea routes also run `tools/debug_route.py` (renders route over the land mask).

## 5. Render
```bash
.venv/bin/python make.py final <name>     # -> out/<name>.mp4 and out/<name>_sfx_only.mp4
```
Rendering is chunked and resumable (re-run after an interruption; delete chunks in
`out/<name>_video.mp4.parts/` to re-render only a time range). ~4-8 min per minute
of video on 4-8 cores. Use `--workers 2` on machines with < 8 GB RAM.
`--mix-only` re-mixes audio without re-rendering.

## 6. Deliver
Tell the user where the files are, the storyboard you used, what is placeholder
(TTS voice), and anything they should verify (historical accuracy, imagery license:
Esri World Imagery needs attribution / check terms for commercial use; set
`TILE_PROVIDER = "s2"` for Sentinel-2 cloudless, CC BY 4.0).
