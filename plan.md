# Avatar roadmap

Tier A (the actor engine) is done: an LLM director, a timeline aligned to the spoken words, layered clips, procedural IK gestures, gaze and a camera rig. This roadmap covers what comes next.

**Status (2026-10-03):**
- **Phase 1 is done.** `rpm-detailed` is the default avatar.
- **Phase 2 is done.** Edge with dictionary lip sync and **Azure (DavisNeural, centralus) are tested live**, including the order of the 55 facial channels. ElevenLabs is built and unit-tested, but has no key yet.
- Phases 3 and 4 come later.

## Where the limits are
- **Face:** `avatar.glb` (Ready Player Me, whose service shut down on 2026-01-31) has 20 morph targets: 15 visemes plus `mouthOpen`, `mouthSmile`, `eyesClosed`, `eyesLookUp` and `eyesLookDown`. With no brows, frowns, squints or cheeks, 13 emotions share one smile and one eyelid.
- **Eyes:** each eye is a half-sphere cap (radius ≈ 1.95 cm, 120 vertices). Turning it more than about 8° pushes its rim through the eyelids.
- **Arms:** there are no twist bones, so palm-up and pointing poses put all the forearm roll on the wrist.
- **Voice:** edge-tts has one neutral delivery, and Rhubarb alone takes about 3.5 s per reply.
- **Gestures:** 17 clips and 8 procedural actions, all named in the prompt, so the actor repeats itself.

---

## Phase 1: A detailed rig (now)
### 1A. Rig upgrade in Python (`tools/`)
Blender isn't installed, and Faceit is paid and needs landmarks placed by hand. So the first pass edits the GLB directly with a deterministic, re-runnable script.

- `tools/glb.py`: reads and writes GLB files with numpy.
- `tools/avatar_audit.py <glb>`: bones, morph coverage (ARKit 52 / Oculus 15 / legacy), eye geometry, twist bones and sizes, ending with a PASS or FAIL.
- `tools/rig_upgrade.py`: reads `static/avatar.glb` and writes `static/avatars/rpm-detailed/avatar.glb`. Every existing bone and morph is kept. It adds:
  - **ARKit shapes derived from existing morphs**, split left/right:
    - eye blink, squint and wide
    - eye look up/down
    - mouth smile (one-sided smirk) and frown
    - `jawOpen`, mouth press, pucker and funnel
  - **Region-sculpted shapes:** brows (inner up, outer up, down), cheek squint, nose sneer.
  - **Spherical eyes:** the caps are closed into full spheres, so gaze can turn ±25°.
  - **Forearm twist bones**, with the forearm weights split between the forearm and twist bones.
- **Later upgrade path:** Blender plus Faceit, to hand-sculpt all 52 ARKit shapes on the same avatar.

### 1B. The engine uses the detail
- `static/avatars/<id>/avatar.json`: per-avatar config (GLB path, eye limits, aliases, feature flags). Choose with `?avatar=<id>`. `rpm-default` is today's avatar; `rpm-detailed` is the upgrade.
- `avatar.js`: capability detection and name aliases.
- `face.js`:
  - left/right blinks and `eyeLook*` gaze-follow
  - emotion presets on the new shapes
  - micro-expressions: brow flashes, smile squints, a one-sided smirk
  - `jawOpen` blended with the visemes
- `procedural.js`: eye limits come from the config.
- `ik.js`: forearm roll is shared with the twist bones.
- `tools/shoot.py`: a headless-Chrome screenshot harness for visual checks.

## Phase 2: An expressive voice with exact timing (now)
- `voices.py`: one provider interface, chosen with `TTS_PROVIDER` in `.env`:
  - **`edge`** (default, free): edge-tts plus **dictionary lip sync** from the CMU dictionary (`res/sphinx/cmudict-en-us.dict`), which needs no Rhubarb. Set `LIPSYNC=rhubarb` to use Rhubarb instead.
  - **`azure`:** SSML per beat with speaking styles (`mstts:express-as`), prosody and pauses. One call returns audio, word timings, viseme IDs and 55-value ARKit blend-shape frames at 60 fps.
  - **`elevenlabs`:** `eleven_v3` with audio tags (`[whispers]`, `[laughs]`, `[sighs]`) and word timestamps, plus dictionary lip sync.
  - If a provider fails, it falls back to edge.
