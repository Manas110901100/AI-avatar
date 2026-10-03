// Facial layer: emotion presets, lip sync, blinks and micro-expressions mixed into one set of
// morph-target weights.
//
// Two preset tables: LEGACY_EMOTIONS for the original Ready Player Me avatar (mouthSmile,
// eyesClosed, eyesLookUp/Down and visemes only) and ARKIT_EMOTIONS for rigs with ARKit shapes
// (tools/rig_upgrade.py, or any avatar with brows, squints and left/right smiles).

// Head and body posture per emotion, shared by both rigs (radians; lean is spine pitch)
export const EMOTION_POSES = {
    neutral: {},
    confident: { pitch: -0.04, lean: -0.015 },
    amused: { pitch: -0.01, roll: 0.05 },
    happy: { pitch: -0.03, roll: 0.03 },
    warm: { pitch: 0.02, roll: 0.06 },
    excited: { pitch: -0.05, lean: 0.02 },
    thoughtful: { pitch: -0.02, roll: 0.07 },
    curious: { roll: 0.09, lean: 0.02 },
    skeptical: { pitch: 0.04, roll: -0.06 },
    serious: { pitch: 0.03 },
    sad: { pitch: 0.09, roll: 0.03, lean: 0.04 },
    surprised: { pitch: -0.07, lean: -0.03 },
    annoyed: { pitch: 0.02, roll: -0.03, yaw: 0.04 },
};

const LEGACY_EMOTIONS = {
    neutral: {},
    confident: { mouthSmile: 0.18, eyesClosed: 0.12 },
    amused: { mouthSmile: 0.45, eyesClosed: 0.18 },
    happy: { mouthSmile: 0.75, eyesClosed: 0.22 },
    warm: { mouthSmile: 0.4, eyesClosed: 0.12 },
    excited: { mouthSmile: 0.65 },
    thoughtful: { eyesClosed: 0.15, eyesLookUp: 0.15 },
    curious: { mouthSmile: 0.1 },
    skeptical: { eyesClosed: 0.3, mouthSmile: 0.08 },
    serious: { eyesClosed: 0.1 },
    sad: { eyesClosed: 0.3, eyesLookDown: 0.25 },
    surprised: { mouthOpen: 0.2 },
    annoyed: { eyesClosed: 0.28 },
};

// Tuned for the cool persona: smiles lean to one side, lids sit a little heavy
const ARKIT_EMOTIONS = {
    neutral: {},
    confident: { mouthSmileLeft: 0.32, mouthSmileRight: 0.06, eyeBlinkLeft: 0.12, eyeBlinkRight: 0.12, eyeSquintLeft: 0.25, eyeSquintRight: 0.2, browDownLeft: 0.12, browDownRight: 0.12 },
    amused: { mouthSmileLeft: 0.5, mouthSmileRight: 0.3, eyeSquintLeft: 0.4, eyeSquintRight: 0.35, cheekSquintLeft: 0.35, cheekSquintRight: 0.25, browOuterUpLeft: 0.25 },
    happy: { mouthSmileLeft: 0.75, mouthSmileRight: 0.75, cheekSquintLeft: 0.55, cheekSquintRight: 0.55, eyeSquintLeft: 0.45, eyeSquintRight: 0.45, browInnerUp: 0.1 },
    warm: { mouthSmileLeft: 0.42, mouthSmileRight: 0.38, eyeSquintLeft: 0.3, eyeSquintRight: 0.3, browInnerUp: 0.22, cheekSquintLeft: 0.2, cheekSquintRight: 0.2 },
    excited: { mouthSmileLeft: 0.7, mouthSmileRight: 0.7, eyeWideLeft: 0.45, eyeWideRight: 0.45, browInnerUp: 0.45, browOuterUpLeft: 0.4, browOuterUpRight: 0.4, jawOpen: 0.08 },
    thoughtful: { browInnerUp: 0.25, browDownLeft: 0.2, eyeSquintLeft: 0.25, eyeSquintRight: 0.2, mouthPressLeft: 0.3, mouthPressRight: 0.3, mouthFrownLeft: 0.1 },
    curious: { browInnerUp: 0.35, browOuterUpLeft: 0.45, mouthSmileLeft: 0.12, eyeWideLeft: 0.15, eyeWideRight: 0.1 },
    skeptical: { browDownRight: 0.5, browOuterUpLeft: 0.5, eyeSquintRight: 0.45, eyeSquintLeft: 0.15, mouthPressLeft: 0.35, mouthSmileLeft: 0.12, mouthFrownRight: 0.15 },
    serious: { browDownLeft: 0.35, browDownRight: 0.35, eyeSquintLeft: 0.2, eyeSquintRight: 0.2, mouthPressLeft: 0.3, mouthPressRight: 0.3 },
    sad: { browInnerUp: 0.7, mouthFrownLeft: 0.55, mouthFrownRight: 0.55, eyeBlinkLeft: 0.22, eyeBlinkRight: 0.22, eyeLookDownLeft: 0.3, eyeLookDownRight: 0.3, mouthPressLeft: 0.2, mouthPressRight: 0.2 },
    surprised: { eyeWideLeft: 0.75, eyeWideRight: 0.75, browInnerUp: 0.7, browOuterUpLeft: 0.7, browOuterUpRight: 0.7, jawOpen: 0.22 },
    annoyed: { browDownLeft: 0.6, browDownRight: 0.6, eyeSquintLeft: 0.4, eyeSquintRight: 0.4, noseSneerLeft: 0.4, noseSneerRight: 0.25, mouthPressLeft: 0.4, mouthPressRight: 0.4, mouthFrownLeft: 0.2, mouthFrownRight: 0.2 },
};

