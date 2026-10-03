"""Gesture catalog: recorded Mixamo clips plus procedural actions synthesized live in the browser.

`stroke` is the time (seconds from the gesture's start) of its main stroke — the instant the
timeline compiler aligns to the stressed word. Clip strokes default to 40% of the clip's length;
tune them by hand after watching a clip.
"""

from typing import Literal

# name: (duration seconds, energy, meaning)
CLIPS = {
    "acknowledging.glb": (1.67, "low", "brief acknowledging nod: 'right', 'got it'"),
    "angry gesture.glb": (2.13, "high", "sharp angry arm gesture: frustration, outrage"),
    "annoyed head shake.glb": (2.10, "medium", "annoyed head shake: exasperation"),
    "being cocky.glb": (2.77, "medium", "cocky, self-assured body language: bragging, swagger"),
    "Disappointed.glb": (4.23, "medium", "disappointed slump: letdown, regret"),
    "dismissing gesture.glb": (3.27, "medium", "dismissive wave-off: 'forget it', brushing an idea aside"),
    "happy hand gesture.glb": (2.77, "medium", "upbeat hand gesture: enthusiasm, good news"),
    "hard head nod.glb": (1.67, "medium", "firm emphatic nod: strong agreement, 'absolutely'"),
    "head nod yes.glb": (2.53, "low", "nodding yes: agreement"),
    "lengthy head nod.glb": (1.77, "low", "slow understanding nod: empathy, 'I see'"),
    "look away gesture.glb": (1.83, "low", "glances away: reluctance, shyness, avoiding"),
    "relieved sigh.glb": (3.03, "low", "relieved sigh: relief, 'phew'"),
    "sarcastic head nod.glb": (2.07, "low", "sarcastic nod: irony, 'sure, right'"),
    "shaking head no.glb": (1.83, "low", "shakes head no: disagreement, denial"),
    "Telling A Secret.glb": (10.93, "medium", "leans in conspiratorially: a secret or insider tip (long)"),
    "thoughtful head shake.glb": (3.10, "low", "thoughtful head shake: gentle disagreement, 'not quite'"),
    "Yelling.glb": (7.87, "high", "yelling, big forceful delivery (rare: comedic outrage only)"),
}

# name: (duration seconds, stroke seconds, meaning)
PROCEDURAL = {
    "point_at_viewer": (1.6, 0.45, "points straight at the viewer: 'you', direct address, a challenge"),
    "open_palms": (2.0, 0.55, "both palms up and open: explaining, offering, honesty, 'here's the thing'"),
    "hand_on_chest": (2.2, 0.6, "hand over the heart: sincerity, 'I', gratitude, personal feeling"),
    "shrug": (1.6, 0.5, "shoulders up, palms up: uncertainty, 'who knows', playful indifference"),
    "count": (1.8, 0.5, "holds up fingers while listing points; set count 1-5"),
    "hand_to_chin": (2.6, 0.7, "hand to the chin: considering, weighing an idea"),
    "wave": (2.0, 0.5, "friendly wave: hello or goodbye only"),
    "beat": (0.7, 0.3, "small downward hand stroke that punctuates the stressed word"),
}

GESTURE_NAMES = tuple(CLIPS) + tuple(PROCEDURAL)
GestureName = Literal[GESTURE_NAMES]


def gesture_info(name: str) -> dict:
    """Timing info the compiler and the browser share."""
    if name in CLIPS:
        duration, _, _ = CLIPS[name]
        return {"kind": "clip", "name": name, "duration": duration, "stroke": round(duration * 0.4, 2)}
    duration, stroke, _ = PROCEDURAL[name]
    return {"kind": "proc", "name": name, "duration": duration, "stroke": stroke}


def catalog() -> dict:
    return {
        "clips": [gesture_info(name) for name in CLIPS],
        "procedural": [gesture_info(name) for name in PROCEDURAL],
    }


def catalog_for_prompt() -> str:
    lines = ["Live hand gestures (precise, economical; prefer these):"]
    for name, (_, _, meaning) in PROCEDURAL.items():
        lines.append(f"- {name}: {meaning}")
    lines.append("Recorded body clips (bigger, whole upper body; use sparingly):")
    for name, (duration, energy, meaning) in CLIPS.items():
        lines.append(f"- {name}: {meaning} [{duration:.1f}s, {energy} energy]")
    return "\n".join(lines)
