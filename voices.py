"""Voice providers: turn a PerformanceScript into audio plus the timing the actor needs.

Pick one with TTS_PROVIDER in .env:
  edge        free; edge-tts word timings + dictionary lip sync (LIPSYNC=rhubarb for Rhubarb)
  azure       speaking styles per beat, word timings, viseme IDs and ARKit blend-shape frames
  elevenlabs  eleven_v3 with audio tags and word timings + dictionary lip sync

A provider that fails (missing key, network, quota) falls back to edge, so replies keep coming.
"""

import base64
import json
import os
from dataclasses import dataclass, field
from xml.sax.saxutils import escape

import httpx

import texttospeech
from lipsync_dictionary import lipsync_from_words
from models import PerformanceScript

TICKS_PER_SECOND = 10_000_000


@dataclass
class SpeechResult:
    audio: bytes
    mime: str
    words: list  # [{text, start, end}] seconds
    lipsync: dict = None  # Rhubarb-format mouth cues
    visemes: list = None  # [{t, id}] Azure viseme IDs
    blendshapes: dict = None  # {fps, names, frames}
    provider: str = "edge"
    notes: list = field(default_factory=list)


def synthesize(script: PerformanceScript, workdir: str) -> SpeechResult:
    provider = os.getenv("TTS_PROVIDER", "edge").strip().lower()
    providers = {"azure": azure_speech, "elevenlabs": elevenlabs_speech}
    if provider in providers:
        try:
            return providers[provider](script, workdir)
        except Exception as e:
            print(f"{provider} TTS failed, falling back to edge: {e}")
            result = edge_speech(script, workdir)
            result.notes.append(f"{provider} failed: {e}")
            return result
    return edge_speech(script, workdir)


# ---- edge ----------------------------------------------------------------------------------

def edge_speech(script: PerformanceScript, workdir: str) -> SpeechResult:
    text = script.spoken_text
    use_rhubarb = os.getenv("LIPSYNC", "dictionary").strip().lower() == "rhubarb"
    audio, words, wav_path = texttospeech.synthesize(text, workdir, wav=use_rhubarb)

    lipsync = None
    if use_rhubarb:
        try:
            lipsync = texttospeech.run_rhubarb(wav_path, text)
        except Exception as e:
            print(f"Rhubarb Error: {e}")
    if lipsync is None:
        lipsync = lipsync_from_words(words)
    return SpeechResult(audio=audio, mime="audio/mpeg", words=words, lipsync=lipsync, provider="edge")


# ---- azure ---------------------------------------------------------------------------------

# Emotion → (speaking style, base degree, rate). Styles exist only on some voices; check the
# chosen voice's list (en-US-DavisNeural: chat, angry, cheerful, excited, friendly, hopeful,
# sad, shouting, terrified, unfriendly, whispering).
AZURE_STYLES = {
    "neutral": ("chat", 0.8, "0%"),
    "confident": ("chat", 1.0, "-4%"),
    "amused": ("cheerful", 0.7, "0%"),
    "happy": ("cheerful", 1.2, "+2%"),
    "warm": ("friendly", 1.0, "-3%"),
    "excited": ("excited", 1.0, "+6%"),
    "thoughtful": (None, 1.0, "-8%"),
    "curious": ("hopeful", 0.8, "0%"),
    "skeptical": ("unfriendly", 0.5, "-3%"),
    "serious": (None, 1.0, "-5%"),
    "sad": ("sad", 1.0, "-10%"),
    "surprised": ("excited", 0.8, "+4%"),
    "annoyed": ("angry", 0.6, "0%"),
}
AZURE_DELIVERY = {
    "whisper": ("whispering", 1.0, "-6%"),
    "laugh": ("cheerful", 1.6, "+2%"),
    "sigh": ("sad", 0.6, "-12%"),
    "emphatic": ("excited", 1.3, "+3%"),
}
# Azure's 55 facial positions follow the ARKit order, then head and eye roll
AZURE_BLENDSHAPES = [
    "eyeBlinkLeft", "eyeLookDownLeft", "eyeLookInLeft", "eyeLookOutLeft", "eyeLookUpLeft", "eyeSquintLeft", "eyeWideLeft",
    "eyeBlinkRight", "eyeLookDownRight", "eyeLookInRight", "eyeLookOutRight", "eyeLookUpRight", "eyeSquintRight", "eyeWideRight",
    "jawForward", "jawLeft", "jawRight", "jawOpen", "mouthClose", "mouthFunnel", "mouthPucker", "mouthLeft", "mouthRight",
    "mouthSmileLeft", "mouthSmileRight", "mouthFrownLeft", "mouthFrownRight", "mouthDimpleLeft", "mouthDimpleRight",
    "mouthStretchLeft", "mouthStretchRight", "mouthRollLower", "mouthRollUpper", "mouthShrugLower", "mouthShrugUpper",
    "mouthPressLeft", "mouthPressRight", "mouthLowerDownLeft", "mouthLowerDownRight", "mouthUpperUpLeft", "mouthUpperUpRight",
    "browDownLeft", "browDownRight", "browInnerUp", "browOuterUpLeft", "browOuterUpRight", "cheekPuff",
    "cheekSquintLeft", "cheekSquintRight", "noseSneerLeft", "noseSneerRight", "tongueOut", "headRoll", "leftEyeRoll", "rightEyeRoll",
]
BLENDSHAPE_FPS = 60


