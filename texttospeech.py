import asyncio
import edge_tts
import subprocess
import os
import json

VOICE = "en-US-ChristopherNeural"
MP3_FILE = "response.mp3"
WAV_FILE = "response.wav"

async def text_to_speech(text, voice) -> None:
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(MP3_FILE)
   
def mp3_to_wav_ffmpeg(text: str) -> None:
    asyncio.run(text_to_speech(text, VOICE)) 
    
    # Check for local ffmpeg.exe
    ffmpeg_cmd = "ffmpeg"
    if os.path.exists("ffmpeg.exe"):
        ffmpeg_cmd = "ffmpeg.exe"
        
    subprocess.run(
        [ffmpeg_cmd, "-y", "-i", str(MP3_FILE), str(WAV_FILE)],
        check=True
    )
    return WAV_FILE

def run_rhubarb(wav_file: str) -> str:
    rhubarb_cmd = "rhubarb"
    if os.path.exists("rhubarb.exe"):
        rhubarb_cmd = "rhubarb.exe"
    
    # Run Rhubarb to get JSON output
    # -f json: Output format
    result = subprocess.run(
        [rhubarb_cmd, "-f", "json", wav_file],
        capture_output=True,
        text=True,
        check=True
    )
    return result.stdout

