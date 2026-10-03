import asyncio
import edge_tts
import subprocess
import os
import json

VOICE = "en-US-ChristopherNeural"
TICKS_PER_SECOND = 10_000_000  # edge-tts boundary offsets are in 100 ns ticks


def _tool(name: str) -> str:
    # Prefer a binary sitting in the working directory over one on PATH
    local = f"{name}.exe"
    return os.path.abspath(local) if os.path.exists(local) else name


async def _stream_speech(text: str, voice: str, mp3_path: str) -> list:
    communicate = edge_tts.Communicate(text, voice, boundary="WordBoundary")
    words = []
    with open(mp3_path, "wb") as audio_file:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_file.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                start = chunk["offset"] / TICKS_PER_SECOND
                words.append({
                    "text": chunk["text"],
                    "start": round(start, 3),
                    "end": round(start + chunk["duration"] / TICKS_PER_SECOND, 3),
                })
    return words


def synthesize(text: str, workdir: str, wav: bool = True):
    """Speak `text` into `workdir`. Returns (mp3 bytes, word timings, wav path for Rhubarb or None)."""
    mp3_path = os.path.join(workdir, "speech.mp3")
    wav_path = os.path.join(workdir, "speech.wav") if wav else None

    words = asyncio.run(_stream_speech(text, VOICE, mp3_path))

    if wav_path:
        subprocess.run(
            [_tool("ffmpeg"), "-y", "-loglevel", "error", "-i", mp3_path, wav_path],
            check=True
        )
    with open(mp3_path, "rb") as audio_file:
        audio = audio_file.read()
    return audio, words, wav_path


def run_rhubarb(wav_file: str, dialog_text: str = None) -> dict:
    # -f json: Output format; -d: the known transcript, which makes recognition more accurate
    command = [_tool("rhubarb"), "-f", "json", wav_file]
    if dialog_text:
        dialog_path = os.path.join(os.path.dirname(wav_file), "dialog.txt")
        with open(dialog_path, "w", encoding="utf-8") as dialog_file:
            dialog_file.write(dialog_text)
        command += ["-d", dialog_path]

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=True
    )
    return json.loads(result.stdout)