// Lip-sync cue values: Rhubarb mouth shapes A-H, X, or Oculus viseme names directly
const RHUBARB_VISEMES = {
    A: 'viseme_PP', // MBP
    B: 'viseme_kk', // KST
    C: 'viseme_E', // Eh/Ae
    D: 'viseme_aa', // Aa
    E: 'viseme_O', // Ao/Er
    F: 'viseme_U', // Uw/Oy
    G: 'viseme_FF', // F/V
    H: 'viseme_nn', // L (approx)
    X: 'viseme_sil', // Idle
};
const VISEMES = ['viseme_sil', 'viseme_PP', 'viseme_FF', 'viseme_TH', 'viseme_DD', 'viseme_kk', 'viseme_CH', 'viseme_SS',
    'viseme_nn', 'viseme_RR', 'viseme_aa', 'viseme_E', 'viseme_I', 'viseme_O', 'viseme_U'];
// Azure viseme IDs 0-21 to Oculus visemes
const AZURE_VISEMES = ['viseme_sil', 'viseme_aa', 'viseme_aa', 'viseme_O', 'viseme_E', 'viseme_RR', 'viseme_I', 'viseme_U',
    'viseme_O', 'viseme_aa', 'viseme_O', 'viseme_aa', 'viseme_kk', 'viseme_RR', 'viseme_nn', 'viseme_SS', 'viseme_CH',
    'viseme_TH', 'viseme_FF', 'viseme_DD', 'viseme_kk', 'viseme_PP'];
// How much each viseme opens the jaw, for the ARKit jawOpen boost
const JAW_OPENNESS = { viseme_aa: 1, viseme_O: 0.8, viseme_E: 0.55, viseme_I: 0.35, viseme_U: 0.4, viseme_RR: 0.3, viseme_CH: 0.25 };
const LIP_ANTICIPATION = 0.04; // the mouth shapes slightly ahead of the sound
const COARTICULATION = 0.3; // last part of a cue already leans toward the next shape
const BLINK_SIDE_OFFSET = 0.015; // the right lid trails the left by a few milliseconds
const BROW_FLASH_TIME = 0.45;

export class Face {
    constructor(avatar, persona) {
        this.avatar = avatar;
        this.meshes = avatar.morphMeshes;
        this.available = avatar.morphNames;
        this.arkit = avatar.capabilities.arkit;
        // Voice blend-shape frames can only articulate speech on a rig with the full ARKit mouth;
        // otherwise visemes keep the mouth and the frames only add expression
        this.arkitMouth = ['mouthClose', 'mouthRollLower', 'mouthLowerDownLeft', 'mouthUpperUpLeft', 'mouthStretchLeft']
            .every((name) => avatar.morphNames.has(name));
        this.presets = this.arkit ? ARKIT_EMOTIONS : LEGACY_EMOTIONS;
        this.persona = persona;
        this.time = 0;

        this.emotion = 'neutral';
        this.emotionTarget = {};
        this.emotionWeights = {};
        this.visemeWeights = {};
        this.cues = [];
        this.cueIndex = 0;
        this.frames = null; // voice-provided ARKit blend-shape frames ({fps, names, frames})

        this.blinkStart = -1;
        this.nextBlink = 1.5;
        this.eyeLook = { up: 0, down: 0 };
        this.browFlashStart = -1;
        this.browFlashStrength = 0;
        this.override = {}; // console tuning: setMorph(name, weight)
        this.written = new Set();
    }

