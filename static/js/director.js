import { EMOTION_POSES } from './face.js';

// The actor's character. Tune these to change how the whole performance reads.
export const PERSONA = {
    talkLoopWeight: 0.3, // how much of the talking loop shows through while speaking
    gestureScale: 0.9, // size of gesture accents
    autoBeat: 0.5, // chance an automatic emphasis beat is performed
    blinkInterval: [3.0, 6.0],
    gazeHold: [3.5, 8.0], // idle: seconds of eye contact before a glance away
    glance: [0.6, 1.4], // idle: seconds a glance lasts
    idleAmplitude: 0.7,
    headBeatScale: 0.7,
    expressionSpeed: 0.25, // seconds for the face to settle into a new expression
    thinkingHandDelay: 1.2, // seconds of thinking before the hand comes to the chin
    endHold: 0.6, // seconds the final expression holds after the last word
};

const LISTEN_TIMEOUT = 2.5;

function between([low, high]) {
    return low + Math.random() * (high - low);
}

// Runs the actor's states (idle, listening, thinking, speaking) and plays timelines against the audio clock.
export class Director {
    constructor({ animator, synth, procedural, face, stage }) {
        Object.assign(this, { animator, synth, procedural, face, stage });
        this.state = 'idle';
        this.time = 0;
        this.audio = new Audio();
        this.audioUrl = null;
        this.analyser = null;
        this.levels = null;

        this.listenUntil = 0;
        this.nextIdleGlance = between(PERSONA.gazeHold);
        this.glanceUntil = 0;
        this.nextListenNod = 0;
        this.thinkingSince = 0;
        this.thinkingHand = null;
        this.timeline = null;
        this.finished = null;
        this.pendingFlashes = [];

        this.setEmotion('neutral', 0);
    }

    // Must run inside a user gesture (a click or key press) so the browser lets audio start
    unlockAudio() {
        if (this.analyser) {
            this.audioContext.resume();
            return;
        }
        try {
            this.audioContext = new AudioContext();
            const source = this.audioContext.createMediaElementSource(this.audio);
            this.analyser = this.audioContext.createAnalyser();
            this.analyser.fftSize = 512;
            source.connect(this.analyser);
            this.analyser.connect(this.audioContext.destination);
            this.levels = new Float32Array(this.analyser.fftSize);
        } catch (err) {
            console.warn('Speech analysis unavailable; head beats will rely on the timeline only.', err);
        }
    }

    setEmotion(name, intensity) {
        this.face.setEmotion(name, intensity);
        this.procedural.setPosture(EMOTION_POSES[name] || EMOTION_POSES.neutral, intensity);
        this.stage.setMood(name);
    }

    notifyTyping() {
        this.listenUntil = this.time + LISTEN_TIMEOUT;
        if (this.state === 'idle') this.enterListening();
    }

    enterListening() {
        this.state = 'listening';
        this.procedural.setListening(true);
        this.procedural.setGaze('camera');
        this.setEmotion('curious', 0.3);
        this.nextListenNod = this.time + between([1.5, 3]);
    }

    enterIdle() {
        this.state = 'idle';
        this.procedural.setListening(false);
        this.procedural.setGaze('camera');
        this.setEmotion('neutral', 0);
        this.nextIdleGlance = this.time + between(PERSONA.gazeHold);
    }

    beginThinking() {
        this.unlockAudio();
        this.stopSpeaking();
        this.state = 'thinking';
        this.thinkingSince = this.time;
        this.procedural.setListening(false);
        this.procedural.setGaze(Math.random() < 0.5 ? 'up' : 'up_right');
        this.setEmotion('thoughtful', 0.6);
        this.procedural.addHeadMove('tilt', 0.4, 30);
    }

    endThinking() {
        if (this.thinkingHand) this.synth.release(this.thinkingHand);
        this.thinkingHand = null;
        this.procedural.moves = []; // drop the held thinking tilt
        if (this.state === 'thinking') this.enterIdle();
    }

    // response: the /chat/speak JSON, with `audioBlob` already decoded
    perform(response, audioBlob) {
        this.endThinking();
        if (this.audioUrl) URL.revokeObjectURL(this.audioUrl);
        this.audioUrl = URL.createObjectURL(audioBlob);
        this.audio.src = this.audioUrl;

        this.timeline = response.timeline;
        this.eventIndex = 0;
        this.clock = -(this.timeline.preroll || 0);
        this.audioStarted = false;
        this.endedAt = null;
        // Lip sync: voice-provided blend-shape frames, else viseme IDs, else Rhubarb-format cues
        this.face.setLipSync(response.lipsync);
        this.face.setVisemes(response.visemes, this.timeline.duration);
        this.face.setBlendshapes(response.blendshapes);
        this.state = 'speaking';
        this.animator.setSpeaking(true);

        return new Promise((resolve) => { this.finished = resolve; });
    }