def azure_ssml(script: PerformanceScript, voice: str) -> str:
    parts = []
    for beat in script.beats:
        text = beat.text.strip()
        if not text:
            continue
        style, degree, rate = AZURE_DELIVERY.get(beat.delivery) or AZURE_STYLES.get(beat.emotion, AZURE_STYLES["neutral"])
        spoken = f'<prosody rate="{rate}">{escape(text)}</prosody>'
        if style:
            degree = round(max(0.01, min(2.0, degree * (0.6 + 0.8 * beat.intensity))), 2)
            spoken = f'<mstts:express-as style="{style}" styledegree="{degree}">{spoken}</mstts:express-as>'
        pause = 350 if beat.delivery == "sigh" else 150
        parts.append(f'{spoken}<break time="{pause}ms"/>')
    return (
        '<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" '
        'xmlns:mstts="https://www.w3.org/2001/mstts" xml:lang="en-US">'
        f'<voice name="{escape(voice)}"><mstts:viseme type="FacialExpression"/>{"".join(parts)}</voice></speak>'
    )


class AzureCollector:
    """Gathers word boundaries, viseme IDs and blend-shape frames from Azure's events."""

    def __init__(self):
        self.words, self.visemes, self.frames = [], [], {}

    def on_word(self, offset_ticks: int, duration_seconds: float, text: str, is_word: bool = True):
        if not is_word or not text.strip():
            return
        start = offset_ticks / TICKS_PER_SECOND
        self.words.append({"text": text, "start": round(start, 3), "end": round(start + duration_seconds, 3)})

    def on_viseme(self, offset_ticks: int, viseme_id: int, animation: str = ""):
        self.visemes.append({"t": round(offset_ticks / TICKS_PER_SECOND, 3), "id": int(viseme_id)})
        if animation:
            chunk = json.loads(animation)
            first = chunk.get("FrameIndex", 0)
            for i, frame in enumerate(chunk.get("BlendShapes", [])):
                self.frames[first + i] = [round(float(v), 2) for v in frame]

    def blendshapes(self):
        if not self.frames:
            return None
        count = max(self.frames) + 1
        empty = [0.0] * len(AZURE_BLENDSHAPES)
        rows, last = [], empty
        for i in range(count):
            last = self.frames.get(i, last)  # hold through any missing frame
            rows.append(last)
        return {"fps": BLENDSHAPE_FPS, "names": AZURE_BLENDSHAPES, "frames": rows}


