"""Upgrade the Ready Player Me avatar's rig for detailed acting, without Blender.

usage: python tools/rig_upgrade.py [--src static/avatar.glb] [--out static/avatars/rpm-detailed/avatar.glb]

Keeps every existing bone and morph, and adds:
  1. ARKit face shapes: split left/right from existing morphs where the motion exists
     (blink, smile, press, pucker, funnel, jaw), sculpted from measured face regions where it
     doesn't (brows, squint, wide, lid-follow, cheeks, nose, frown)
  2. Spherical eyes: each eye cap is closed into a ball and its bone moved to the ball's
     centre, so the eyes can turn ±25° without the rim showing
  3. Forearm twist bones that share the wrist's roll with the forearm skin

Deterministic: rerun after changing any constant below. All distances are metres in the
avatar's bind pose (Y up, facing +Z, the avatar's left = +X).
"""

import argparse
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from glb import ARRAY_BUFFER, ELEMENT_ARRAY_BUFFER, GLB  # noqa: E402
from avatar_audit import audit, fit_sphere  # noqa: E402

# ---- sculpt sizes (tune by eye with tools/shoot.py) ------------------------------------------
MIDLINE_BLEND = 0.012  # width of the left/right crossfade across the face's centre
BROW_UP = 0.0072  # browInnerUp / browOuterUp lift
BROW_DOWN = 0.0048  # browDown drop
BROW_DOWN_INWARD = 0.002  # browDown pull toward the nose
LOWER_LID_RAISE = 0.0026  # eyeSquint lower-lid lift
UPPER_LID_SQUINT = 0.2  # share of the blink's upper-lid motion in a squint
EYE_WIDE = 0.5  # share of the blink's upper-lid motion reversed for eyeWide
LID_FOLLOW_DOWN = 0.3  # upper lid follows a downward look
LID_FOLLOW_UP = 0.22  # upper lid lifts with an upward look
NOSE_SNEER = 0.0036
FROWN_DROP = 0.8  # frown = smile's corner motion, vertical part flipped and scaled
CHEEK_FROM_SMILE_Y = 1.675  # above this height, smile motion counts as cheek raise
TWIST_SHARE_START, TWIST_SHARE_END = 0.15, 0.85  # where along the forearm skin starts and finishes following the twist bone


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


def gaussian(x, centre, sigma):
    return np.exp(-0.5 * ((x - centre) / sigma) ** 2)


