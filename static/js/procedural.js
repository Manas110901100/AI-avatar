import * as THREE from 'three';

// Layers added on top of the animated pose every frame: breathing and posture on the spine,
// head nods/tilts/shakes and speech-driven beats on the neck and head, and eye gaze.

const GAZE_POINTS = {
    // Offsets from the head, in the avatar's frame (its left = +X, forward = +Z)
    away_left: [0.9, 0.05, 1.4],
    away_right: [-0.9, 0.05, 1.4],
    up: [0.45, 0.75, 1.3],
    up_right: [-0.45, 0.75, 1.3],
    down: [0.25, -0.85, 1.1],
};
// Eye-bone limits come from the avatar config: the original avatar's eyes are shallow caps
// pivoting off-centre (tight limits); rigs with spherical eyes can turn much further.
const DEFAULT_EYE_LIMITS = { yaw: 0.3, up: 0.2, down: 0.07 };

function approach(current, target, dt, seconds) {
    return target + (current - target) * Math.exp(-dt / Math.max(seconds, 1e-3));
}

function bump(x) {
    return x <= 0 || x >= 1 ? 0 : Math.sin(Math.PI * x);
}

function ease(x) {
    x = Math.min(1, Math.max(0, x));
    return x * x * (3 - 2 * x);
}

const _q = new THREE.Quaternion();
const _e = new THREE.Euler();
const _v = new THREE.Vector3();
const _w = new THREE.Vector3();
const _hq = new THREE.Quaternion();

export class Procedural {
    constructor(avatar, persona) {
        this.avatar = avatar;
        this.persona = persona;
        this.time = 0;
        const b = (name) => avatar.bone(name);
        this.spine = [b('Spine'), b('Spine1'), b('Spine2')].filter(Boolean);
        this.neck = b('Neck');
        this.head = b('Head');
        this.eyes = [b('LeftEye'), b('RightEye')].filter(Boolean).map((bone) => ({ bone, rest: bone.quaternion.clone() }));
        this.eyeLimits = { ...DEFAULT_EYE_LIMITS, ...(avatar.config?.eyes || {}) };

        this.posture = { pitch: 0, roll: 0, yaw: 0, lean: 0 };
        this.postureTarget = { pitch: 0, roll: 0, yaw: 0, lean: 0 };
        this.listening = 0;
        this.listeningTarget = 0;
        this.moves = [];

        this.gaze = 'camera';
        this.gazePoint = new THREE.Vector3(0, 1.6, 2);
        this.headAim = { yaw: 0, pitch: 0 };
        this.saccade = new THREE.Vector3();
        this.nextSaccade = 0;
        this.wanderPoint = new THREE.Vector3();
        this.eyeAngles = { yaw: 0, pitch: 0 };

        this.speech = { level: 0, average: 0, cooldown: 0 };
    }

    setPosture(pose = {}, intensity = 1) {
        ['pitch', 'roll', 'yaw', 'lean'].forEach((k) => {
            this.postureTarget[k] = (pose[k] || 0) * intensity;
        });
    }

    setListening(on) {
        this.listeningTarget = on ? 1 : 0;
    }

    setGaze(target) {
        if (target === 'wander') {
            const side = Math.random() < 0.5 ? 1 : -1;
            this.wanderPoint.set(side * (0.35 + Math.random() * 0.5), (Math.random() - 0.35) * 0.4, 1.6);
        }
        this.gaze = target;
    }

    // move: nod | small_nod | tilt | shake | chin_up | lean_in
    addHeadMove(move, strength = 0.5, hold = 1.2) {
        const s = 0.6 + 0.8 * strength;
        const t0 = this.time;
        const sustained = (length, peak) => (t) => {
            const x = t - t0;
            const span = Math.max(length, 0.6);
            if (x < 0 || x > span + 0.5) return null;
            return peak * Math.min(ease(x / 0.35), 1 - ease((x - span) / 0.5));
        };
        const shapes = {
            nod: (t) => { const x = (t - t0) / 0.5; return x > 1 ? null : { pitch: 0.12 * s * bump(x) }; },
            small_nod: (t) => { const x = (t - t0) / 0.4; return x > 1 ? null : { pitch: 0.06 * s * bump(x) }; },
            shake: (t) => { const x = (t - t0) / 0.8; return x > 1 ? null : { yaw: 0.09 * s * Math.sin(x * Math.PI * 4) * bump(x) }; },
            tilt: (t) => { const k = sustained(hold, 1)(t); return k === null ? null : { roll: 0.1 * s * k }; },
            chin_up: (t) => { const k = sustained(hold, 1)(t); return k === null ? null : { pitch: -0.07 * s * k }; },
            lean_in: (t) => { const k = sustained(hold, 1)(t); return k === null ? null : { lean: 0.06 * s * k, pitch: 0.03 * s * k }; },
        };
        if (shapes[move]) this.moves.push(shapes[move]);
    }

    // Loudness of the voice, 0..1, measured by the director's analyser each frame
    setSpeechLevel(level) {
        const sp = this.speech;
        sp.level = level;
        sp.average = approach(sp.average, level, 1 / 60, 0.6);
        if (sp.cooldown <= 0 && level > 0.08 && level > sp.average * 1.5) {
            this.addHeadMove('small_nod', 0.25 * this.persona.headBeatScale);
            sp.cooldown = 0.45 + Math.random() * 0.4;
        }
    }