def azure_speech(script: PerformanceScript, workdir: str) -> SpeechResult:
    key, region = os.getenv("AZURE_SPEECH_KEY"), os.getenv("AZURE_SPEECH_REGION")
    if not key or not region:
        raise RuntimeError("AZURE_SPEECH_KEY and AZURE_SPEECH_REGION must be set")
    import azure.cognitiveservices.speech as speechsdk  # optional dependency, loaded only when used

    voice = os.getenv("AZURE_VOICE", "en-US-DavisNeural")
    config = speechsdk.SpeechConfig(subscription=key, region=region)
    config.set_speech_synthesis_output_format(speechsdk.SpeechSynthesisOutputFormat.Audio24Khz48KBitRateMonoMp3)
    synthesizer = speechsdk.SpeechSynthesizer(speech_config=config, audio_config=None)

    collected = AzureCollector()
    synthesizer.synthesis_word_boundary.connect(lambda e: collected.on_word(
        e.audio_offset, e.duration.total_seconds(), e.text,
        e.boundary_type == speechsdk.SpeechSynthesisBoundaryType.Word))
    synthesizer.viseme_received.connect(lambda e: collected.on_viseme(e.audio_offset, e.viseme_id, e.animation))

    result = synthesizer.speak_ssml_async(azure_ssml(script, voice)).get()
    if result.reason != speechsdk.ResultReason.SynthesizingAudioCompleted:
        details = result.cancellation_details
        raise RuntimeError(f"Azure synthesis {result.reason}: {details.reason} {details.error_details}")

    words = collected.words
    return SpeechResult(
        audio=bytes(result.audio_data), mime="audio/mpeg", words=words,
        lipsync=lipsync_from_words(words),  # backup cues if the browser can't use the visemes
        visemes=collected.visemes, blendshapes=collected.blendshapes(), provider="azure",
    )


# ---- elevenlabs ----------------------------------------------------------------------------

ELEVEN_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice}/with-timestamps"
ELEVEN_DEFAULT_VOICE = "JBFqnCBsd6RMkjVDRZzb"
# eleven_v3 reads bracketed audio tags as direction; keep to tags it's known to follow
ELEVEN_DELIVERY_TAGS = {"whisper": "[whispers]", "laugh": "[laughs]", "sigh": "[sighs]", "emphatic": "[excited]"}
ELEVEN_EMOTION_TAGS = {"excited": "[excited]", "curious": "[curious]", "skeptical": "[sarcastic]", "amused": "[mischievously]"}


def eleven_text(script: PerformanceScript) -> str:
    parts = []
    for beat in script.beats:
        text = beat.text.strip()
        if not text:
            continue
        tag = ELEVEN_DELIVERY_TAGS.get(beat.delivery) or (ELEVEN_EMOTION_TAGS.get(beat.emotion) if beat.intensity >= 0.5 else None)
        parts.append(f"{tag} {text}" if tag else text)
    return " ".join(parts)


def words_from_alignment(alignment: dict) -> list:
    """Characters with start/end times → words, skipping [audio tags]."""
    chars = alignment.get("characters", [])
    starts = alignment.get("character_start_times_seconds", [])
    ends = alignment.get("character_end_times_seconds", [])
    words, current, in_tag = [], None, False
    for ch, start, end in zip(chars, starts, ends):
        if ch == "[":
            in_tag = True
        if in_tag or ch.isspace():
            if current:
                words.append(current)
                current = None
            if ch == "]":
                in_tag = False
            continue
        if current is None:
            current = {"text": ch, "start": round(start, 3), "end": round(end, 3)}
        else:
            current["text"] += ch
            current["end"] = round(end, 3)
    if current:
        words.append(current)
    return [w for w in words if any(c.isalnum() for c in w["text"])]


def elevenlabs_speech(script: PerformanceScript, workdir: str) -> SpeechResult:
    key = os.getenv("ELEVENLABS_API_KEY")
    if not key:
        raise RuntimeError("ELEVENLABS_API_KEY must be set")
    voice = os.getenv("ELEVENLABS_VOICE_ID", ELEVEN_DEFAULT_VOICE)
    response = httpx.post(
        ELEVEN_URL.format(voice=voice),
        params={"output_format": "mp3_44100_128"},
        headers={"xi-api-key": key},
        json={"text": eleven_text(script), "model_id": os.getenv("ELEVENLABS_MODEL", "eleven_v3")},
        timeout=60,
    )
    response.raise_for_status()
    data = response.json()
    words = words_from_alignment(data.get("alignment") or data.get("normalized_alignment") or {})
    return SpeechResult(audio=base64.b64decode(data["audio_base64"]), mime="audio/mpeg", words=words,
                        lipsync=lipsync_from_words(words), provider="elevenlabs")