- `Beat.delivery`: `normal | whisper | laugh | sigh | emphatic`.
- `face.js`: when blend-shape frames arrive, they drive the mouth and jaw, while our emotion layer keeps the brows and eyes.

### `.env` settings
```
TTS_PROVIDER=edge            # edge | azure | elevenlabs
LIPSYNC=dictionary           # dictionary | rhubarb   (edge only)
AZURE_SPEECH_KEY=...
AZURE_SPEECH_REGION=...      # e.g. eastus
AZURE_VOICE=en-US-DavisNeural
ELEVENLABS_API_KEY=...
ELEVENLABS_VOICE_ID=...
```

---

## Later
### Phase 3: Gesture library (100+ variants)
- **Pick by intent, not file name.** The LLM chooses from about 22 intents (`agree`, `point_you`, `uncertain`, `think`…), and `performance.choose_gesture` picks a fresh variant by energy, beat length and recent use.
- `static/gestures/manifest.json`, plus `tools/gesture_audit.py` to measure each clip's duration, stroke and body region.
- Left-hand variants built at load by mirroring, plus lazy loading.
- **New clips:**
  - a Mixamo batch converted with a Blender command-line script
  - your own gestures through video mocap (Rokoko Vision or DeepMotion)
  - **Higgsfield as a stand-in actor:** reference performances with a static camera, run through video mocap
  - generative motion (Kimodo or HY-Motion), as a spike with a go/no-go

### Phase 4: A new identity (optional)
Design the face as a Higgsfield Soul ID character, then use it as the selfie input for MetaPerson or Avaturn (both export GLB with ARKit shapes). Check it with `tools/avatar_audit.py` and plug it in through `avatar.json`.

---

## What we need
| Item | For | Notes |
|---|---|---|
| A valid OpenAI key | Every phase | The key stored in `apikey.db` has been revoked |
| Azure Speech key + region | Phase 2 `azure` | The free F0 tier is enough |
| ElevenLabs key + voice ID | Phase 2 `elevenlabs` | Optional |
| Blender, plus Faceit (paid) | The Phase 1 upgrade path, Phase 3 | Not installed yet |
| Mixamo account; Higgsfield credits; a cloud GPU | Phase 3 | Higgsfield and the GPU are optional |

## Risks
- **Derived and sculpted shapes are approximations.** Hand-sculpting in Faceit is the quality upgrade.
- **Azure blend-shape quality** is mixed in community reports. The fallback is visemes plus our emotion layer.
- **Azure styles** exist only on some voices. Choose the voice by its style list.
- **Higgsfield is a content source, not a live renderer.** It's slow, costs credits per generation, isn't interactive, and produces 2D video.
- **Licensing:** Mixamo, Higgsfield output and avatar-platform terms.

## References
- Faceit: https://superhivemarket.com/products/faceit
- Azure viseme and blend shapes: https://learn.microsoft.com/azure/ai-services/speech-service/how-to-speech-synthesis-viseme
- ElevenLabs v3: https://aireiter.com/blog/elevenlabs-eleven-v3-api-guide
- Avatar platforms in 2026: https://avatarsdk.com/blog/2026/08/31/avatar-platforms-2026-whos-alive-whos-gone/
- Higgsfield: https://higgsfield.ai/blog/best-ai-avatar-generators-talking-videos
- Kimodo: https://rits.shanghai.nyu.edu/ai/nvidia-releases-kimodo-controllable-text-to-motion-for-characters-and-humanoid-robots/
- HY-Motion 1.0: https://rits.shanghai.nyu.edu/ai/tencent-open-sources-hy-motion-1-0-a-billion-parameter-text-to-motion-ai-model/
