import * as THREE from 'three';

const FINGERS = ['Thumb', 'Index', 'Middle', 'Ring', 'Pinky'];

// Curl angles (radians) for joints 1-3 of each finger
const EXTENDED = [0.04, 0.06, 0.04];
const CURLED = [1.25, 1.45, 1.0];
const THUMB_OPEN = [0.0, 0.05, 0.05];
const THUMB_TUCKED = [0.45, 0.55, 0.35];

export const HAND_POSES = {
    open: { Thumb: THUMB_OPEN, Index: EXTENDED, Middle: EXTENDED, Ring: EXTENDED, Pinky: EXTENDED },
    relaxed: { Thumb: [0.15, 0.2, 0.15], Index: [0.2, 0.3, 0.2], Middle: [0.25, 0.35, 0.25], Ring: [0.3, 0.4, 0.3], Pinky: [0.35, 0.45, 0.3] },
    fist: { Thumb: THUMB_TUCKED, Index: CURLED, Middle: CURLED, Ring: CURLED, Pinky: CURLED },
    point: { Thumb: THUMB_TUCKED, Index: EXTENDED, Middle: CURLED, Ring: CURLED, Pinky: CURLED },
    thinker: { Thumb: [0.25, 0.3, 0.2], Index: [0.45, 0.6, 0.4], Middle: [1.1, 1.3, 0.9], Ring: [1.15, 1.35, 0.9], Pinky: [1.2, 1.4, 0.9] },
};

// Per-joint mix of two hand poses (k = 0 → a, 1 → b)
export function blendPose(a, b, k) {
    const pose = {};
    Object.keys(b).forEach((finger) => {
        const from = a[finger] || b[finger];
        pose[finger] = b[finger].map((angle, i) => from[i] + (angle - from[i]) * k);
    });
    return pose;
}

// Fingers raised in counting order: index, middle, ring, pinky, then thumb
export function countPose(n) {
    const order = ['Index', 'Middle', 'Ring', 'Pinky', 'Thumb'];
    const pose = { ...HAND_POSES.fist };
    order.slice(0, Math.max(1, Math.min(5, n))).forEach((finger) => {
        pose[finger] = finger === 'Thumb' ? THUMB_OPEN : EXTENDED;
    });
    return pose;
}

const _a = new THREE.Vector3();
const _b = new THREE.Vector3();
const _c = new THREE.Vector3();
const _p = new THREE.Vector3();
const _e = new THREE.Vector3();
const _w = new THREE.Vector3();
const _h = new THREE.Vector3();
const _u = new THREE.Vector3();
const _f = new THREE.Vector3();
const _q = new THREE.Quaternion();
const _pq = new THREE.Quaternion();
const _mL = new THREE.Matrix4();
const _mW = new THREE.Matrix4();
const _x = new THREE.Vector3();
const _y = new THREE.Vector3();
const _z = new THREE.Vector3();

function basis(primary, secondary, out) {
    _x.copy(primary).normalize();
    _z.crossVectors(_x, secondary);
    if (_z.lengthSq() < 1e-8) _z.set(0, 0, 1).cross(_x); // secondary parallel to primary
    _z.normalize();
    _y.crossVectors(_z, _x);
    return out.makeBasis(_x, _y, _z);
}

// Rotation that takes the local pair (aL, bL) onto the world pair (aW, bW), exact on the primary axis
function frameRotation(aL, bL, aW, bW, out) {
    basis(aL, bL, _mL).transpose();
    basis(aW, bW, _mW).multiply(_mL);
    return out.setFromRotationMatrix(_mW);
}

function blendWorldRotation(bone, worldQ, weight) {
    bone.parent.getWorldQuaternion(_pq);
    _q.copy(_pq).invert().multiply(worldQ);
    bone.quaternion.slerp(_q, weight);
    bone.updateMatrixWorld(true);
}

// One arm: analytic two-bone IK with an elbow pole, a hinge-locked elbow, wrist orientation and finger poses.
// Every axis is measured from the avatar's rest pose at construction, so nothing assumes a particular rig.
export class ArmRig {
    constructor(avatar, side) {
        this.side = side;
        this.sign = side === 'Left' ? 1 : -1;
        const bone = (name) => avatar.bone(`${side}${name}`);
        this.shoulder = bone('Shoulder');
        this.upper = bone('Arm');
        this.fore = bone('ForeArm');
        this.hand = bone('Hand');
        this.twist = bone('ForeArmTwist'); // optional: shares the wrist's roll with the forearm skin
        this.ok = Boolean(this.shoulder && this.upper && this.fore && this.hand && bone('HandMiddle1'));
        if (this.ok) this.calibrate(avatar, bone);
    }