    has(name) {
        return this.available.has(name);
    }

    setEmotion(name, intensity = 0.5) {
        const preset = this.presets[name] || this.presets.neutral;
        this.emotion = name;
        this.emotionTarget = {};
        Object.entries(preset).forEach(([morph, weight]) => {
            if (this.has(morph)) this.emotionTarget[morph] = weight * (0.4 + 0.8 * intensity);
        });
    }

    // Rhubarb-format cues ({mouthCues: [{start, end, value}]}); values may be Rhubarb letters or viseme names
    setLipSync(lipsync) {
        this.cues = lipsync?.mouthCues || [];
        this.cueIndex = 0;
    }

    // Provider viseme IDs ([{t, id}], Azure numbering) as cues
    setVisemes(visemes, duration) {
        if (!visemes?.length) return;
        const cues = visemes.map((v, i) => ({
            start: v.t,
            end: i + 1 < visemes.length ? visemes[i + 1].t : duration ?? v.t + 0.15,
            value: AZURE_VISEMES[v.id] || 'viseme_sil',
        }));
        this.setLipSync({ mouthCues: cues });
    }

    setBlendshapes(blendshapes) {
        this.frames = blendshapes?.frames?.length && this.arkit ? blendshapes : null;
    }

    blink() {
        this.blinkStart = this.time;
        this.nextBlink = this.time + this.randomBlinkGap();
    }

    // A quick lift of the brows, the way people mark a stressed word
    browFlash(strength = 0.5) {
        this.browFlashStart = this.time;
        this.browFlashStrength = strength;
    }

    randomBlinkGap() {
        const [low, high] = this.persona.blinkInterval;
        return low + Math.random() * (high - low);
    }

    // Vertical gaze in radians (positive = down) beyond what the eye bones carry
    setEyeLook(pitch, limits) {
        if (this.arkit) {
            // Lid-follow shapes: the eyeballs turn on their bones, the upper lids track them
            this.eyeLook.up = Math.min(1, Math.max(0, -pitch) / Math.max(limits.up, 0.05));
            this.eyeLook.down = Math.min(1, Math.max(0, pitch) / Math.max(limits.down, 0.05));
        } else {
            // The original eyes are shallow caps: these shapes carry the look the bones can't
            this.eyeLook.up = Math.min(0.5, Math.max(0, -pitch - 0.1) * 1.2);
            this.eyeLook.down = Math.min(0.6, Math.max(0, pitch - 0.04) * 1.5);
        }
    }

    blinkValue(delay = 0) {
        if (this.blinkStart < 0) return 0;
        const x = this.time - this.blinkStart - delay;
        if (x < 0) return 0;
        if (x < 0.07) return x / 0.07;
        if (x < 0.1) return 1;
        if (x < 0.23) return 1 - (x - 0.1) / 0.13;
        return 0;
    }

    visemeTargets(speechTime) {
        const targets = {};
        if (speechTime === null || !this.cues.length) return targets;
        const t = speechTime + LIP_ANTICIPATION;
        if (this.cues[this.cueIndex] && t < this.cues[this.cueIndex].start) this.cueIndex = 0;
        while (this.cueIndex < this.cues.length - 1 && t > this.cues[this.cueIndex].end) this.cueIndex++;

        const cue = this.cues[this.cueIndex];
        if (!cue || t < cue.start || t > cue.end) return targets;
        const shape = (value) => RHUBARB_VISEMES[value] || value;
        const current = shape(cue.value);
        const next = this.cues[this.cueIndex + 1];
        const progress = (t - cue.start) / Math.max(cue.end - cue.start, 1e-3);
        const lean = next ? Math.max(0, (progress - (1 - COARTICULATION)) / COARTICULATION) * 0.5 : 0;
        if (current) targets[current] = 1 - lean;
        if (next) targets[shape(next.value)] = (targets[shape(next.value)] || 0) + lean;
        return targets;
    }

    // Voice-provided ARKit frame at `speechTime`: mouth/jaw channels and expression channels
    frameAt(speechTime) {
        if (!this.frames || speechTime === null) return null;
        const { fps, names, frames } = this.frames;
        const row = frames[Math.min(frames.length - 1, Math.max(0, Math.floor(speechTime * fps)))];
        if (!row) return null;
        const mouth = {};
        const expression = {};
        names.forEach((name, i) => {
            if (!this.has(name) || name.startsWith('eyeBlink') || name.startsWith('eyeLook')) return; // blinks and gaze stay ours
            (/^(jaw|mouth|tongue|cheekPuff)/.test(name) ? mouth : expression)[name] = row[i];
        });
        return { mouth, expression };
    }

