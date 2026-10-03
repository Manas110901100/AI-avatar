import * as THREE from 'three';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { BokehPass } from 'three/addons/postprocessing/BokehPass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';
import { ShaderPass } from 'three/addons/postprocessing/ShaderPass.js';
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js';

// Camera framings, as offsets from the (smoothed) head position. `time` is how long the move takes.
const SHOTS = {
    // Lenses sit near eye level (the head bone is ~9 cm below the eyes) so eye contact reads
    wide: { from: [0, -0.2, 3.3], at: [0, -0.55, 0], fov: 36, time: 1.1 },
    medium: { from: [0, 0.03, 1.85], at: [0, -0.16, 0], fov: 30, time: 0.9 },
    close: { from: [0, 0.07, 0.95], at: [0, 0.0, 0], fov: 28, time: 0.8 },
    push_in: { from: [0, 0.06, 1.25], at: [0, -0.05, 0], fov: 29, time: 2.6 },
};

// Key-light colour per emotion: warmer for warmth, cooler for weight
const MOODS = {
    neutral: 0xffe6cc, confident: 0xffe2c0, amused: 0xffe0b8, happy: 0xffdcae, warm: 0xffd6a6,
    excited: 0xffdcb0, thoughtful: 0xf2e6dc, curious: 0xfbe6cf, skeptical: 0xeae6e4,
    serious: 0xe4e8f0, sad: 0xd6e0f2, surprised: 0xfff0dc, annoyed: 0xf6dccb,
};

const GradeShader = {
    uniforms: { tDiffuse: { value: null }, time: { value: 0 }, vignette: { value: 0.42 }, grain: { value: 0.035 } },
    vertexShader: `
        varying vec2 vUv;
        void main() { vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`,
    fragmentShader: `
        uniform sampler2D tDiffuse;
        uniform float time;
        uniform float vignette;
        uniform float grain;
        varying vec2 vUv;
        float rand(vec2 co) { return fract(sin(dot(co, vec2(12.9898, 78.233))) * 43758.5453); }
        void main() {
            vec4 color = texture2D(tDiffuse, vUv);
            float edge = smoothstep(0.25, 0.85, length((vUv - 0.5) * vec2(1.0, 0.9)));
            color.rgb *= 1.0 - vignette * edge;
            color.rgb = (color.rgb - 0.5) * 1.04 + 0.5;
            color.rgb += (rand(vUv * 1000.0 + fract(time)) - 0.5) * grain;
            gl_FragColor = color;
        }`,
};

function smoothDamp(current, target, velocity, smoothTime, dt) {
    const omega = 2 / Math.max(smoothTime, 1e-4);
    const x = omega * dt;
    const decay = 1 / (1 + x + 0.48 * x * x + 0.235 * x * x * x);
    const change = current - target;
    const temp = (velocity + omega * change) * dt;
    return { value: target + (change + temp) * decay, velocity: (velocity - omega * temp) * decay };
}

function backdropTexture() {
    const canvas = document.createElement('canvas');
    canvas.width = 512;
    canvas.height = 512;
    const ctx = canvas.getContext('2d');
    const gradient = ctx.createRadialGradient(256, 190, 20, 256, 256, 380);
    gradient.addColorStop(0, '#2a3040');
    gradient.addColorStop(0.55, '#141821');
    gradient.addColorStop(1, '#07080b');
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, 512, 512);
    const texture = new THREE.CanvasTexture(canvas);
    texture.colorSpace = THREE.SRGBColorSpace;
    return texture;
}

export class Stage {
    constructor(canvas, container) {
        this.container = container;
        this.time = 0;

        this.renderer = new THREE.WebGLRenderer({ canvas, antialias: false, powerPreference: 'high-performance' });
        this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
        this.renderer.outputColorSpace = THREE.SRGBColorSpace;
        this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
        this.renderer.toneMappingExposure = 1.05;
        this.renderer.shadowMap.enabled = true;
        this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;

        this.scene = new THREE.Scene();
        this.scene.background = backdropTexture();
        const pmrem = new THREE.PMREMGenerator(this.renderer);
        this.scene.environment = pmrem.fromScene(new RoomEnvironment(this.renderer), 0.04).texture;

        this.camera = new THREE.PerspectiveCamera(36, 1, 0.05, 50);
        this.camera.position.set(0, 1.3, 3.3);

        this.addLights();
        this.addFloor();
        this.addPostProcessing();

        this.headBone = null;
        this.head = new THREE.Vector3(0, 1.64, 0);
        this.shot = SHOTS.wide;
        this.shotTime = SHOTS.wide.time;
        this.look = new THREE.Vector3(0, 1.1, 0);
        this.velocity = { pos: [0, 0, 0], look: [0, 0, 0], fov: 0 };

        new ResizeObserver(() => this.resize()).observe(container);
        this.resize();
    }

