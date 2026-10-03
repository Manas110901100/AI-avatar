# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A talking 3D avatar that performs like an on-camera actor. A FastAPI backend has an OpenAI model **direct** each reply as a beat-by-beat performance script, speaks it through a voice provider (`voices.py`), and compiles a timeline aligned to the spoken words. A Three.js frontend (`static/index.html` + ES modules in `static/js/`) plays that timeline through layered animation: recorded Mixamo clips, procedural IK gestures, eye gaze, facial emotion, lip sync and a camera rig.

## Running

```powershell
pip install -r requirements.txt
uvicorn main:app --reload        # then open http://127.0.0.1:8000/
python debug_routes.py           # prints registered routes (local helper, gitignored)
```

There is no test suite, linter or build step. `test_api_validation.py` is a gitignored ad-hoc script, and it is stale: it imports `validate_api_key`, which no longer exists (the function is now `validate_and_save_api_key`).

**Run from the repo root.** The static mount, the SQLite file (`./apikey.db`), the request log (`request_logs.txt`) and the external binaries all resolve against the current working directory.

The avatar loads and idles before a key is entered (behind the access screen). In the browser console, `perform(name, params)`, `setEmotion(name, intensity)`, `setShot(name)`, `setGaze(target)`, `setMorph(name, weight)`/`clearMorphs()` and `director` drive the actor by hand without an API key.

```powershell
python tools/rig_upgrade.py                                   # rebuild static/avatars/rpm-detailed/avatar.glb from static/avatar.glb, then audit it
python tools/avatar_audit.py <avatar.glb> [--baseline <glb>]  # morph/eye/bone coverage + PASS/FAIL gate
python tools/shoot.py steps.json --serve --out shots [--query avatar=rpm-default]  # headless-Chrome screenshots; exits 1 on page errors
```

`plan.md` is the roadmap (Phases 1–2 done; gesture library and new identity later).

### Voice settings (`.env`, loaded by `main.py`)

`TTS_PROVIDER=edge|azure|elevenlabs` (default `edge`), `LIPSYNC=dictionary|rhubarb` (edge only, default `dictionary`), `AZURE_SPEECH_KEY`, `AZURE_SPEECH_REGION`, `AZURE_VOICE` (default `en-US-DavisNeural`), `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID`, `ELEVENLABS_MODEL` (default `eleven_v3`). A provider that fails falls back to edge.

### External files (not in git)

- **`res/sphinx/`**: PocketSphinx models for Rhubarb. Its `cmudict-en-us.dict` is also the pronunciation dictionary for `lipsync_dictionary.py`, so the default lip sync needs `res/` too.
- **ffmpeg** and **Rhubarb Lip Sync**: only for `LIPSYNC=rhubarb`. `ffmpeg.exe`/`rhubarb.exe` in the repo root (resolved to absolute paths) are preferred over PATH.

## Request flow

1. **Key registration**: `POST /keys/validate` → `api_validator.validate_and_save_api_key`. It checks that the key starts with `sk-`, returns the existing row if the key is already stored, otherwise verifies it live with `OpenAI().models.list()` and stores it in the `api_keys` table. The frontend keeps the returned `id`, never the key. All later calls send `api_key_id`, and the server looks up the raw key from the DB.
2. **Direction**: `POST /chat/speak` → `aimodels.generate_performance`. It loads the last 5 `ConversationLog` rows as history and calls `ChatOpenAI(...).with_structured_output(PerformanceScript)` with `DIRECTOR_PROMPT` (persona, direction rules, gesture catalog). A `PerformanceScript` is 1–5 `Beat`s: `text, emotion, intensity, gesture, hand, count, force, stress_word, gaze, head, shot, delivery`. The log row stores the joined text and comma-joined gestures.
3. **Speech**: `voices.synthesize(script, workdir)` returns a `SpeechResult`: audio, words with start/end, and lip sync as Rhubarb-format cues, Azure viseme IDs and/or 60 fps ARKit blend-shape frames.
   - `edge`: `texttospeech.synthesize` streams edge-tts (`boundary="WordBoundary"`, offsets in 100 ns ticks); `lipsync_dictionary.lipsync_from_words` maps CMU-dictionary phonemes to Oculus visemes across each word (~1 s total vs ~3.5 s with Rhubarb).
   - `azure`: SSML per beat (`azure_ssml`: emotion/delivery → `mstts:express-as` style, prosody, breaks, `mstts:viseme type="FacialExpression"`); `AzureCollector` gathers word boundaries, viseme IDs and blend-shape frames.
   - `elevenlabs`: `eleven_v3` `/with-timestamps` with audio tags (`eleven_text`); `words_from_alignment` rebuilds words, skipping `[tags]`.
4. **Timeline**: `performance.build_timeline` matches words to beats by character position in the joined text, then emits sorted events (`emotion`, `gaze`, `blink`, `shot`, `head`, `gesture`). Acting rules live here as constants: expressions lead the line by 0.2 s, a gesture's stroke lands on its beat's stress word, look-aways return to camera on it, blinks fall at phrase ends. Consecutive `count` gestures continue the raised hand (`continues: true`) and count up. Emphasis `beat`s are added automatically on strong lines, but not on sad or thoughtful ones. If the director leaves every line on `medium`, the strongest line gets a `push_in`. Events may start before the audio (`preroll`).
5. **Response**: JSON `{text, audio (base64), audio_mime, lipsync, visemes, blendshapes, voice, timeline}`.

