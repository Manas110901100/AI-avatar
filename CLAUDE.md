# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A talking 3D avatar chat app. A FastAPI backend sends the user's text to OpenAI, which picks a reply and a gesture animation. The backend turns the reply into speech and lip-sync data. A single-page Three.js frontend (`static/index.html`) plays the audio and drives the avatar's mouth, gestures, blinking and idle motion.

## Running

```powershell
pip install -r requirements.txt
uvicorn main:app --reload        # then open http://127.0.0.1:8000/
python debug_routes.py           # prints registered routes (local helper, gitignored)
```

There is no test suite, linter or build step. `test_api_validation.py` is a gitignored ad-hoc script, and it is stale: it imports `validate_api_key`, which no longer exists (the function is now `validate_and_save_api_key`).

**Run from the repo root.** The static mount, the SQLite file (`./apikey.db`), the request log (`request_logs.txt`), the temp audio files and the external binaries all resolve against the current working directory.

### External binaries (not in git)

- **ffmpeg**: converts the TTS MP3 to WAV. `ffmpeg.exe` in the repo root is preferred over `ffmpeg` on PATH.
- **Rhubarb Lip Sync**: produces mouth cues from the WAV. `rhubarb.exe` in the repo root is preferred over `rhubarb` on PATH. It needs the `res/sphinx/` PocketSphinx models next to the executable, and `res/` is gitignored too.

If Rhubarb fails, `/chat/speak` still returns audio with an empty lip-sync header. If ffmpeg fails, the request fails.

## Request flow

1. **Key registration**: `POST /keys/validate` → `api_validator.validate_and_save_api_key`. It checks that the key starts with `sk-`, returns the existing row if the key is already stored, otherwise verifies it live with `OpenAI().models.list()` and stores it in the `api_keys` table. The frontend keeps the returned `id`, never the key. All later calls send `api_key_id`, and the server looks up the raw key from the DB.
2. **Chat**: `POST /chat/speak` → `aimodels.generate_chat_response`. It loads the last 5 `ConversationLog` rows as LangChain history and calls `ChatOpenAI(...).with_structured_output(ChatModelResponse)`, which returns `{response, animation}`. It then saves a new log row.
3. **Speech**: `texttospeech.mp3_to_wav_ffmpeg` (edge-tts voice `en-US-ChristopherNeural` → `response.mp3` → ffmpeg → `response.wav`), then `run_rhubarb` returns JSON mouth cues.
4. **Response**: the WAV is the response body. The metadata travels in **HTTP headers**: `X-Response-Text`, `X-Animation-File` and `X-Lip-Sync-Data` (base64 Rhubarb JSON). CORS `expose_headers=["*"]` is what lets the browser read them.

The frontend hardcodes `model: "gpt-3.5-turbo"` in `sendMessage()`.

## Animation system

- `models.AnimationType` is a `Literal` of gesture `.glb` filenames. It doubles as the LLM's structured-output enum. **To add a gesture, put the `.glb` in `static/` and add its exact filename (case and spaces included) to `AnimationType`.**
- `avatar.glb` (the Ready Player Me-style model with viseme/`eyesClosed` morph targets), `weight shift.glb` (idle loop) and `Talking_2.glb` (default talking loop) are loaded directly by the frontend. They are deliberately left out of `AnimationType`. `Talking_1.glb` is currently unused.
- The gesture files are Mixamo animations. `filterTracks()` in `index.html` strips `mixamorig` prefixes to retarget them onto the avatar's bones. It also drops hips/root tracks and all `.position`/`.scale` tracks so the avatar doesn't drift.
- `playAudio()` plays the chosen gesture once (`LoopOnce`), falls back to `Talking_2` while audio is still playing, and returns to idle when the audio ends. `VISEME_MAP` maps Rhubarb mouth shapes (A–H, X) to `viseme_*` morph targets.

## Gotchas

- **Shared temp files**: every request writes the same `response.mp3`/`response.wav` (the `output_filename` in `main.py` is unused), so concurrent `/chat/speak` calls overwrite each other's audio.
- **Header encoding**: response text goes out as an HTTP header, which Starlette encodes as latin-1. LLM output with characters outside latin-1 (curly quotes, emoji) can fail at response time.
- `mp3_to_wav_ffmpeg` calls `asyncio.run()`. That only works because `/chat/speak` is a sync `def` endpoint running in a threadpool. Making it `async def` will break it.
- The schema is created with `Base.metadata.create_all` and there are no migrations. Model column changes need `apikey.db` deleted or migrated by hand.
- API keys are stored in plaintext in `apikey.db`. `GET /chat/history/{api_key_id}` and `/chat/speak` have no auth beyond knowing the integer id.
- `dotenv` is in `requirements.txt`, but nothing calls `load_dotenv`. OpenAI keys come from the DB, not the environment.
