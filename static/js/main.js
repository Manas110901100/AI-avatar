import * as THREE from 'three';
import { loadAvatar, loadAvatarConfig } from './avatar.js';
import { Animator } from './animator.js';
import { Stage } from './stage.js';
import { GestureSynth } from './synth.js';
import { Procedural } from './procedural.js';
import { Face } from './face.js';
import { Director, PERSONA } from './director.js';

// The LLM that writes the performance script; it must support tool/function calling
const DIRECTOR_MODEL = 'gpt-4o-mini';
// Which rig to load from static/avatars/<id>/; override with ?avatar=rpm-default
const DEFAULT_AVATAR = 'rpm-detailed';

let apiKeyId = null;
let director = null;

// VALIDATION LOGIC
window.validateKey = async (event) => {
    if (event) event.preventDefault();
    const input = document.getElementById('api-key-input');
    const btn = document.querySelector('#access-screen .btn');
    const errorMsg = document.getElementById('error-msg');
    const key = input.value.trim();

    if (!key) return;

    btn.disabled = true;
    btn.innerText = "Verifying...";
    errorMsg.innerText = "";

    try {
        const response = await fetch('/keys/validate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ api_key: key })
        });

        const contentType = response.headers.get("content-type");
        let data;
        if (contentType && contentType.indexOf("application/json") !== -1) {
            data = await response.json();
        } else {
            const text = await response.text();
            console.error("Non-JSON response:", text);
            throw new Error(`Server returned status ${response.status}. See console for details.`);
        }

        if (!response.ok) {
            throw new Error(data.detail || 'Validation failed');
        }

        apiKeyId = data.id;

        // Success transition
        document.getElementById('access-screen').classList.add('hidden');
        document.getElementById('user-input').disabled = false;
        document.getElementById('send-btn').disabled = false;
        director?.unlockAudio();

    } catch (err) {
        console.error("Validation error:", err);
        errorMsg.innerText = err.message || "Connection failed";
        btn.disabled = false;
        btn.innerText = "Connect";
    }
};

// CHAT LOGIC
window.handleEnter = (e) => {
    if (e.key === 'Enter') sendMessage();
};

window.sendMessage = async () => {
    const input = document.getElementById('user-input');
    const text = input.value.trim();
    if (!text || !apiKeyId) return;

    // UI Updates
    addMessage(text, 'user');
    input.value = '';
    input.disabled = true;
    director?.beginThinking();

    try {
        const response = await fetch('/chat/speak', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                input: text,
                api_key_id: apiKeyId,
                model: DIRECTOR_MODEL
            })
        });

        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.detail || 'Failed to get response');

        const audioBlob = base64ToBlob(data.audio, data.audio_mime);
        addMessage(data.text || "...", 'ai');
        if (director) director.perform(data, audioBlob);
        else new Audio(URL.createObjectURL(audioBlob)).play();

    } catch (err) {
        console.error(err);
        director?.endThinking();
        addMessage(`Error communicating with AI: ${err.message}`, 'ai');
    } finally {
        input.disabled = false;
        input.focus();
    }
};

function base64ToBlob(base64, mime) {
    const bytes = Uint8Array.from(atob(base64), (c) => c.charCodeAt(0));
    return new Blob([bytes], { type: mime || 'audio/mpeg' });
}

function addMessage(text, type) {
    const history = document.getElementById('chat-history');
    const div = document.createElement('div');
    div.className = `message ${type}`;
    div.innerText = text;
    history.appendChild(div);
    history.scrollTop = history.scrollHeight;
}

// THE ACTOR
async function initActor() {
    const section = document.querySelector('.avatar-section');
    const stage = new Stage(document.getElementById('avatar-canvas'), section);

    const avatarId = new URLSearchParams(window.location.search).get('avatar') || DEFAULT_AVATAR;
    const avatar = await loadAvatar(await loadAvatarConfig(avatarId));
    console.log(`Avatar "${avatarId}"`, avatar.capabilities);
    stage.add(avatar.root);
    stage.follow(avatar.bone('Head'));

    // Rigs measure the rest pose, so they are built before any animation plays
    const synth = new GestureSynth(avatar, stage, PERSONA);
    const procedural = new Procedural(avatar, PERSONA);
    const face = new Face(avatar, PERSONA);
    const animator = new Animator(avatar, PERSONA);

    const catalog = await fetch('/gestures').then((r) => r.json());
    await animator.init(catalog.clips.map((clip) => clip.name));

    director = new Director({ animator, synth, procedural, face, stage });
    stage.setShot('medium');

    const clock = new THREE.Clock();
    function frame() {
        requestAnimationFrame(frame);
        const dt = Math.min(clock.getDelta(), 0.05);
        director.update(dt);
        animator.update(dt);
        avatar.root.updateMatrixWorld(true);
        procedural.updateBody(dt, synth);
        synth.update(dt);
        procedural.updateHead(dt, stage.camera.position, synth);
        face.setEyeLook(procedural.eyeAngles.pitch, procedural.eyeLimits);
        face.update(dt, director.speechTime);
        stage.render(dt);
    }
    frame();

    document.getElementById('user-input').addEventListener('input', () => director.notifyTyping());

    // Console helpers for trying the actor by hand
    window.director = director;
    window.perform = (name, params = {}) => {
        if (catalog.clips.some((clip) => clip.name === name)) return animator.playClip(name, params.duration);
        const info = catalog.procedural.find((g) => g.name === name);
        return synth.perform(name, { ...info, ...params });
    };
    window.setEmotion = (name, intensity = 0.7) => director.setEmotion(name, intensity);
    window.setShot = (name) => stage.setShot(name);
    window.setGaze = (target) => procedural.setGaze(target);
    window.setMorph = (name, weight = 1) => { face.override[name] = weight; };
    window.clearMorphs = () => { face.override = {}; };
    window.avatar = avatar;
}

initActor().catch((err) => console.error('The avatar failed to load:', err));
