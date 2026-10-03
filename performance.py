"""Compiles a PerformanceScript and the voice's word timings into the timeline the browser plays.

Acting rules encoded here:
- the face changes EXPRESSION_LEAD seconds before a line starts (thought precedes words)
- a gesture's stroke lands on its beat's stress word
- a look-away returns to camera on the stress word
- blinks fall at phrase ends and with gaze shifts
"""

import re

from gestures import gesture_info
from models import PerformanceScript

EXPRESSION_LEAD = 0.2
GAZE_LEAD = 0.3
SHOT_LEAD = 0.3
MIN_LOOK_AWAY = 0.6
PREROLL_LIMIT = 0.5  # how far before the audio the first event may start
GESTURE_GAP = 0.15
AUTO_BEAT_MIN_INTENSITY = 0.55
NO_AUTO_BEAT_EMOTIONS = {"sad", "thoughtful"}  # emphasis strokes read as callous here
REPEATABLE_GESTURES = {"count", "beat"}  # a list counts on every item; beats punctuate freely
COUNT_CHANGE_LEAD = 0.12  # fingers change just ahead of the next item's stressed word
HELD_PROCEDURAL = {"point_at_viewer", "open_palms", "hand_on_chest", "shrug", "count", "hand_to_chin"}


def _clamp(value, low=0.0, high=1.0):
    return max(low, min(high, value))


def _norm(word: str) -> str:
    return re.sub(r"[^\w']", "", word.lower().replace("’", "'"))


def _assign_words(script: PerformanceScript, words: list) -> list:
    """Group the voice's words by beat, matching on character position in the spoken text."""
    spans, pos = [], 0
    for beat in script.beats:
        text = beat.text.strip()
        if not text:
            spans.append(None)
            continue
        if pos:
            pos += 1  # the joining space
        spans.append((pos, pos + len(text)))
        pos += len(text)

    lowered = script.spoken_text.lower()
    beat_words = [[] for _ in script.beats]
    cursor, current = 0, next((i for i, span in enumerate(spans) if span), 0)
    for word in words:
        index = lowered.find(word["text"].lower(), cursor)
        if index >= 0:
            cursor = index + len(word["text"])
            for i, span in enumerate(spans):
                if span and span[0] <= index < span[1]:
                    current = i
                    break
        beat_words[current].append(word)
    return beat_words


def _stress_word(stress: str, beat_words: list) -> dict:
    targets = [_norm(token) for token in (stress or "").split() if _norm(token)]
    if targets:
        for word in beat_words:
            if _norm(word["text"]) == targets[0]:
                return word
    # Fall back to the longest word, a fair proxy for the content word
    return max(beat_words, key=lambda word: len(_norm(word["text"])))


def _shots_with_push_in(script: PerformanceScript, beat_words: list) -> list:
    """The script's shots, plus a push-in on the strongest line if the director left the camera static."""
    shots = [beat.shot for beat in script.beats]
    spoken = [i for i, words in enumerate(beat_words) if words]
    if len(spoken) >= 2 and len({shots[i] for i in spoken}) == 1 and shots[spoken[0]] == "medium":
        key = max(spoken, key=lambda i: (script.beats[i].intensity, i))  # ties go to the later line
        shots[key] = "push_in"
    return shots


def _event(t: float, event_type: str, **fields) -> dict:
    return {"t": round(t, 3), "type": event_type, **fields}


def build_timeline(script: PerformanceScript, words: list, lipsync: dict = None) -> dict:
    beat_words = _assign_words(script, words)

    duration = max([0.5] + [word["end"] for word in words])
    if lipsync:
        duration = max(duration, lipsync.get("metadata", {}).get("duration", 0))

    events, beats = [], []
    previous_shot, previous_gesture, gesture_free_at = None, None, float("-inf")
    last_count = 0
    shots = _shots_with_push_in(script, beat_words)

    for beat, spoken, shot in zip(script.beats, beat_words, shots):
        if not spoken:
            continue
        start, end = spoken[0]["start"], spoken[-1]["end"]
        stress = _stress_word(beat.stress_word, spoken)
        intensity = _clamp(beat.intensity)

        events.append(_event(start - EXPRESSION_LEAD, "emotion", emotion=beat.emotion, intensity=intensity))

        events.append(_event(start - GAZE_LEAD, "gaze", target=beat.gaze))
        if beat.gaze != "camera":
            events.append(_event(start - GAZE_LEAD + 0.02, "blink"))
            back = max(stress["start"], start + MIN_LOOK_AWAY)
            back = min(back, end + 0.2)
            events.append(_event(back - 0.1, "gaze", target="camera"))
            events.append(_event(back - 0.08, "blink"))

        if shot != previous_shot or shot == "push_in":
            events.append(_event(start - SHOT_LEAD, "shot", shot=shot, until=round(end, 3)))
            previous_shot = shot

        if beat.head != "none":
            events.append(_event(stress["start"] - 0.08, "head", move=beat.head, strength=intensity, until=round(end, 3)))

        gesture, auto, hand = beat.gesture, False, beat.hand
        if not gesture and intensity >= AUTO_BEAT_MIN_INTENSITY and beat.emotion not in NO_AUTO_BEAT_EMOTIONS:
            gesture, auto = "beat", True
            hand = "right" if hand == "both" else hand
        if gesture and (gesture != previous_gesture or gesture in REPEATABLE_GESTURES):
            info = gesture_info(gesture)
            begin = stress["start"] - info["stroke"]
            # The next item of a list keeps the hand up and changes fingers on its stressed word
            continues = gesture == "count" and previous_gesture == "count" and begin < gesture_free_at
            if continues:
                begin = stress["start"] - COUNT_CHANGE_LEAD
            if begin >= gesture_free_at or continues:
                length = info["duration"]
                if gesture in HELD_PROCEDURAL:
                    # Hold the pose through the rest of the line, within reason
                    length = min(max(length, end + 0.3 - begin), length * 2)
                count = beat.count or 1
                if gesture == "count" and previous_gesture == "count" and count <= last_count:
                    count = last_count + 1  # list items count up even if the script repeats a number
                count = int(_clamp(count, 1, 5))
                events.append(_event(
                    begin, "gesture",
                    kind=info["kind"], name=gesture, hand=hand,
                    force=_clamp(beat.force), count=count,
                    duration=round(length, 2), stroke=info["stroke"], auto=auto, continues=continues,
                ))
                gesture_free_at = begin + length + GESTURE_GAP
                if not auto:
                    previous_gesture = gesture
                    last_count = count if gesture == "count" else 0

        events.append(_event(end + 0.05, "blink"))
        beats.append({"start": start, "end": end, "text": beat.text.strip(), "emotion": beat.emotion})

    preroll = 0.0
    if events:
        preroll = _clamp(-min(event["t"] for event in events), 0.0, PREROLL_LIMIT)
        for event in events:
            event["t"] = round(max(event["t"], -preroll), 3)
        events.sort(key=lambda event: event["t"])

    return {
        "duration": round(duration, 3),
        "preroll": round(preroll, 3),
        "words": words,
        "beats": beats,
        "events": events,
    }