`DIRECTOR_MODEL` in `static/js/main.js` picks the OpenAI model (it must support tool calling).

## Animation system

- **Gesture catalog**: `gestures.py` lists recorded clips (`CLIPS`: file, duration, energy, meaning) and procedural actions (`PROCEDURAL`). It builds the `GestureName` Literal the LLM chooses from and the catalog text in the prompt. **To add a recorded gesture, put the `.glb` in `static/` and add one line to `CLIPS`** (exact filename, case and spaces included). `stroke` defaults to 40% of a clip; tune per clip if needed.
- **Frontend modules** (`static/js/`), run each frame in this order by `main.js`: `director` (states idle/listening/thinking/speaking, fires timeline events against `audio.currentTime`, `PERSONA` tuning) → `animator` (mixer) → `procedural.updateBody` (spine lean, breathing) → `synth` (procedural gestures via `ik.js`) → `procedural.updateHead` (head/neck offsets, eyes) → `face` (morph targets) → `stage.render` (camera rig, lights, post-processing).
- **Layering**: `avatar.retargetClip` splits every Mixamo clip into upper- and lower-body clips. The lower body always plays the idle (`weight shift.glb`); the upper body blends idle, the `Talking_1`/`Talking_2` loops and gesture clips with weights summing to 1 (three.js fills any shortfall with the bind/T-pose). Only quaternion tracks are kept.
- **Procedural layers run after the mixer** and modify bone quaternions in place each frame; they don't accumulate because the mixer rewrites those bones every frame. Eye bones have no tracks, so `procedural.updateEyes` sets them absolutely from their rest pose.
- **IK (`ik.js`)**: analytic two-bone arm IK with an elbow pole and a hinge-locked elbow; wrist orientation from finger direction + palm normal; finger curls about axes measured from the rest pose. `synth.js` authors gesture geometry in the avatar's rest frame (Y up, facing +Z, its left = +X, `s` mirrors per hand) and makes it follow the chest/head bones.
- **Avatars**: `static/avatars/<id>/avatar.json` holds the GLB path, eye-bone limits and bone/morph aliases. It's chosen by `?avatar=<id>`, defaulting to `DEFAULT_AVATAR = 'rpm-detailed'` in `main.js`. `avatar.capabilities` (`arkit`, `oculusVisemes`, `legacyRPM`, `eyeBones`, `twistBones`) switches behavior. Engine code uses canonical Mixamo/ARKit names, and the aliases map them to the rig.
- **Face** (`face.js`):
  - `ARKIT_EMOTIONS` on rigs with ARKit shapes: one-sided smirks, brows, squints, a Duchenne squint added to smiles, brow flashes on head events and strong gesture strokes, left/right blinks, and `eyeLook*` as lid-follow. `LEGACY_EMOTIONS` on the original avatar. `EMOTION_POSES` (head and spine posture) is shared.
  - Lip-sync cue values may be Rhubarb letters or `viseme_*` names.
  - Voice blend-shape frames drive the mouth only on rigs with the full ARKit mouth (`arkitMouth`); otherwise visemes keep the mouth and the frames only add expression.
  - Any morph written last frame but not this one is reset to 0.
- **Rig upgrade** (`tools/rig_upgrade.py`, constants at the top):
  - derives ARKit shapes from existing morphs (split left/right across a smooth midline) and sculpts the rest from face regions measured off the eye bones and the welded skin component
  - closes each eye cap into a sphere and moves the eye bone to its centre
  - adds `Left/RightForeArmTwist` bones, which have no tracks; `ArmRig.updateTwist` gives them half the hand's roll every frame
  - writes morph targets as sparse accessors

## Gotchas

- **Rigs calibrate from the rest pose**: `GestureSynth`, `Procedural` and `Face` must be constructed before the `Animator` starts playing (as `initActor` does).
- **Mixamo hips**: the clip GLBs have a +90° X, 0.01-scale armature root; `retargetClip` folds that rotation into the hips keys. Positions are dropped, so root motion never applies.
- **Original avatar** (`static/avatar.glb`, Ready Player Me, whose service shut down in January 2026):
  - 20 morph targets: visemes, `mouthOpen`, `mouthSmile`, `eyesClosed`, `eyesLookUp`, `eyesLookDown`. Its `eyesLookUp/Down` morphs move the eyeballs, not the lids.
  - Its eyes are partial caps pivoting ~4 mm off-centre, so `rpm-default` clamps eye turns tightly.
  - Don't edit it in place: `rig_upgrade.py` reads it.
- **Derived and sculpted shapes are approximations.** Blender + Faceit hand-sculpting is the quality path (see `plan.md`).
- **Azure**:
  - styles exist only on some voices, and `styledegree` may be ignored outside some locales
  - if frames look wrong, check the 55-name blend-shape order in `voices.AZURE_BLENDSHAPES` against Azure's docs
  - `azure-cognitiveservices-speech` is imported lazily
- `texttospeech.synthesize` calls `asyncio.run()`. That only works because `/chat/speak` is a sync `def` endpoint running in a threadpool. Making it `async def` will break it.
- An invalid enum value from the LLM (e.g. an unknown gesture) fails Pydantic validation and returns a 500.
- The schema is created with `Base.metadata.create_all` and there are no migrations. Model column changes need `apikey.db` deleted or migrated by hand.
- API keys are stored in plaintext in `apikey.db`. `GET /chat/history/{api_key_id}` and `/chat/speak` have no auth beyond knowing the integer id.
- OpenAI keys come from the DB, not the environment. `.env` only configures voices.
