#!/usr/bin/env python3
"""map-shorts command line.  (Run with the project venv: .venv/bin/python make.py ...)

  new     <name> [--text metin.txt|--text-str "..."]   scaffold projects/<name> from the template
  tts     <project> [--voice tr-TR-AhmetNeural]         placeholder voice + word timings (edge-tts)
  align   <project> [--audio vo/voice.mp3]              word timings from a real voiceover (faster-whisper)
  words   <project>                                     print word / sentence timings
  find    <query>                                       look up country / state names -> codes
  stills  <project> t1 t2 ...                           preview PNGs (half res) into <project>/stills
  sheet   <project> [--every 1.5]                       contact sheet PNG of the whole video
  render  <project> [--res 1] [--workers 4]             video only
  final   <project> [--mix-only]                        video + voice + SFX  ->  out/<name>.mp4

<project> = a name under projects/ or examples/, or a path to a project folder.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)


def project_dir(p):
    for cand in (p, os.path.join(ROOT, "projects", p), os.path.join(ROOT, "examples", p)):
        if os.path.isfile(os.path.join(cand, "scene.py")) or os.path.isfile(os.path.join(cand, "metin.txt")):
            return os.path.abspath(cand)
    sys.exit(f"project not found: {p}")


def cmd_new(a):
    d = os.path.join(ROOT, "projects", a.project)
    if os.path.exists(os.path.join(d, "scene.py")):
        sys.exit(f"already exists: {d}")
    os.makedirs(os.path.join(d, "vo"), exist_ok=True)
    shutil.copy(os.path.join(ROOT, "templates", "scene_template.py"), os.path.join(d, "scene.py"))
    txt = a.text_str or (open(a.text, encoding="utf-8").read() if a.text else "")
    if txt:
        open(os.path.join(d, "metin.txt"), "w", encoding="utf-8").write(txt.strip() + "\n")
    print(d)


def cmd_tts(a):
    d = project_dir(a.project)
    import asyncio
    import edge_tts
    text = open(os.path.join(d, "metin.txt"), encoding="utf-8").read().strip()

    async def go():
        c = edge_tts.Communicate(text, a.voice, rate=a.rate, boundary="WordBoundary")
        words = []
        with open(os.path.join(d, "vo", "placeholder.mp3"), "wb") as f:
            async for ch in c.stream():
                if ch["type"] == "audio":
                    f.write(ch["data"])
                elif ch["type"] == "WordBoundary":
                    words.append(dict(word=ch["text"], start=round(ch["offset"] / 1e7, 3),
                                      end=round((ch["offset"] + ch["duration"]) / 1e7, 3)))
        return words

    os.makedirs(os.path.join(d, "vo"), exist_ok=True)
    words = asyncio.run(go())
    # edge-tts drops punctuation; restore it from the text so sentences are detectable
    words = _restore_punct(words, text)
    json.dump(words, open(os.path.join(d, "vo", "words.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    print(f"{len(words)} words -> {d}/vo/words.json (+ placeholder.mp3)")


def _restore_punct(words, text):
    toks = text.split()
    i = 0
    for w in words:
        n = len(w["word"].split())
        if i + n <= len(toks):
            w["word"] = " ".join(toks[i:i + n])
        i += n
    return words


def cmd_align(a):
    d = project_dir(a.project)
    audio = a.audio or next((os.path.join(d, "vo", f) for f in ("voice.mp3", "voice.wav", "voice.m4a")
                             if os.path.exists(os.path.join(d, "vo", f))), None)
    if not audio:
        sys.exit("put the voiceover at <project>/vo/voice.mp3 (or pass --audio)")
    if not os.path.isabs(audio):
        audio = os.path.join(d, audio) if os.path.exists(os.path.join(d, audio)) else os.path.abspath(audio)
    subprocess.run([sys.executable, os.path.join(ROOT, "tools", "align_vo.py"), audio,
                    "--out", os.path.join(d, "vo", "words.json"), "--model", a.model], check=True)


def cmd_words(a):
    from mapengine.timing import Words
    d = project_dir(a.project)
    W = Words(os.path.join(d, "vo", "words.json"))
    for i, (s, e) in enumerate(W.sentences):
        print(f"sentence {i}: {s:6.2f} - {e:6.2f}")
    print(" ".join(f"{w['start']:.2f}:{w['word']}" for w in W.words))


def cmd_find(a):
    from mapengine.geo import find_admin1, find_country
    q = " ".join([a.project] + [str(x) for x in a.rest])
    for r in find_country(q):
        print("country:", r)
    for r in find_admin1(q)[:15]:
        print("admin1 :", r)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd")
    ap.add_argument("project")
    ap.add_argument("rest", nargs="*")
    ap.add_argument("--res", type=float, default=1.0)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--t0", type=float, default=0.0)
    ap.add_argument("--t1", type=float, default=None)
    ap.add_argument("--every", type=float, default=1.5)
    ap.add_argument("--mix-only", action="store_true")
    ap.add_argument("--text")
    ap.add_argument("--text-str")
    ap.add_argument("--voice", default="tr-TR-AhmetNeural")
    ap.add_argument("--rate", default="+8%")
    ap.add_argument("--audio")
    ap.add_argument("--model", default="small")
    a = ap.parse_args()

    simple = dict(new=cmd_new, tts=cmd_tts, align=cmd_align, words=cmd_words, find=cmd_find)
    if a.cmd in simple:
        return simple[a.cmd](a)

    from mapengine import render as R
    pdir = project_dir(a.project)
    name = os.path.basename(pdir.rstrip("/"))
    scene = os.path.join(pdir, "scene.py")
    out = os.path.join(ROOT, "out")
    os.makedirs(out, exist_ok=True)
    if a.cmd == "stills":
        times = [float(x) for x in a.rest]
        for p in R.stills(scene, times, os.path.join(pdir, "stills"), res=a.res if a.res != 1.0 else 0.5):
            print(p)
    elif a.cmd == "sheet":
        sc = R.load_scene(scene)
        times = [round(x * a.every, 2) for x in range(int(sc.DURATION / a.every) + 1)]
        paths = R.stills(scene, times, os.path.join(pdir, "stills"), res=0.25)
        cols = 8
        sheet = os.path.join(pdir, "contact_sheet.png")
        from PIL import Image, ImageDraw
        ims = [Image.open(p) for p in paths]
        w, h = ims[0].size
        rows = (len(ims) + cols - 1) // cols
        S = Image.new("RGB", (cols * w, rows * h), (0, 0, 0))
        d = ImageDraw.Draw(S)
        for i, (im, t) in enumerate(zip(ims, times)):
            x, y = (i % cols) * w, (i // cols) * h
            S.paste(im, (x, y))
            d.rectangle([x, y, x + 58, y + 18], fill=(0, 0, 0))
            d.text((x + 4, y + 3), f"{t:.1f}s", fill=(255, 255, 0))
        S.save(sheet)
        print(sheet)
    elif a.cmd in ("render", "final"):
        video = os.path.join(out, f"{name}_video.mp4")
        if not a.mix_only:
            R.render(scene, video, res=a.res, workers=a.workers, t0=a.t0, t1=a.t1)
        if a.cmd == "final":
            from mapengine import audio
            audio.mix_project(pdir, video, os.path.join(out, f"{name}.mp4"))
            audio.mix_project(pdir, video, os.path.join(out, f"{name}_sfx_only.mp4"), with_vo=False)
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
