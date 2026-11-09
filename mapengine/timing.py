"""Word-timing based cues: scene timings follow the voiceover automatically.

words.json = [{"word": "Pasifik", "start": 20.55, "end": 21.1}, ...]
(produced from TTS word boundaries or from a transcription of the real VO)
"""
import json
import os
import re

_TR = str.maketrans("İIÇĞÖŞÜ", "iıçğöşü")


def find_vo(project_dir):
    """Relative path of the voice to use: vo/voice.* if present, else the placeholder."""
    for f in ("voice.mp3", "voice.wav", "voice.m4a", "voice.flac", "placeholder.mp3"):
        if os.path.exists(os.path.join(project_dir, "vo", f)):
            return "vo/" + f
    return "vo/placeholder.mp3"


def norm(w):
    w = w.translate(_TR).lower()
    w = re.split(r"[’']", w)[0]  # Atlantik’i -> atlantik, 1521'de -> 1521
    return re.sub(r"[^\wçğıöşü]", "", w)


class Words:
    def __init__(self, path, offset=0.0):
        with open(path, encoding="utf-8") as f:
            self.words = json.load(f)
        self.offset = offset
        self.tokens = []  # (norm_token, start, end) - multiword entries split
        self.sentences = []  # (start, end) of each sentence
        s_start = None
        for w in self.words:
            parts = w["word"].split()
            for p in parts:
                self.tokens.append((norm(p), w["start"] + offset, w["end"] + offset))
            if s_start is None:
                s_start = w["start"] + offset
            if re.search(r"[.!?…:]$", w["word"].strip()):
                self.sentences.append((s_start, w["end"] + offset))
                s_start = None
        if s_start is not None:
            self.sentences.append((s_start, self.words[-1]["end"] + offset))

    def _find(self, phrase, n=1):
        q = [norm(p) for p in phrase.split()]
        hits = 0
        for i in range(len(self.tokens) - len(q) + 1):
            if all(self.tokens[i + k][0].startswith(q[k]) for k in range(len(q))):
                hits += 1
                if hits == n:
                    return i, i + len(q) - 1
        raise KeyError(f"phrase not found in VO: {phrase!r} (#{n})")

    def at(self, phrase, n=1):
        """start time of phrase"""
        return self.tokens[self._find(phrase, n)[0]][1]

    def end(self, phrase, n=1):
        return self.tokens[self._find(phrase, n)[1]][2]

    def sentence(self, i):
        """(start, end) of sentence i (negative i counts from the end; clamped)."""
        if not self.sentences:
            return (self.tokens[0][1], self.tokens[-1][2])
        i = max(-len(self.sentences), min(len(self.sentences) - 1, i))
        return self.sentences[i]

    @property
    def n_sentences(self):
        return len(self.sentences)

    @property
    def last_end(self):
        return self.tokens[-1][2]
