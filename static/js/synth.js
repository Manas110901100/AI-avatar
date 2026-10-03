import * as THREE from 'three';
import { ArmRig, HAND_POSES, blendPose, countPose } from './ik.js';

// Procedural gestures, synthesized live from the skeleton. Every gesture runs
// prepare → stroke → hold → retract, and its stroke is the moment the timeline aligns to a word.
//
// Geometry is authored in the avatar's rest frame (metres, Y up, facing +Z, its left = +X) and
// `s` mirrors it per hand (+1 left, -1 right). Points and directions follow the chest (or head) as
// the body moves; directions keep their length, so accents carry their size in metres.

const v = (x, y, z) => new THREE.Vector3(x, y, z);

const ACTIONS = {
    point_at_viewer: {
        hands: 'one',
        pose: (s, ctx) => {
            const wrist = ctx.toCamera(s, 0.40).add(ctx.chest(v(0, -0.05, 0), true));
            return {
                wrist,
                fingerDir: ctx.cameraFrom(wrist),
                palm: ctx.chest(v(-s * 0.45, -0.9, 0), true),
                pole: ctx.chest(v(s * 0.5, -0.8, -0.3), true),
                hand: HAND_POSES.point,
                accent: ctx.cameraFrom(wrist).multiplyScalar(0.03),
                lean: 0.03,
            };
        },
    },
    open_palms: {
        hands: 'both',
        pose: (s, ctx, t) => ({
            wrist: ctx.shoulder(s, v(s * (0.04 + 0.03 * t.hold), -0.34, 0.30)),
            fingerDir: ctx.chest(v(s * 0.35, 0.1, 1), true),
            palm: ctx.chest(v(-s * 0.3, 1, 0.05), true),
            pole: ctx.chest(v(s * 0.6, -0.7, -0.3), true),
            hand: HAND_POSES.open,
            accent: ctx.chest(v(0, 0.015, 0.01), true),
        }),
    },
    hand_on_chest: {
        hands: 'one',
        defaultHand: 'right',
        pose: (s, ctx) => {
            const fingerDir = ctx.chest(v(-s * 0.92, 0.38, 0).normalize(), true);
            const palmCenter = ctx.chest(v(0.075, 1.365, 0.14));
            return {
                wrist: palmCenter.addScaledVector(fingerDir, -0.085),
                fingerDir,
                palm: ctx.chest(v(0, 0, -1), true),
                pole: ctx.chest(v(s * 0.8, -0.6, 0), true),
                hand: HAND_POSES.open,
                lean: 0.02,
                roll: 0.04,
            };
        },
    },
    shrug: {
        hands: 'both',
        pose: (s, ctx, t) => ({
            wrist: ctx.shoulder(s, v(s * 0.10, -0.40, 0.18)),
            fingerDir: ctx.chest(v(s * 0.55, 0, 0.85), true),
            palm: ctx.chest(v(-s * 0.15, 1, 0), true),
            pole: ctx.chest(v(s * 0.7, -0.6, -0.4), true),
            hand: HAND_POSES.open,
            shoulder: (0.10 + 0.12 * t.force) * (1 - 0.35 * t.hold),
            roll: 0.08,
            lean: -0.02,
        }),
    },
    count: {
        hands: 'one',
        pose: (s, ctx, t) => ({
            wrist: ctx.shoulder(s, v(-s * 0.03, -0.17, 0.30)),
            fingerDir: ctx.chest(v(-s * 0.15, 1, 0.25), true),
            palm: ctx.chest(v(-s * 0.2, 0, 1), true),
            pole: ctx.chest(v(s * 0.6, -0.8, -0.1), true),
            hand: blendPose(countPose(t.previousCount), countPose(t.count), t.countChange),
            accent: ctx.chest(v(0, 0, 0.02), true),
        }),
    },
    hand_to_chin: {
        hands: 'one',
        defaultHand: 'right',
        pose: (s, ctx) => {
            const fingerDir = ctx.head(v(-s * 0.1, 0.85, -0.25).normalize(), true);
            const fist = ctx.head(v(0, 1.638 - 0.115, 0.12));
            return {
                wrist: fist.addScaledVector(fingerDir, -0.07),
                fingerDir,
                palm: ctx.head(v(0, 0, -1), true),
                pole: ctx.chest(v(s * 0.4, -1, 0.3), true),
                hand: HAND_POSES.thinker,
                roll: -0.05,
                pitch: 0.04,
            };
        },
    },
    wave: {
        hands: 'one',
        pose: (s, ctx, t) => {
            const swing = Math.sin(t.holdTime * Math.PI * 2 * 2.2) * 0.35 * t.hold;
            const fingerDir = ctx.chest(v(s * 0.1 + Math.sin(swing) * s, Math.cos(swing), 0.05), true);
            return {
                wrist: ctx.shoulder(s, v(s * (0.14 + 0.02 * Math.sin(swing)), 0.12, 0.16)),
                fingerDir,
                palm: ctx.chest(v(0, 0, 1), true),
                pole: ctx.chest(v(s * 0.6, -1, -0.1), true),
                hand: HAND_POSES.open,
            };
        },
    },
    beat: {
        hands: 'one',
        pose: (s, ctx) => ({
            wrist: ctx.shoulder(s, v(0, -0.30, 0.26)),
            fingerDir: ctx.chest(v(-s * 0.25, -0.05, 1), true),
            palm: ctx.chest(v(-s * 0.35, -1, 0), true),
            pole: ctx.chest(v(s * 0.6, -0.7, -0.3), true),
            hand: HAND_POSES.relaxed,
            accent: ctx.chest(v(0, -0.045, 0.01), true),
        }),
    },
};