    // speechTime: seconds into the current audio, or null when not speaking
    update(dt, speechTime) {
        this.time += dt;
        if (this.time >= this.nextBlink) this.blink();

        const emotionRate = 1 - Math.exp(-dt / this.persona.expressionSpeed);
        const names = new Set([...Object.keys(this.emotionWeights), ...Object.keys(this.emotionTarget)]);
        names.forEach((name) => {
            const current = this.emotionWeights[name] || 0;
            this.emotionWeights[name] = current + ((this.emotionTarget[name] || 0) - current) * emotionRate;
        });

        const frame = this.frameAt(speechTime);
        const visemeRate = 1 - Math.exp(-dt * 22);
        const framesSpeak = frame && this.arkitMouth;
        const targets = framesSpeak ? {} : this.visemeTargets(speechTime);
        VISEMES.forEach((name) => {
            const current = this.visemeWeights[name] || 0;
            this.visemeWeights[name] = current + ((targets[name] || 0) - current) * visemeRate;
        });

        const speaking = speechTime !== null;
        const out = { ...this.emotionWeights };
        const add = (name, value) => { if (this.has(name)) out[name] = (out[name] || 0) + value; };
        const raise = (name, value) => { if (this.has(name)) out[name] = Math.max(out[name] || 0, value); };

        ['mouthSmile', 'mouthSmileLeft', 'mouthSmileRight'].forEach((name) => {
            if (out[name] && speaking) out[name] *= 0.7;
        });
        VISEMES.forEach((name) => add(name, this.visemeWeights[name]));

        if (frame) {
            if (framesSpeak) Object.entries(frame.mouth).forEach(([name, value]) => { out[name] = value; });
            Object.entries(frame.expression).forEach(([name, value]) => raise(name, value));
        }

        const flash = this.browFlashStart < 0 ? 0 : Math.max(0, Math.sin(Math.PI * (this.time - this.browFlashStart) / BROW_FLASH_TIME));
        const flashing = this.time - this.browFlashStart < BROW_FLASH_TIME ? flash * this.browFlashStrength : 0;

        if (this.arkit) {
            // Real smiles reach the eyes
            const smileL = (out.mouthSmileLeft || 0) + (out.mouthSmile || 0);
            const smileR = (out.mouthSmileRight || 0) + (out.mouthSmile || 0);
            add('eyeSquintLeft', smileL * 0.35);
            add('eyeSquintRight', smileR * 0.35);
            add('cheekSquintLeft', smileL * 0.25);
            add('cheekSquintRight', smileR * 0.25);

            let jaw = 0;
            Object.entries(JAW_OPENNESS).forEach(([viseme, k]) => { jaw += (this.visemeWeights[viseme] || 0) * k; });
            add('jawOpen', Math.min(1, jaw) * 0.15);

            add('browInnerUp', flashing * 0.8);
            add('browOuterUpLeft', flashing * 0.6);
            add('browOuterUpRight', flashing * 0.6);

            raise('eyeBlinkLeft', this.blinkValue());
            raise('eyeBlinkRight', this.blinkValue(BLINK_SIDE_OFFSET));
            raise('eyeLookUpLeft', this.eyeLook.up);
            raise('eyeLookUpRight', this.eyeLook.up);
            raise('eyeLookDownLeft', this.eyeLook.down);
            raise('eyeLookDownRight', this.eyeLook.down);
        } else {
            out.eyesClosed = Math.max(out.eyesClosed || 0, this.blinkValue());
            out.eyesLookUp = Math.max(out.eyesLookUp || 0, this.eyeLook.up);
            out.eyesLookDown = Math.max(out.eyesLookDown || 0, this.eyeLook.down);
        }
        Object.assign(out, this.override);

        // Anything driven last frame but not now (a cleared override, frames that ended) returns to rest
        this.written.forEach((name) => { if (!(name in out)) out[name] = 0; });
        this.written = new Set(Object.keys(out));

        this.meshes.forEach((mesh) => {
            const dict = mesh.morphTargetDictionary;
            const influences = mesh.morphTargetInfluences;
            Object.entries(out).forEach(([name, weight]) => {
                const index = dict[this.avatar.morph(name)];
                if (index !== undefined) influences[index] = Math.min(1, Math.max(0, weight));
            });
        });
    }
}
