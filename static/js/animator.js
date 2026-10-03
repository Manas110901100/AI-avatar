import * as THREE from 'three';
import { loadClip } from './avatar.js';

const IDLE_CLIP = '/static/weight shift.glb';
const TALK_CLIPS = ['/static/Talking_1.glb', '/static/Talking_2.glb'];
const GESTURE_FADE_IN = 0.3;
const GESTURE_FADE_OUT = 0.45;

function approach(current, target, dt, seconds) {
    return target + (current - target) * Math.exp(-dt / Math.max(seconds, 1e-3));
}

// Layered mixer. The lower body always plays the idle. The upper body blends idle, a talking
// loop and recorded gesture clips, with weights that always sum to 1 so the bind pose never leaks in.
export class Animator {
    constructor(avatar, persona) {
        this.avatar = avatar;
        this.persona = persona;
        this.mixer = new THREE.AnimationMixer(avatar.root);
        this.clips = new Map();
        this.speaking = false;
        this.talkWeight = 0;
        this.talkMix = 0;
        this.talkMixTarget = 0;
        this.gesture = null; // { action, start, end }
        this.fading = []; // gestures cut short by a newer one
        this.time = 0;
    }

    async init(gestureFiles) {
        const [idle, ...talk] = await Promise.all([IDLE_CLIP, ...TALK_CLIPS].map((url) => loadClip(url, this.avatar)));

        this.idleLower = this.loop(idle.lower, 1);
        this.idleUpper = this.loop(idle.upper, 1);
        this.talk = talk.filter(Boolean).map((clip) => this.loop(clip.upper, 0));

        // Preload every recorded gesture so it starts on its word, not after a download
        await Promise.all(gestureFiles.map(async (file) => {
            try {
                const clip = await loadClip(`/static/${file}`, this.avatar);
                if (clip) this.clips.set(file, clip);
            } catch (err) {
                console.warn(`Gesture clip failed to load: ${file}`, err);
            }
        }));
    }

    loop(clip, weight) {
        const action = this.mixer.clipAction(clip);
        action.setLoop(THREE.LoopRepeat);
        action.setEffectiveWeight(weight);
        action.play();
        return action;
    }

    setSpeaking(speaking) {
        if (speaking && !this.speaking && this.talk.length > 1) {
            this.talkMixTarget = 1 - this.talkMixTarget; // alternate loops between replies
        }
        this.speaking = speaking;
    }

    get gestureBusy() {
        return Boolean(this.gesture);
    }

    playClip(file, duration) {
        const clip = this.clips.get(file);
        if (!clip) return false;
        if (this.gesture) this.fading.push({ action: this.gesture.action, weight: this.gesture.action.getEffectiveWeight() });

        const action = this.mixer.clipAction(clip.upper);
        this.fading = this.fading.filter((f) => f.action !== action);
        action.reset();
        action.setLoop(THREE.LoopOnce);
        action.clampWhenFinished = true;
        action.setEffectiveWeight(0);
        action.play();
        const length = Math.min(clip.duration, duration || clip.duration);
        this.gesture = { action, start: this.time, end: this.time + length };
        return true;
    }

    update(dt) {
        this.time += dt;

        this.talkWeight = approach(this.talkWeight, this.speaking ? this.persona.talkLoopWeight : 0, dt, 0.35);
        this.talkMix = approach(this.talkMix, this.talkMixTarget, dt, 0.6);

        let gestureWeight = 0;
        const g = this.gesture;
        if (g) {
            const fadeIn = Math.min(1, (this.time - g.start) / GESTURE_FADE_IN);
            const fadeOut = Math.min(1, Math.max(0, (g.end - this.time) / GESTURE_FADE_OUT));
            gestureWeight = smooth(Math.min(fadeIn, fadeOut));
            g.action.setEffectiveWeight(gestureWeight);
            if (this.time >= g.end) {
                g.action.stop();
                this.gesture = null;
                gestureWeight = 0;
            }
        }

        // Weights above 1 in total are averaged by the mixer, so a cut-short gesture can fade over the new one
        this.fading = this.fading.filter((f) => {
            f.weight = approach(f.weight, 0, dt, GESTURE_FADE_OUT / 3);
            f.action.setEffectiveWeight(f.weight);
            if (f.weight > 0.01) return true;
            f.action.stop();
            return false;
        });

        const base = 1 - gestureWeight;
        this.idleLower.setEffectiveWeight(1);
        this.idleUpper.setEffectiveWeight(base * (1 - this.talkWeight));
        if (this.talk.length) {
            const mix = this.talk.length > 1 ? this.talkMix : 0;
            this.talk[0].setEffectiveWeight(base * this.talkWeight * (1 - mix));
            if (this.talk[1]) this.talk[1].setEffectiveWeight(base * this.talkWeight * mix);
        }

        this.mixer.update(dt);
    }
}

function smooth(x) {
    return x * x * (3 - 2 * x);
}