class Rig:
    def __init__(self, path):
        self.glb = GLB.load(path)
        g = self.glb.gltf
        self.mesh = g["meshes"][0]
        self.prim = self.mesh["primitives"][0]
        a = self.prim["attributes"]
        self.attrs = {name: self.glb.read(index) for name, index in a.items()}
        self.indices = self.glb.read(self.prim["indices"]).astype(np.int64)
        self.target_names = list(self.mesh["extras"]["targetNames"])
        self.targets = {n: self.glb.read(t["POSITION"]).astype(np.float32) for n, t in zip(self.target_names, self.prim["targets"])}
        self.joint_nodes = g["skins"][0]["joints"]
        self.joint_names = [g["nodes"][j]["name"] for j in self.joint_nodes]
        self.ibm = self.glb.read(g["skins"][0]["inverseBindMatrices"]).reshape(-1, 4, 4).transpose(0, 2, 1).astype(np.float64)
        self.added = []

    @property
    def P(self):
        return self.attrs["POSITION"].astype(np.float64)

    def joint_weight(self, name):
        j = self.joint_names.index(name)
        return np.where(self.attrs["JOINTS_0"] == j, self.attrs["WEIGHTS_0"], 0).sum(axis=1)

    def bind_world(self, name):
        return np.linalg.inv(self.ibm[self.joint_names.index(name)])

    def add_target(self, name, delta):
        if name in self.targets:
            raise ValueError(f"morph {name} already exists")
        self.targets[name] = delta.astype(np.float32)
        self.target_names.append(name)
        self.added.append(name)

    # ---- landmarks -------------------------------------------------------------------------

    def measure(self):
        P = self.P
        self.eye = {}
        for side in ("Left", "Right"):
            cap = self.joint_weight(f"{side}Eye") > 0.99
            centre, radius = fit_sphere(P[cap])
            self.eye[side] = {"cap": cap, "centre": centre, "radius": radius}
        self.eye_y = (self.eye["Left"]["centre"][1] + self.eye["Right"]["centre"][1]) / 2
        self.eye_x = abs(self.eye["Left"]["centre"][0])

        smile = np.linalg.norm(self.targets["mouthSmile"], axis=1)
        self.mouth_corner_y = P[np.argmax(smile), 1]
        jaw = np.linalg.norm(self.targets["viseme_aa"], axis=1)
        self.mouth_centre = (P * (jaw / jaw.sum())[:, None]).sum(axis=0)

        # The head's skin is the welded component that holds the eyelids (hair is separate)
        self.skin = self.component_of(np.argmax(np.linalg.norm(self.targets["eyesClosed"], axis=1)))
        self.front = smoothstep(0.03, 0.07, P[:, 2])  # face front, not the sides or back of the head
        self.left = smoothstep(-MIDLINE_BLEND, MIDLINE_BLEND, P[:, 0])
        print(f"eyes at y={self.eye_y:.4f} x=±{self.eye_x:.4f}  mouth corners y={self.mouth_corner_y:.4f}  "
              f"mouth centre {self.mouth_centre.round(4)}  skin verts {int(self.skin.sum())}")

    def component_of(self, vertex):
        key = np.round(self.P / 1e-5).astype(np.int64)
        _, weld = np.unique(key, axis=0, return_inverse=True)
        weld = weld.ravel()
        parent = np.arange(weld.max() + 1)

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        for a, b, c in weld[self.indices.reshape(-1, 3)]:
            ra = find(a)
            parent[find(b)] = ra
            parent[find(c)] = ra
        roots = np.array([find(x) for x in weld])
        return roots == roots[vertex]

    def split(self, name, delta):
        """Add `nameLeft` / `nameRight` from a symmetric delta."""
        self.add_target(f"{name}Left", delta * self.left[:, None])
        self.add_target(f"{name}Right", delta * (1 - self.left)[:, None])

    # ---- 1. face shapes --------------------------------------------------------------------

    def face_shapes(self):
        P, T = self.P, self.targets
        y = P[:, 1]
        skin = (self.skin & ~self.eye["Left"]["cap"] & ~self.eye["Right"]["cap"]).astype(np.float64)
        face = skin * self.front

        blink = T["eyesClosed"].astype(np.float64)
        upper_lid = blink * smoothstep(self.eye_y - 0.002, self.eye_y + 0.002, y)[:, None]

        # Straight from existing morphs
        self.split("eyeBlink", blink)
        self.split("mouthSmile", T["mouthSmile"])
        self.split("mouthPress", T["viseme_PP"] * 0.8)
        self.add_target("jawOpen", T["mouthOpen"])
        self.add_target("mouthPucker", T["viseme_U"])
        self.add_target("mouthFunnel", T["viseme_O"])

        # Lids: squint lifts the lower lid; wide and the look-follow shapes move the upper lid
        dx = np.abs(np.abs(P[:, 0]) - self.eye_x)
        below_eye = self.eye_y - y
        lower_lid = face * gaussian(dx, 0, 0.012) * smoothstep(0.0, 0.004, below_eye) * (1 - smoothstep(0.008, 0.016, below_eye))
        squint = UPPER_LID_SQUINT * upper_lid
        squint[:, 1] += LOWER_LID_RAISE * lower_lid
        self.split("eyeSquint", squint)
        self.split("eyeWide", -EYE_WIDE * upper_lid)
        self.split("eyeLookDown", LID_FOLLOW_DOWN * upper_lid)
        self.split("eyeLookUp", -LID_FOLLOW_UP * upper_lid)

        # Brows: a band above each eye, faded out below the brow and up the forehead
        above = y - self.eye_y
        band = face * smoothstep(0.006, 0.016, above) * (1 - smoothstep(0.03, 0.05, above))
        inner = band * gaussian(np.abs(P[:, 0]), 0.012, 0.012)
        lift = np.zeros_like(P)
        lift[:, 1] = BROW_UP * inner
        lift[:, 2] = 0.0005 * inner
        self.add_target("browInnerUp", lift)

        outer = band * gaussian(np.abs(P[:, 0]), self.eye_x + 0.014, 0.013)
        lift = np.zeros_like(P)
        lift[:, 1] = BROW_UP * outer
        self.split("browOuterUp", lift)

        whole = band * gaussian(np.abs(P[:, 0]), self.eye_x - 0.004, 0.022)
        down = np.zeros_like(P)
        down[:, 1] = -BROW_DOWN * whole
        down[:, 0] = -np.sign(P[:, 0]) * BROW_DOWN_INWARD * whole
        down[:, 2] = 0.0008 * whole
        self.split("browDown", down)

        # Cheeks: the part of the smile above the mouth corners
        cheek = T["mouthSmile"] * (face * smoothstep(CHEEK_FROM_SMILE_Y - 0.004, CHEEK_FROM_SMILE_Y + 0.004, y))[:, None]
        self.split("cheekSquint", cheek)

        # Frown: the smile's mouth-corner motion with the vertical part flipped
        mouth_band = 1 - smoothstep(self.mouth_corner_y + 0.012, self.mouth_corner_y + 0.024, y)
        corners = T["mouthSmile"] * (skin * mouth_band)[:, None]
        frown = np.stack([corners[:, 0] * 0.15, -corners[:, 1] * FROWN_DROP, corners[:, 2] * 0.2], axis=1)
        self.split("mouthFrown", frown)

        # Nose sneer: lift beside the nostrils
        nose_y = self.mouth_centre[1] + 0.03
        wing = face * gaussian(np.abs(P[:, 0]), 0.013, 0.007) * gaussian(y, nose_y, 0.008)
        sneer = np.zeros_like(P)
        sneer[:, 1] = NOSE_SNEER * wing
        sneer[:, 2] = -0.0006 * wing
        self.split("noseSneer", sneer)

    # ---- 2. spherical eyes ---------------------------------------------------------------

    def close_eyes(self):
        for side in ("Left", "Right"):
            eye = self.eye[side]
            centre = eye["centre"]
            forward = self.bind_world(f"{side}Eye")[:3, 2]
            forward /= np.linalg.norm(forward)
            P = self.P
            in_front = eye["cap"] & ((P - centre) @ forward > 0)

            tris = self.indices.reshape(-1, 3)
            keep = in_front[tris].all(axis=1)
            source = np.unique(tris[keep])
            new_index = {int(v): len(P) + i for i, v in enumerate(source)}

            def mirror(vectors, is_point):
                v = vectors.astype(np.float64)
                offset = (v - centre) if is_point else v
                reflected = offset - 2 * (offset @ forward)[:, None] * forward
                return (reflected + centre) if is_point else reflected

            a = self.attrs
            additions = {
                "POSITION": mirror(a["POSITION"][source], True).astype(a["POSITION"].dtype),
                "NORMAL": mirror(a["NORMAL"][source], False).astype(a["NORMAL"].dtype),
            }
            for name in a:
                if name not in additions:
                    additions[name] = a[name][source]
            for name, values in additions.items():
                a[name] = np.concatenate([a[name], values])
            for name, delta in self.targets.items():
                self.targets[name] = np.concatenate([delta, mirror(delta[source], False).astype(np.float32)])

            mirrored = np.array([[new_index[int(v)] for v in tri] for tri in tris[keep]])
            self.indices = np.concatenate([self.indices, mirrored[:, ::-1].ravel()])
            eye["cap"] = np.concatenate([eye["cap"], np.ones(len(source), dtype=bool)])
            other = self.eye["Right" if side == "Left" else "Left"]
            other["cap"] = np.concatenate([other["cap"], np.zeros(len(source), dtype=bool)])

            self.move_joint(f"{side}Eye", centre)
            print(f"{side} eye: +{len(source)} vertices, pivot moved to the ball's centre (r={eye['radius'] * 100:.2f} cm)")

    def move_joint(self, name, world_position):
        """Move a leaf joint to `world_position` in the bind pose, keeping its orientation."""
        g = self.glb.gltf
        node_index = self.joint_nodes[self.joint_names.index(name)]
        parent_world = self.glb.world_matrix(self.glb.parents()[node_index])
        local = np.linalg.inv(parent_world) @ np.append(world_position, 1.0)
        g["nodes"][node_index]["translation"] = [float(v) for v in local[:3]]
        world = self.bind_world(name)
        world[:3, 3] = world_position
        self.ibm[self.joint_names.index(name)] = np.linalg.inv(world)

    # ---- 3. forearm twist bones --------------------------------------------------------------

    def twist_bones(self):
        g = self.glb.gltf
        for side in ("Left", "Right"):
            fore, hand = f"{side}ForeArm", f"{side}Hand"
            fore_node = self.joint_nodes[self.joint_names.index(fore)]
            hand_node = self.joint_nodes[self.joint_names.index(hand)]
            half = [0.5 * v for v in g["nodes"][hand_node].get("translation", [0, 0, 0])]

            name = f"{side}ForeArmTwist"
            g["nodes"].append({"name": name, "translation": half})
            twist_node = len(g["nodes"]) - 1
            g["nodes"][fore_node].setdefault("children", []).append(twist_node)
            g["skins"][0]["joints"].append(twist_node)
            self.joint_nodes = g["skins"][0]["joints"]
            self.joint_names.append(name)
            offset = np.eye(4)
            offset[:3, 3] = half
            self.ibm = np.concatenate([self.ibm, np.linalg.inv(self.bind_world(fore) @ offset)[None]])

            elbow = self.bind_world(fore)[:3, 3]
            wrist = self.bind_world(hand)[:3, 3]
            axis = wrist - elbow
            along = ((self.P - elbow) @ axis) / (axis @ axis)
            share = smoothstep(TWIST_SHARE_START, TWIST_SHARE_END, along)

            joints, weights = self.attrs["JOINTS_0"], self.attrs["WEIGHTS_0"].astype(np.float64)
            fore_j, twist_j = self.joint_names.index(fore), len(self.joint_names) - 1
            moved = 0
            for v in np.where((joints == fore_j).any(axis=1) & (share > 0.01))[0]:
                slot = int(np.where(joints[v] == fore_j)[0][0])
                give = weights[v, slot] * share[v]
                weights[v, slot] -= give
                free = int(np.argmin(weights[v]))
                if free == slot or weights[v, free] > give:
                    weights[v, slot] += give  # no room for a fifth influence; leave this vertex as it was
                    continue
                joints[v, free] = twist_j
                weights[v, free] = give
                weights[v] /= weights[v].sum()
                moved += 1
            self.attrs["WEIGHTS_0"] = weights.astype(self.attrs["WEIGHTS_0"].dtype)
            print(f"{name}: {moved} forearm vertices now share the twist")

    # ---- write -------------------------------------------------------------------------

    def save(self, out):
        g, glb = self.glb.gltf, self.glb
        a = self.attrs
        targets = {"POSITION": ARRAY_BUFFER, "NORMAL": ARRAY_BUFFER, "TEXCOORD_0": ARRAY_BUFFER,
                   "WEIGHTS_0": ARRAY_BUFFER, "JOINTS_0": ARRAY_BUFFER}
        for name, values in a.items():
            self.prim["attributes"][name] = glb.add_accessor(values, target=targets.get(name), minmax=(name == "POSITION"))
        index_dtype = np.uint16 if len(a["POSITION"]) < 65535 else np.uint32
        self.prim["indices"] = glb.add_accessor(self.indices.astype(index_dtype), "SCALAR", target=ELEMENT_ARRAY_BUFFER)
        self.prim["targets"] = [{"POSITION": glb.add_sparse_accessor(self.targets[n], minmax=True)} for n in self.target_names]
        self.mesh["extras"]["targetNames"] = self.target_names
        g["skins"][0]["inverseBindMatrices"] = glb.add_accessor(
            self.ibm.transpose(0, 2, 1).reshape(-1, 16).astype(np.float32), "MAT4")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        size = glb.save(out)
        print(f"wrote {out} ({size / 1e6:.2f} MB): +{len(self.added)} morphs {self.added}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--src", default="static/avatar.glb")
    parser.add_argument("--out", default="static/avatars/rpm-detailed/avatar.glb")
    args = parser.parse_args()

    rig = Rig(args.src)
    rig.measure()
    rig.face_shapes()
    rig.close_eyes()
    rig.twist_bones()
    rig.save(args.out)
    print()
    sys.exit(0 if audit(args.out, baseline=args.src) else 1)


if __name__ == "__main__":
    main()