const DEFAULTS = { duration: 1.6, stroke: 0.45 };

function ease(x) {
    x = Math.min(1, Math.max(0, x));
    return x * x * (3 - 2 * x);
}

function bump(x) {
    return Math.abs(x) >= 1 ? 0 : (1 - x * x) * (1 - x * x);
}

export class GestureSynth {
    constructor(avatar, stage, persona) {
        this.avatar = avatar;
        this.stage = stage;
        this.persona = persona;
        this.arms = { Left: new ArmRig(avatar, 'Left'), Right: new ArmRig(avatar, 'Right') };
        this.active = [];
        this.time = 0;
        this.lean = 0;
        this.roll = 0;
        this.pitch = 0;

        // Rest frames of the chest and head, so authored points follow the body as it moves
        avatar.root.updateMatrixWorld(true);
        const restInverse = (node) => (node ? node.matrixWorld.clone().invert() : new THREE.Matrix4());
        this.chestBone = avatar.bone('Spine2') || avatar.bone('Spine1');
        this.headBone = avatar.bone('Head');
        this.chestRestInverse = restInverse(this.chestBone);
        this.headRestInverse = restInverse(this.headBone);
        this.shoulderRest = {
            1: this.arms.Left.ok ? this.arms.Left.upper.getWorldPosition(new THREE.Vector3()) : v(0.16, 1.53, -0.04),
            [-1]: this.arms.Right.ok ? this.arms.Right.upper.getWorldPosition(new THREE.Vector3()) : v(-0.16, 1.53, -0.04),
        };
        this.ctx = this.makeContext();
    }

    makeContext() {
        const delta = new THREE.Matrix4();
        const rotation = new THREE.Quaternion();
        const scratch = new THREE.Vector3();
        const follow = (bone, restInverse, point, isDirection) => {
            if (!bone) return point;
            delta.multiplyMatrices(bone.matrixWorld, restInverse);
            if (!isDirection) return point.applyMatrix4(delta);
            delta.decompose(scratch, rotation, new THREE.Vector3());
            return point.applyQuaternion(rotation);
        };
        const camera = () => this.stage.camera.getWorldPosition(new THREE.Vector3());
        return {
            chest: (point, isDirection = false) => follow(this.chestBone, this.chestRestInverse, point, isDirection),
            head: (point, isDirection = false) => follow(this.headBone, this.headRestInverse, point, isDirection),
            shoulder: (s, offset) => follow(this.chestBone, this.chestRestInverse, offset.add(this.shoulderRest[s]), false),
            toCamera: (s, reach) => {
                const joint = (s > 0 ? this.arms.Left : this.arms.Right).upper.getWorldPosition(new THREE.Vector3());
                return camera().sub(joint).normalize().multiplyScalar(reach).add(joint);
            },
            cameraFrom: (point) => camera().sub(point).normalize(),
        };
    }

