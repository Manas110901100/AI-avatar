"""Lip sync from word timings and a pronunciation dictionary, with no audio analysis.

Each spoken word is looked up in the CMU dictionary that ships with Rhubarb's models
(res/sphinx/cmudict-en-us.dict), its phonemes are mapped to Oculus visemes and spread across
the word's start/end (vowels hold longer than consonants). Output uses Rhubarb's JSON shape,
so the browser treats it exactly like Rhubarb's cues — but it takes milliseconds, not seconds.
"""

import os
import re

DICTIONARY_PATH = os.path.join("res", "sphinx", "cmudict-en-us.dict")

PHONEME_VISEMES = {
    "AA": "viseme_aa", "AE": "viseme_aa", "AH": "viseme_aa", "AY": "viseme_aa", "AW": "viseme_aa",
    "EH": "viseme_E", "EY": "viseme_E",
    "IH": "viseme_I", "IY": "viseme_I", "Y": "viseme_I",
    "AO": "viseme_O", "OW": "viseme_O", "OY": "viseme_O",
    "UH": "viseme_U", "UW": "viseme_U", "W": "viseme_U",
    "ER": "viseme_RR", "R": "viseme_RR",
    "P": "viseme_PP", "B": "viseme_PP", "M": "viseme_PP",
    "F": "viseme_FF", "V": "viseme_FF",
    "TH": "viseme_TH", "DH": "viseme_TH",
    "T": "viseme_DD", "D": "viseme_DD",
    "K": "viseme_kk", "G": "viseme_kk", "NG": "viseme_kk", "HH": "viseme_kk",
    "CH": "viseme_CH", "JH": "viseme_CH", "SH": "viseme_CH", "ZH": "viseme_CH",
    "S": "viseme_SS", "Z": "viseme_SS",
    "N": "viseme_nn", "L": "viseme_nn",
}
VOWELS = {"AA", "AE", "AH", "AO", "AW", "AY", "EH", "ER", "EY", "IH", "IY", "OW", "OY", "UH", "UW"}
DIPHTHONGS = {"AW", "AY", "EY", "OW", "OY"}
STOPS = {"P", "B", "T", "D", "K", "G"}

# Rough letter-to-phoneme fallback for words the dictionary doesn't know
LETTER_PHONEMES = {
    "a": ["AE"], "b": ["B"], "c": ["K"], "d": ["D"], "e": ["EH"], "f": ["F"], "g": ["G"], "h": ["HH"],
    "i": ["IH"], "j": ["JH"], "k": ["K"], "l": ["L"], "m": ["M"], "n": ["N"], "o": ["OW"], "p": ["P"],
    "q": ["K"], "r": ["R"], "s": ["S"], "t": ["T"], "u": ["UH"], "v": ["V"], "w": ["W"], "x": ["K", "S"],
    "y": ["IY"], "z": ["Z"],
}
DIGIT_WORDS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"]
MIN_SILENCE = 0.06  # pauses shorter than this keep the mouth moving instead of closing

_dictionary = None


def _load() -> dict:
    global _dictionary
    if _dictionary is None:
        _dictionary = {}
        with open(DICTIONARY_PATH, encoding="utf-8", errors="ignore") as f:
            for line in f:
                parts = line.split()
                if len(parts) < 2 or "(" in parts[0]:
                    continue  # skip alternate pronunciations: word(2)
                _dictionary[parts[0]] = [re.sub(r"\d", "", p) for p in parts[1:]]
    return _dictionary


def phonemes(word: str) -> list:
    dictionary = _load()
    token = word.lower().replace("’", "'")
    token = re.sub(r"[^a-z0-9']", "", token)
    if not token:
        return []
    if token in dictionary:
        return dictionary[token]
    if token.isdigit():
        return [p for digit in token for p in dictionary.get(DIGIT_WORDS[int(digit)], [])]
    stripped = token.strip("'")
    if stripped in dictionary:
        return dictionary[stripped]
    return [p for letter in stripped if letter.isalpha() for p in LETTER_PHONEMES.get(letter, [])]


def _weight(phoneme: str) -> float:
    if phoneme in DIPHTHONGS:
        return 2.4
    if phoneme in VOWELS:
        return 2.0
    if phoneme in STOPS:
        return 0.7
    return 1.0


def lipsync_from_words(words: list, duration: float = None) -> dict:
    """words: [{text, start, end}] in seconds → {"mouthCues": [...], "metadata": {...}}."""
    cues = []

    def push(start, end, value):
        if end - start <= 1e-4:
            return
        if cues and cues[-1]["value"] == value and abs(cues[-1]["end"] - start) < 1e-4:
            cues[-1]["end"] = round(end, 3)
            return
        cues.append({"start": round(start, 3), "end": round(end, 3), "value": value})

    clock = 0.0
    for word in words:
        start, end = word["start"], max(word["end"], word["start"] + 0.04)
        if start - clock >= MIN_SILENCE:
            push(clock, start, "viseme_sil")
        elif cues:
            cues[-1]["end"] = round(start, 3)  # close tiny gaps so the mouth never snaps shut mid-phrase
        sounds = [p for p in phonemes(word["text"]) if p in PHONEME_VISEMES]
        if not sounds:
            push(start, end, "viseme_sil")
        else:
            total = sum(_weight(p) for p in sounds)
            t = start
            for p in sounds:
                span = (end - start) * _weight(p) / total
                push(t, t + span, PHONEME_VISEMES[p])
                t += span
        clock = end

    final = max(duration or 0, clock)
    if final > clock:
        push(clock, final, "viseme_sil")
    return {"metadata": {"duration": round(final, 3), "source": "dictionary"}, "mouthCues": cues}
