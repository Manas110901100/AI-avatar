import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';

const loader = new GLTFLoader();

const LOWER_BODY = new Set([
    'Hips',
    'LeftUpLeg', 'LeftLeg', 'LeftFoot', 'LeftToeBase', 'LeftToe_End',
    'RightUpLeg', 'RightLeg', 'RightFoot', 'RightToeBase', 'RightToe_End',
]);

export function loadGLTF(url) {
    return new Promise((resolve, reject) => loader.load(url, resolve, undefined, reject));
}

// Avatar configs live in static/avatars/<id>/avatar.json: GLB path, eye limits and name aliases
export async function loadAvatarConfig(id) {
    const response = await fetch(`/static/avatars/${encodeURIComponent(id)}/avatar.json`);
    if (!response.ok) throw new Error(`Unknown avatar "${id}" (${response.status})`);
    return response.json();
}

// Loads the avatar and indexes what the rest of the engine drives: bones, morph targets, rest pose.
// Engine code asks for canonical (Mixamo / ARKit) names; `aliases` maps them to this rig's names.
export async function loadAvatar(config) {
    const gltf = await loadGLTF(config.glb);
    const root = gltf.scene;
    const bones = new Map();
    const morphMeshes = [];
    const boneAliases = config.aliases?.bones || {};
    const morphAliases = config.aliases?.morphs || {};

    root.traverse((node) => {
        if (node.isBone) bones.set(node.name, node);
        if (node.isMesh) {
            node.castShadow = true;
            node.frustumCulled = false; // skinned bounds don't follow the animation
            if (node.morphTargetDictionary) morphMeshes.push(node);
        }
    });
    Object.entries(boneAliases).forEach(([canonical, actual]) => {
        if (bones.has(actual)) bones.set(canonical, bones.get(actual));
    });

    root.updateMatrixWorld(true);
    const restLocal = new Map();
    bones.forEach((bone, name) => restLocal.set(name, bone.quaternion.clone()));

    const morphNames = new Set();
    morphMeshes.forEach((mesh) => Object.keys(mesh.morphTargetDictionary).forEach((n) => morphNames.add(n)));
    Object.entries(morphAliases).forEach(([canonical, actual]) => {
        if (morphNames.has(actual)) morphNames.add(canonical);
    });

    const has = (name) => morphNames.has(name);
    const capabilities = {
        arkit: ['eyeBlinkLeft', 'eyeBlinkRight', 'mouthSmileLeft', 'browInnerUp', 'jawOpen'].every(has),
        oculusVisemes: ['viseme_aa', 'viseme_PP', 'viseme_O'].every(has),
        legacyRPM: ['eyesClosed', 'mouthSmile'].every(has),
        eyeBones: bones.has('LeftEye') && bones.has('RightEye'),
        twistBones: bones.has('LeftForeArmTwist') && bones.has('RightForeArmTwist'),
    };

    return {
        config,
        root,
        bones,
        restLocal,
        morphMeshes,
        morphNames,
        capabilities,
        bone(name) {
            return bones.get(name) || null;
        },
        // The morph name on the mesh for a canonical name
        morph(name) {
            return morphAliases[name] || name;
        },
    };
}

// Maps a Mixamo clip onto the avatar's bones (the original filterTracks logic) and splits it
// into an upper-body clip and a lower-body clip so layers can drive them independently.
export function retargetClip(clip, sourceScene, avatar) {
    const hipsCorrection = hipsParentCorrection(sourceScene, avatar);
    const upper = [];
    const lower = [];

    clip.tracks.forEach((track) => {
        const parts = track.name.split('.');
        const prop = parts.pop();
        const boneName = parts.join('.').replace(/.*[:\.]?mixamorig:?/i, '');
        if (prop !== 'quaternion') return; // positions/scales would drift or shrink the avatar
        if (!avatar.bones.has(boneName) || boneName.includes('Eye')) return;

        const retargeted = track.clone();
        retargeted.name = `${boneName}.quaternion`;

        if (boneName === 'Hips') {
            // The clip's armature is rotated 90° (Z-up export); fold that into the hips keys
            // so the avatar keeps the weight-shift sway instead of lying down.
            const q = new THREE.Quaternion();
            const values = retargeted.values;
            for (let i = 0; i < values.length; i += 4) {
                q.fromArray(values, i).premultiply(hipsCorrection).toArray(values, i);
            }
        }
        (LOWER_BODY.has(boneName) ? lower : upper).push(retargeted);
    });

    return {
        upper: new THREE.AnimationClip(`${clip.name}:upper`, clip.duration, upper),
        lower: new THREE.AnimationClip(`${clip.name}:lower`, clip.duration, lower),
        duration: clip.duration,
    };
}

function hipsParentCorrection(sourceScene, avatar) {
    const correction = new THREE.Quaternion();
    let sourceHips = null;
    sourceScene.traverse((node) => {
        if (!sourceHips && /hips$/i.test(node.name)) sourceHips = node;
    });
    const avatarHips = avatar.bone('Hips');
    if (!sourceHips || !avatarHips || !sourceHips.parent) return correction;

    sourceScene.updateMatrixWorld(true);
    const sourceParent = sourceHips.parent.getWorldQuaternion(new THREE.Quaternion());
    const avatarParent = avatarHips.parent.getWorldQuaternion(new THREE.Quaternion());
    return correction.copy(avatarParent).invert().multiply(sourceParent);
}

export async function loadClip(url, avatar) {
    const gltf = await loadGLTF(url);
    if (!gltf.animations.length) return null;
    return retargetClip(gltf.animations[0], gltf.scene, avatar);
}
