# Visual style guide

The goal: a viewer with the sound off still understands the story; with sound on,
every visual change lands exactly on its word. Reference: `examples/`.

## Look
* Basemap: satellite imagery, darkened ~20 %, slightly desaturated, vignette.
  Faint white country borders (alpha ≈ 0.12) for context.
* Subject countries: **tinted texture** (`fx.highlight`) - never flat paint - with a
  glowing white border that **draws on** before the fill fades in.
* Palette: protagonist red `#9e1010` / flag; comparison or target yellow `#f7d548`;
  routes gold `(1.0, 0.82, 0.36)`; secondary orange `#e8a33d`; danger red. Max 3 colours at once.
* Flags fill a shape only when the country is "the hero" (circular wipe reveal).
* Ships/icons have a soft dark halo so they read on any background.

## Text (less is more)
* ≤ 3 words on screen at a time; names, dates, numbers only. Never subtitles of the narration.
* Font Montserrat. Title: Black/ExtraBold 100-150 px, wide tracking (0.1-0.2), uppercase.
  Secondary: SemiBold 46-56 px. Numbers in accent yellow `(255, 210, 92)` when they land.
* Position: horizontally centred, y 220-520. Bottom 25 % and right 10 % are covered by the
  Shorts UI - keep important things out of there. Map subjects sit around y 700-1300.
* Titles enter with the mask-slide (`title_anim`), leave before the next beat's title.
* Numbers count up/down (`fx.counter`) rather than appear.

## Motion
* Never static: `drift` (3-6 % push-in) between all moves.
* Long distances: `fly` (zoom out, pan, zoom in). Short / zoom-only: `move`.
  Avoid `move` across oceans - the middle frames show nothing.
* Moves take 1.2-2.5 s, eased (in_out_cubic/quint). Pop-ins use `out_back`.
* Start camera moves ~0.1-0.2 s **before** the word, reveals **on** the word.
* One focus per beat. If two places matter, frame both or fly between them.
* Hook in the first second: spinning globe zooming in, or an immediate flight.
* End on a calm, loop-friendly shot (globe, zoom-out, or the hero shape).

## Sound
* `whoosh` for every camera flight (duration = flight), `swish` for titles,
  `pop` for icons/numbers appearing, `thump` for landings / impacts / deaths,
  `shimmer` for reveals and "discoveries". Keep SFX under the voice (mix does −6 dB).

## Pacing
* A new visual event every 2-4 seconds; shorts are 30-60 s.
* Tail: ~1.5-2 s after the last word, then a short fade.
