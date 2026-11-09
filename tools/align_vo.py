"""Word timings from a real voiceover -> words.json (faster-whisper).

  .venv/bin/python tools/align_vo.py <audio> [--out words.json] [--model small]

If <project>/metin.txt exists it is used as a prompt (proper nouns spelled right)
and the transcribed words are snapped back onto the script's words so that
scene cues like w("Pasifik") keep matching.
"""
import argparse
import difflib
import json
import os
import re

from faster_whisper import WhisperModel


def _n(w):
    return re.sub(r"[^\wçğıöşü]", "", w.lower())


def snap_to_script(words, script):
    """Replace recognised word text with the script's words (keeps timings)."""
    toks = script.split()
    a = [_n(w["word"]) for w in words]
    b = [_n(t) for t in toks]
    sm = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    out = [dict(w) for w in words]
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag in ("equal", "replace") and (i2 - i1) == (j2 - j1):
            for k in range(i2 - i1):
                out[i1 + k]["word"] = toks[j1 + k]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("audio")
    ap.add_argument("--out")
    ap.add_argument("--model", default="small")
    a = ap.parse_args()
    vo_dir = os.path.dirname(os.path.abspath(a.audio))
    out = a.out or os.path.join(vo_dir, "words.json")
    txt = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(out))), "metin.txt")
    script = open(txt, encoding="utf-8").read() if os.path.exists(txt) else None
    model = WhisperModel(a.model, device="cpu", compute_type="int8")
    segs, info = model.transcribe(a.audio, word_timestamps=True, initial_prompt=script,
                                  language=None, vad_filter=False)
    words = []
    for s in segs:
        for wd in s.words:
            words.append(dict(word=wd.word.strip(), start=round(wd.start, 3), end=round(wd.end, 3)))
    if script:
        words = snap_to_script(words, script)
    json.dump(words, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    print(f"{len(words)} words ({info.language}) -> {out}")
    print(" ".join(w["word"] for w in words))


if __name__ == "__main__":
    main()
