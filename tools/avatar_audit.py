"""Audit an avatar GLB for what the actor engine can drive.

usage: python tools/avatar_audit.py <avatar.glb> [--baseline <original.glb>] [--min-arkit 25]

Reports bones, morph coverage (ARKit 52 / Oculus visemes / legacy RPM), eye geometry, twist
bones and sizes, then PASS/FAIL against the gate. Exit code 1 on FAIL.
"""

import argparse
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from glb import GLB  # noqa: E402

ARKIT_52 = [
    "eyeBlinkLeft", "eyeLookDownLeft", "eyeLookInLeft", "eyeLookOutLeft", "eyeLookUpLeft", "eyeSquintLeft", "eyeWideLeft",
    "eyeBlinkRight", "eyeLookDownRight", "eyeLookInRight", "eyeLookOutRight", "eyeLookUpRight", "eyeSquintRight", "eyeWideRight",
    "jawForward", "jawLeft", "jawRight", "jawOpen", "mouthClose", "mouthFunnel", "mouthPucker", "mouthLeft", "mouthRight",
    "mouthSmileLeft", "mouthSmileRight", "mouthFrownLeft", "mouthFrownRight", "mouthDimpleLeft", "mouthDimpleRight",
    "mouthStretchLeft", "mouthStretchRight", "mouthRollLower", "mouthRollUpper", "mouthShrugLower", "mouthShrugUpper",
    "mouthPressLeft", "mouthPressRight", "mouthLowerDownLeft", "mouthLowerDownRight", "mouthUpperUpLeft", "mouthUpperUpRight",
    "browDownLeft", "browDownRight", "browInnerUp", "browOuterUpLeft", "browOuterUpRight", "cheekPuff",
    "cheekSquintLeft", "cheekSquintRight", "noseSneerLeft", "noseSneerRight", "tongueOut",
]
OCULUS_VISEMES = ["viseme_sil", "viseme_PP", "viseme_FF", "viseme_TH", "viseme_DD", "viseme_kk", "viseme_CH", "viseme_SS",
                  "viseme_nn", "viseme_RR", "viseme_aa", "viseme_E", "viseme_I", "viseme_O", "viseme_U"]
LEGACY_RPM = ["mouthOpen", "mouthSmile", "eyesClosed", "eyesLookUp", "eyesLookDown"]
MAX_FILE_MB = 15
MAX_PIVOT_OFFSET_MM = 2.0


def fit_sphere(points: np.ndarray):
    """Least-squares sphere through `points`: returns (centre, radius)."""
    a = np.hstack([2 * points, np.ones((len(points), 1))])
    b = (points ** 2).sum(axis=1)
    solution, *_ = np.linalg.lstsq(a, b, rcond=None)
    centre = solution[:3]
    radius = float(np.sqrt(solution[3] + centre @ centre))
    return centre, radius


def morph_names(glb: GLB) -> list:
    mesh = glb.gltf["meshes"][0]
    return list((mesh.get("extras") or {}).get("targetNames", []))


def skin_vertices(glb: GLB):
    """Bind-pose positions, joints and weights of the first skinned primitive."""
    primitive = glb.gltf["meshes"][0]["primitives"][0]
    attributes = primitive["attributes"]
    return (glb.read(attributes["POSITION"]).astype(np.float64),
            glb.read(attributes["JOINTS_0"]).astype(np.int64),
            glb.read(attributes["WEIGHTS_0"]).astype(np.float64))


def eye_report(glb: GLB, joint_names: list, side: str) -> dict:
    name = f"{side}Eye"
    if name not in joint_names:
        return {"present": False}
    joint = joint_names.index(name)
    positions, joints, weights = skin_vertices(glb)
    weight = np.where(joints == joint, weights, 0).sum(axis=1)
    points = positions[weight > 0.99]
    if len(points) < 8:
        return {"present": True, "vertices": int(len(points))}
    centre, radius = fit_sphere(points)
    pivot = glb.world_matrix(glb.node_index(name))[:3, 3]
    # Fraction of the sphere's depth the geometry spans: ~0.5 for a half cap, ~1.0 for a full ball
    axis_extent = (points[:, 2].max() - points[:, 2].min()) / (2 * radius)
    return {
        "present": True,
        "vertices": int(len(points)),
        "radius_cm": round(radius * 100, 2),
        "pivot_offset_mm": round(float(np.linalg.norm(pivot - centre)) * 1000, 2),
        "depth_coverage": round(float(axis_extent), 2),
        "spherical": bool(axis_extent > 0.85),
    }


def audit(path: str, baseline: str = None, min_arkit: int = 25) -> bool:
    glb = GLB.load(path)
    gltf = glb.gltf
    joint_names = [gltf["nodes"][j]["name"] for j in gltf["skins"][0]["joints"]]
    morphs = morph_names(glb)
    arkit = [m for m in ARKIT_52 if m in morphs]
    visemes = [m for m in OCULUS_VISEMES if m in morphs]
    legacy = [m for m in LEGACY_RPM if m in morphs]
    twist = [j for j in joint_names if "Twist" in j]
    size_mb = os.path.getsize(path) / 1e6
    images = [(img.get("mimeType"), len(glb.views[img["bufferView"]]) // 1024) for img in gltf.get("images", []) if "bufferView" in img]
    vertex_count = gltf["accessors"][gltf["meshes"][0]["primitives"][0]["attributes"]["POSITION"]]["count"]

    print(f"== {path}")
    print(f"size: {size_mb:.2f} MB  vertices: {vertex_count}  joints: {len(joint_names)}  morphs: {len(morphs)}")
    print(f"images (KB): {images}")
    print(f"ARKit: {len(arkit)}/52  {arkit}")
    print(f"ARKit missing: {[m for m in ARKIT_52 if m not in morphs]}")
    print(f"Oculus visemes: {len(visemes)}/15   legacy RPM: {legacy}")
    print(f"twist bones: {twist}")
    eyes = {side: eye_report(glb, joint_names, side) for side in ("Left", "Right")}
    for side, report in eyes.items():
        print(f"{side} eye: {report}")

    checks = {
        f"file <= {MAX_FILE_MB} MB": size_mb <= MAX_FILE_MB,
        f"ARKit >= {min_arkit}": len(arkit) >= min_arkit,
        "eyes spherical": all(e.get("spherical") for e in eyes.values()),
        f"eye pivots within {MAX_PIVOT_OFFSET_MM} mm": all(e.get("pivot_offset_mm", 99) <= MAX_PIVOT_OFFSET_MM for e in eyes.values()),
    }
    if baseline:
        base = GLB.load(baseline)
        base_joints = [base.gltf["nodes"][j]["name"] for j in base.gltf["skins"][0]["joints"]]
        checks["bones superset of baseline"] = set(base_joints) <= set(joint_names)
        checks["morphs superset of baseline"] = set(morph_names(base)) <= set(morphs)

    print("gate:")
    for name, ok in checks.items():
        print(f"  [{'x' if ok else ' '}] {name}")
    passed = all(checks.values())
    print("PASS" if passed else "FAIL")
    return passed


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("glb")
    parser.add_argument("--baseline")
    parser.add_argument("--min-arkit", type=int, default=25)
    args = parser.parse_args()
    sys.exit(0 if audit(args.glb, args.baseline, args.min_arkit) else 1)