    // Starts a gesture now. `duration: Infinity` holds it until release().
    perform(name, params = {}) {
        const action = ACTIONS[name];
        if (!action) {
            console.warn(`Unknown procedural gesture: ${name}`);
            return null;
        }
        // The next item of a list: keep the raised hand and change fingers instead of starting over
        if (params.continues) {
            const live = this.active.find((g) => g.name === name && g.releasedAt === null);
            if (live) {
                live.previousCount = live.count;
                live.count = params.count ?? live.count + 1;
                live.countChangeAt = this.time;
                live.accentAt = this.time + 0.12;
                live.duration = (this.time - live.start) + (params.duration ?? DEFAULTS.duration);
                return live;
            }
        }

        let hand = params.hand || action.defaultHand || 'right';
        if (action.hands === 'both') hand = 'both';
        const sides = hand === 'both' ? [1, -1] : [hand === 'left' ? 1 : -1];

        // A new gesture takes over its arms; whatever held them retracts
        this.active.forEach((g) => {
            if (g.sides.some((s) => sides.includes(s))) this.release(g);
        });

        const duration = params.duration ?? DEFAULTS.duration;
        const stroke = Math.min(params.stroke ?? DEFAULTS.stroke, Number.isFinite(duration) ? duration * 0.6 : Infinity);
        const gesture = {
            name,
            action,
            sides,
            start: this.time,
            stroke: Math.max(0.15, stroke ?? DEFAULTS.stroke),
            duration,
            retract: Number.isFinite(duration) ? Math.min(0.5, duration * 0.3) : 0.5,
            force: params.force ?? 0.5,
            count: params.count ?? 1,
            previousCount: params.count ?? 1,
            countChangeAt: -Infinity,
            releasedAt: null,
            seed: Math.random() * 1000,
        };
        gesture.accentAt = gesture.start + gesture.stroke;
        this.active.push(gesture);
        return gesture;
    }

    release(gesture) {
        if (gesture && gesture.releasedAt === null) gesture.releasedAt = this.time;
    }

    releaseAll() {
        this.active.forEach((g) => this.release(g));
    }

    get busy() {
        return this.active.some((g) => g.releasedAt === null);
    }

    weightOf(g) {
        const t = this.time - g.start;
        const prepare = ease(t / g.stroke);
        let out = 1;
        if (g.releasedAt !== null) {
            out = 1 - ease((this.time - g.releasedAt) / g.retract);
        } else if (Number.isFinite(g.duration)) {
            out = ease((g.duration - t) / g.retract);
        }
        return Math.min(prepare, out);
    }

    // Runs after the mixer: blends each active gesture's IK pose over the animated pose.
    update(dt) {
        this.time += dt;
        let lean = 0;
        let roll = 0;
        let pitch = 0;

        this.active = this.active.filter((g) => {
            const weight = this.weightOf(g);
            const t = this.time - g.start;
            const finished = g.releasedAt !== null
                ? this.time - g.releasedAt >= g.retract
                : Number.isFinite(g.duration) && t >= g.duration;
            if (finished) return false;

            const holdSpan = Number.isFinite(g.duration) ? Math.max(0.01, g.duration - g.stroke - g.retract) : 4;
            const timing = {
                force: g.force,
                count: g.count,
                previousCount: g.previousCount,
                countChange: ease((this.time - g.countChangeAt) / 0.15),
                hold: ease((t - g.stroke) / holdSpan),
                holdTime: Math.max(0, t - g.stroke),
            };
            const accentAmount = bump((this.time - g.accentAt) / 0.18) * (0.5 + g.force) * this.persona.gestureScale;
            const drift = Math.sin(this.time * 1.3 + g.seed) * 0.006;

            g.sides.forEach((s) => {
                const arm = s > 0 ? this.arms.Left : this.arms.Right;
                if (!arm.ok) return;
                const pose = g.action.pose(s, this.ctx, timing);
                if (pose.accent) pose.wrist.addScaledVector(pose.accent, accentAmount);
                pose.wrist.y += drift;
                if (pose.shoulder) arm.raiseShoulder(pose.shoulder * weight, this.avatar.root);
                arm.solve(pose.wrist, pose.pole, pose.fingerDir, pose.palm, weight);
                arm.setHand(pose.hand, weight);
                lean = Math.max(lean, (pose.lean || 0) * weight);
                roll += (pose.roll || 0) * weight * -s;
                pitch += (pose.pitch || 0) * weight;
            });
            return true;
        });

        this.arms.Left.updateTwist();
        this.arms.Right.updateTwist();

        this.lean = lean;
        this.roll = roll;
        this.pitch = pitch;
    }
}

export const PROCEDURAL_GESTURES = Object.keys(ACTIONS);