    stopSpeaking() {
        if (this.state !== 'speaking') return;
        this.audio.pause();
        this.finishSpeaking();
    }

    finishSpeaking() {
        this.animator.setSpeaking(false);
        this.synth.releaseAll();
        this.face.setLipSync(null);
        this.face.setBlendshapes(null);
        this.timeline = null;
        this.enterIdle();
        if (this.finished) this.finished();
        this.finished = null;
    }

    fire(event) {
        const until = (event.until ?? event.t) - event.t;
        switch (event.type) {
            case 'emotion':
                this.setEmotion(event.emotion, event.intensity);
                break;
            case 'gaze':
                this.procedural.setGaze(event.target);
                break;
            case 'blink':
                this.face.blink();
                break;
            case 'shot':
                this.stage.setShot(event.shot, until);
                break;
            case 'head':
                this.procedural.addHeadMove(event.move, event.strength, until);
                this.face.browFlash(0.3 + 0.5 * (event.strength ?? 0.5));
                break;
            case 'gesture':
                this.gesture(event);
                break;
            default:
                break;
        }
    }

    gesture(event) {
        if (event.kind === 'clip') {
            this.synth.releaseAll(); // one arm gesture at a time
            this.animator.playClip(event.name, event.duration);
            return;
        }
        if (event.auto && (Math.random() > PERSONA.autoBeat || this.animator.gestureBusy || this.synth.busy)) return;
        this.synth.perform(event.name, event);
        if (event.force >= 0.5) {
            // Brows punctuate the stroke, not the preparation
            const flashAt = this.time + Math.max(0, (event.stroke ?? 0.4) - 0.1);
            this.pendingFlashes.push({ at: flashAt, strength: 0.25 + 0.4 * event.force });
        }
    }

    // seconds into the current audio, or null when silent
    get speechTime() {
        return this.state === 'speaking' && this.audioStarted && !this.audio.paused ? this.audio.currentTime : null;
    }

    update(dt) {
        this.time += dt;
        this.pendingFlashes = this.pendingFlashes.filter((flash) => {
            if (this.time < flash.at) return true;
            this.face.browFlash(flash.strength);
            return false;
        });

        if (this.state === 'speaking' && this.timeline) this.updateSpeaking(dt);
        if (this.state === 'listening' && this.time > this.listenUntil) this.enterIdle();
        if (this.state === 'listening' && this.time > this.nextListenNod) {
            this.procedural.addHeadMove('small_nod', 0.3);
            this.nextListenNod = this.time + between([2.5, 4.5]);
        }
        if (this.state === 'thinking' && !this.thinkingHand && this.time - this.thinkingSince > PERSONA.thinkingHandDelay) {
            this.thinkingHand = this.synth.perform('hand_to_chin', { duration: Infinity, stroke: 0.8 });
        }
        if (this.state === 'idle') this.updateIdle();

        this.procedural.setSpeechLevel(this.speechLevel());
    }

    updateSpeaking(dt) {
        if (!this.audioStarted) {
            this.clock += dt; // preroll: the face moves before the first word
            if (this.clock >= 0) {
                this.audioStarted = true;
                this.audio.play().catch((err) => {
                    console.error('Playback failed:', err);
                    this.finishSpeaking();
                });
            }
        } else if (!this.audio.ended) {
            this.clock = Math.max(this.clock, this.audio.currentTime);
        }

        const events = this.timeline?.events || [];
        while (this.eventIndex < events.length && events[this.eventIndex].t <= this.clock) {
            this.fire(events[this.eventIndex++]);
        }

        if (this.audioStarted && this.audio.ended) {
            if (this.endedAt === null) {
                this.endedAt = this.time;
                this.animator.setSpeaking(false);
            }
            if (this.time - this.endedAt > PERSONA.endHold) this.finishSpeaking();
        }
    }

    updateIdle() {
        if (this.glanceUntil && this.time > this.glanceUntil) {
            this.glanceUntil = 0;
            this.procedural.setGaze('camera');
            this.face.blink();
            this.nextIdleGlance = this.time + between(PERSONA.gazeHold);
        } else if (!this.glanceUntil && this.time > this.nextIdleGlance) {
            this.procedural.setGaze('wander');
            this.face.blink();
            this.glanceUntil = this.time + between(PERSONA.glance);
        }
    }

    speechLevel() {
        if (!this.analyser || this.speechTime === null) return 0;
        this.analyser.getFloatTimeDomainData(this.levels);
        let sum = 0;
        for (let i = 0; i < this.levels.length; i++) sum += this.levels[i] * this.levels[i];
        return Math.min(1, Math.sqrt(sum / this.levels.length) * 4);
    }
}