    addLights() {
        this.key = new THREE.DirectionalLight(MOODS.neutral, 2.2);
        this.key.position.set(1.5, 2.6, 2.6);
        this.key.castShadow = true;
        this.key.shadow.mapSize.set(1024, 1024);
        this.key.shadow.bias = -0.0004;
        Object.assign(this.key.shadow.camera, { left: -1.2, right: 1.2, top: 2.2, bottom: -0.2, near: 0.5, far: 8 });
        this.keyColor = new THREE.Color(MOODS.neutral);
        this.keyTarget = new THREE.Color(MOODS.neutral);

        const fill = new THREE.DirectionalLight(0xa8c4ff, 0.55);
        fill.position.set(-2.2, 1.6, 1.6);
        const rimCool = new THREE.DirectionalLight(0xbfd4ff, 3.0);
        rimCool.position.set(-1.1, 2.3, -2.6);
        const rimWarm = new THREE.DirectionalLight(0xffd2a8, 1.4);
        rimWarm.position.set(1.3, 2.0, -2.2);
        const ambient = new THREE.HemisphereLight(0x8090b0, 0x101014, 0.25);

        this.scene.add(this.key, fill, rimCool, rimWarm, ambient);
    }

    addFloor() {
        const floor = new THREE.Mesh(new THREE.PlaneGeometry(8, 8), new THREE.ShadowMaterial({ opacity: 0.35 }));
        floor.rotation.x = -Math.PI / 2;
        floor.receiveShadow = true;
        this.scene.add(floor);
    }

    addPostProcessing() {
        const target = new THREE.WebGLRenderTarget(1, 1, { type: THREE.HalfFloatType, samples: 4 });
        this.composer = new EffectComposer(this.renderer, target);
        this.composer.addPass(new RenderPass(this.scene, this.camera));
        this.bokeh = new BokehPass(this.scene, this.camera, { focus: 1.9, aperture: 0.0004, maxblur: 0.006 });
        this.composer.addPass(this.bokeh);
        this.bloom = new UnrealBloomPass(new THREE.Vector2(256, 256), 0.22, 0.5, 0.88);
        this.composer.addPass(this.bloom);
        this.composer.addPass(new OutputPass());
        this.grade = new ShaderPass(GradeShader);
        this.composer.addPass(this.grade);
    }

    add(object) {
        this.scene.add(object);
        object.traverse((node) => {
            if (node.isMesh && node.material) {
                (Array.isArray(node.material) ? node.material : [node.material]).forEach((m) => { m.envMapIntensity = 0.6; });
            }
        });
    }

    follow(headBone) {
        this.headBone = headBone;
        if (headBone) headBone.getWorldPosition(this.head);
    }

    setShot(name, duration) {
        const shot = SHOTS[name];
        if (!shot) return;
        this.shot = shot;
        this.shotTime = name === 'push_in' && duration ? Math.max(shot.time, duration * 0.6) : shot.time;
    }

    setMood(emotion) {
        this.keyTarget.set(MOODS[emotion] || MOODS.neutral);
    }

    resize() {
        const width = Math.max(1, this.container.clientWidth);
        const height = Math.max(1, this.container.clientHeight);
        this.renderer.setSize(width, height, false);
        this.composer.setPixelRatio(this.renderer.getPixelRatio());
        this.composer.setSize(width, height);
        this.camera.aspect = width / height;
        this.camera.updateProjectionMatrix();
    }

    render(dt) {
        this.time += dt;
        if (this.headBone) {
            const head = this.headBone.getWorldPosition(new THREE.Vector3());
            this.head.lerp(head, 1 - Math.exp(-dt / 0.6)); // the operator follows, never jitters
        }

        // Handheld: tiny, slow, never the same
        const t = this.time;
        const hand = [
            (Math.sin(t * 0.37) * 0.6 + Math.sin(t * 0.91 + 1.3) * 0.4) * 0.004,
            (Math.sin(t * 0.43 + 2.1) * 0.6 + Math.sin(t * 1.07) * 0.4) * 0.003,
            0,
        ];
        const shot = this.shot;
        const narrow = this.camera.aspect < 0.8 ? 0.8 / this.camera.aspect : 1;

        const pos = this.camera.position;
        ['x', 'y', 'z'].forEach((axis, i) => {
            const distanceScale = i === 2 ? narrow : 1;
            const p = smoothDamp(pos[axis], this.head.getComponent(i) + shot.from[i] * distanceScale + hand[i], this.velocity.pos[i], this.shotTime / 2, dt);
            pos[axis] = p.value;
            this.velocity.pos[i] = p.velocity;
            const l = smoothDamp(this.look.getComponent(i), this.head.getComponent(i) + shot.at[i], this.velocity.look[i], this.shotTime / 2, dt);
            this.look.setComponent(i, l.value);
            this.velocity.look[i] = l.velocity;
        });
        const f = smoothDamp(this.camera.fov, shot.fov, this.velocity.fov, this.shotTime / 2, dt);
        this.camera.fov = f.value;
        this.velocity.fov = f.velocity;
        this.camera.updateProjectionMatrix();
        this.camera.lookAt(this.look);

        this.keyColor.lerp(this.keyTarget, 1 - Math.exp(-dt / 1.2));
        this.key.color.copy(this.keyColor);

        this.bokeh.uniforms.focus.value = this.camera.position.distanceTo(this.head);
        this.grade.uniforms.time.value = t;
        this.composer.render(dt);
    }
}