    // Spine layer: runs before the gesture synth so hands follow the chest
    updateBody(dt, synth) {
        this.time += dt;
        this.speech.cooldown -= dt;
        Object.keys(this.posture).forEach((k) => {
            this.posture[k] = approach(this.posture[k], this.postureTarget[k], dt, this.persona.expressionSpeed * 1.6);
        });
        this.listening = approach(this.listening, this.listeningTarget, dt, 0.6);

        let lean = this.posture.lean + this.listening * 0.04 + (synth ? synth.lean : 0);
        this.moves.forEach((m) => { lean += m(this.time)?.lean || 0; });

        const breath = Math.sin(this.time * Math.PI * 2 / 4.2) * 0.012 * this.persona.idleAmplitude;
        const share = [0.4, 0.3, 0.3];
        this.spine.forEach((bone, i) => {
            _q.setFromEuler(_e.set((lean + (i > 0 ? breath : 0)) * share[i], 0, 0));
            bone.quaternion.multiply(_q);
            bone.updateMatrixWorld(true);
        });
    }

    gazeTarget(cameraPos, out) {
        const head = this.head.getWorldPosition(_w);
        if (this.gaze === 'camera') return out.copy(cameraPos).add(this.saccade);
        if (this.gaze === 'wander') return out.copy(cameraPos).add(this.wanderPoint);
        const p = GAZE_POINTS[this.gaze] || GAZE_POINTS.up;
        return out.set(p[0], p[1], p[2]).applyQuaternion(this.avatar.root.quaternion).add(head);
    }

    // Head, neck and eyes: runs last so it sits on top of clips and gestures
    updateHead(dt, cameraPos, synth) {
        if (!this.head) return;
        const t = this.time;

        // Small eye jumps while holding eye contact
        if (t >= this.nextSaccade) {
            this.saccade.set((Math.random() - 0.5) * 0.06, (Math.random() - 0.5) * 0.03, 0);
            this.nextSaccade = t + 0.4 + Math.random() * 1.2;
        }

        // Eyes jump fast, the head follows slowly and only part of the way
        const target = this.gazeTarget(cameraPos, _v);
        this.gazePoint.lerp(target, 1 - Math.exp(-dt / 0.05));

        const headPos = this.head.getWorldPosition(_w);
        const toTarget = _v.copy(this.gazePoint).sub(headPos);
        const inv = this.head.parent.getWorldQuaternion(_hq).invert();
        toTarget.applyQuaternion(inv).normalize();
        const follow = this.gaze === 'camera' ? 0.25 : 0.45;
        const aimYaw = Math.atan2(toTarget.x, toTarget.z) * follow;
        const aimPitch = -Math.asin(THREE.MathUtils.clamp(toTarget.y, -1, 1)) * follow;
        this.headAim.yaw = approach(this.headAim.yaw, THREE.MathUtils.clamp(aimYaw, -0.35, 0.35), dt, 0.45);
        this.headAim.pitch = approach(this.headAim.pitch, THREE.MathUtils.clamp(aimPitch, -0.25, 0.25), dt, 0.45);

        let pitch = this.posture.pitch + this.headAim.pitch + this.listening * 0.03 + (synth ? synth.pitch : 0);
        let yaw = this.posture.yaw + this.headAim.yaw;
        let roll = this.posture.roll + this.listening * 0.05 + (synth ? synth.roll : 0);

        this.moves = this.moves.filter((m) => {
            const r = m(t);
            if (!r) return false;
            pitch += r.pitch || 0;
            yaw += r.yaw || 0;
            roll += r.roll || 0;
            return true;
        });

        // Idle life: slow, small drift that never repeats exactly
        const a = 0.025 * this.persona.idleAmplitude * (1 + this.speech.level * 2);
        pitch += Math.sin(t * 0.53) * a * 0.6 + Math.sin(t * 1.31) * a * 0.3;
        yaw += Math.sin(t * 0.37 + 1.7) * a;
        roll += Math.sin(t * 0.29 + 0.4) * a * 0.5;

        [[this.neck, 0.35], [this.head, 0.65]].forEach(([bone, share]) => {
            if (!bone) return;
            _q.setFromEuler(_e.set(pitch * share, yaw * share, roll * share, 'YXZ'));
            bone.quaternion.multiply(_q);
            bone.updateMatrixWorld(true);
        });

        this.updateEyes(dt);
    }

    updateEyes(dt) {
        let yaw = 0;
        let pitch = 0;
        this.eyes.forEach(({ bone, rest }) => {
            const eyePos = bone.getWorldPosition(_w);
            const dir = _v.copy(this.gazePoint).sub(eyePos);
            dir.applyQuaternion(bone.parent.getWorldQuaternion(_hq).invert()).applyQuaternion(_q.copy(rest).invert()).normalize();
            const limits = this.eyeLimits;
            yaw = THREE.MathUtils.clamp(Math.atan2(dir.x, dir.z), -limits.yaw, limits.yaw);
            pitch = THREE.MathUtils.clamp(-Math.asin(THREE.MathUtils.clamp(dir.y, -1, 1)), -0.5, 0.5);
            _q.setFromEuler(_e.set(THREE.MathUtils.clamp(pitch, -limits.up, limits.down), yaw, 0, 'YXZ'));
            bone.quaternion.copy(rest).multiply(_q);
        });
        this.eyeAngles.yaw = yaw;
        this.eyeAngles.pitch = pitch;
    }
}