    calibrate(avatar, bone) {
        avatar.root.updateMatrixWorld(true);
        const worldQ = (node) => node.getWorldQuaternion(new THREE.Quaternion());
        const worldP = (node) => node.getWorldPosition(new THREE.Vector3());

        const shoulderJoint = worldP(this.upper);
        const elbow = worldP(this.fore);
        const wrist = worldP(this.hand);
        this.l1 = shoulderJoint.distanceTo(elbow);
        this.l2 = elbow.distanceTo(wrist);

        this.upperAxis = this.fore.position.clone().normalize();
        this.foreAxis = this.hand.position.clone().normalize();
        this.handRestInverse = this.hand.quaternion.clone().invert();
        this.twistRest = this.twist ? this.twist.quaternion.clone() : null;
        this.handAxis = bone('HandMiddle1').position.clone().normalize();

        // The elbow flexes the forearm toward the avatar's front
        const forward = new THREE.Vector3(0, 0, 1).applyQuaternion(worldQ(avatar.root));
        const hinge = new THREE.Vector3().subVectors(elbow, shoulderJoint).normalize().cross(forward).normalize();
        this.upperHinge = hinge.clone().applyQuaternion(worldQ(this.upper).invert());
        this.foreHinge = hinge.clone().applyQuaternion(worldQ(this.fore).invert());

        // Palm normal from the knuckle line and the hand's length; the sign flips between hands
        const index = bone('HandIndex1') || bone('HandMiddle1');
        const pinky = bone('HandPinky1') || bone('HandRing1') || bone('HandMiddle1');
        const across = new THREE.Vector3().subVectors(worldP(index), worldP(pinky));
        const along = new THREE.Vector3().subVectors(worldP(bone('HandMiddle1')), wrist);
        const palm = across.cross(along).normalize().multiplyScalar(-this.sign);
        if (palm.lengthSq() < 0.5) palm.set(0, -1, 0);
        this.handPalm = palm.clone().applyQuaternion(worldQ(this.hand).invert());

        // Each finger joint curls about the axis that turns it toward the palm
        this.fingers = FINGERS.map((name) => {
            const joints = [1, 2, 3].map((i) => bone(`Hand${name}${i}`)).filter(Boolean).map((joint) => {
                const child = joint.children.find((c) => c.isBone);
                const dir = child ? child.position.clone().normalize() : new THREE.Vector3(0, 1, 0);
                const palmLocal = palm.clone().applyQuaternion(worldQ(joint).invert());
                const axis = new THREE.Vector3().crossVectors(dir, palmLocal).normalize();
                return { bone: joint, axis, rest: joint.quaternion.clone() };
            });
            return { name, joints };
        });
    }

    // Raise (positive) or drop the shoulder, in radians
    raiseShoulder(angle, root) {
        if (!this.ok || !angle) return;
        const up = _a.set(0, 1, 0);
        const side = _b.set(this.sign, 0, 0).applyQuaternion(root.getWorldQuaternion(_q));
        const axis = _c.crossVectors(side, up).normalize();
        const delta = new THREE.Quaternion().setFromAxisAngle(axis, angle);
        const target = this.shoulder.getWorldQuaternion(new THREE.Quaternion()).premultiply(delta);
        blendWorldRotation(this.shoulder, target, 1);
    }

    // Moves the wrist toward `target` (world). `pole` is the direction the elbow should point;
    // `fingerDir` and `palm` orient the hand. All blended over the current pose by `weight`.
    solve(target, pole, fingerDir, palm, weight) {
        if (!this.ok || weight <= 0) return;
        const { l1, l2 } = this;
        const shoulderJoint = this.upper.getWorldPosition(_a);

        const toTarget = _b.subVectors(target, shoulderJoint);
        const reach = THREE.MathUtils.clamp(toTarget.length(), Math.abs(l1 - l2) + 1e-3, (l1 + l2) * 0.999);
        const dir = toTarget.normalize();
        const along = (l1 * l1 - l2 * l2 + reach * reach) / (2 * reach);
        const lift = Math.sqrt(Math.max(l1 * l1 - along * along, 0));

        const bend = _p.copy(pole).addScaledVector(dir, -pole.dot(dir));
        if (bend.lengthSq() < 1e-8) bend.set(0, -1, 0).addScaledVector(dir, dir.y);
        bend.normalize();

        const elbow = _e.copy(shoulderJoint).addScaledVector(dir, along).addScaledVector(bend, lift);
        const wrist = _w.copy(shoulderJoint).addScaledVector(dir, reach);
        const hinge = _h.crossVectors(bend, dir).normalize();

        const upperDir = _u.subVectors(elbow, shoulderJoint).normalize();
        blendWorldRotation(this.upper, frameRotation(this.upperAxis, this.upperHinge, upperDir, hinge, new THREE.Quaternion()), weight);

        const foreDir = _f.subVectors(wrist, this.fore.getWorldPosition(_c)).normalize();
        blendWorldRotation(this.fore, frameRotation(this.foreAxis, this.foreHinge, foreDir, hinge, new THREE.Quaternion()), weight);

        if (fingerDir && palm) {
            blendWorldRotation(this.hand, frameRotation(this.handAxis, this.handPalm, fingerDir, palm, new THREE.Quaternion()), weight);
        }
    }

    // Give the twist bone `share` of the hand's roll about the forearm, so the wrist doesn't
    // wring like a candy wrapper when the palm turns over. Runs every frame, clips included.
    updateTwist(share = 0.5) {
        if (!this.ok || !this.twist) return;
        _q.copy(this.hand.quaternion).multiply(this.handRestInverse); // roll since rest, in forearm space
        const along = _a.set(_q.x, _q.y, _q.z).dot(this.foreAxis);
        _pq.set(this.foreAxis.x * along, this.foreAxis.y * along, this.foreAxis.z * along, _q.w);
        if (_pq.lengthSq() < 1e-10) return;
        _pq.normalize();
        this.twist.quaternion.copy(this.twistRest).multiply(_q.identity().slerp(_pq, share));
    }

    setHand(pose, weight) {
        if (!this.ok || weight <= 0 || !pose) return;
        this.fingers.forEach(({ name, joints }) => {
            const angles = pose[name];
            if (!angles) return;
            joints.forEach((joint, i) => {
                _q.setFromAxisAngle(joint.axis, angles[i] ?? 0).premultiply(joint.rest);
                joint.bone.quaternion.slerp(_q, weight);
            });
        });
    }
}
