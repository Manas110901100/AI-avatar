"""Minimal GLB (binary glTF 2.0) reader/writer on numpy, for rig tooling.

Accessors are read into arrays; edits are written as new tightly packed buffer views, and
views nothing references any more are dropped on save. Images and extensions pass through.
"""

import json
import struct

import numpy as np

COMPONENT_DTYPES = {5120: np.int8, 5121: np.uint8, 5122: np.int16, 5123: np.uint16, 5125: np.uint32, 5126: np.float32}
DTYPE_COMPONENTS = {np.dtype(dtype): code for code, dtype in COMPONENT_DTYPES.items()}
TYPE_WIDTHS = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT2": 4, "MAT3": 9, "MAT4": 16}
WIDTH_TYPES = {1: "SCALAR", 2: "VEC2", 3: "VEC3", 4: "VEC4", 16: "MAT4"}
ARRAY_BUFFER = 34962
ELEMENT_ARRAY_BUFFER = 34963

GLB_MAGIC = 0x46546C67
CHUNK_JSON = 0x4E4F534A
CHUNK_BIN = 0x004E4942


class GLB:
    def __init__(self, gltf: dict, binary: bytes):
        self.gltf = gltf
        self.views = []
        for view in gltf.get("bufferViews", []):
            start = view.get("byteOffset", 0)
            self.views.append(binary[start:start + view["byteLength"]])

    @classmethod
    def load(cls, path: str) -> "GLB":
        with open(path, "rb") as f:
            data = f.read()
        magic, version, _ = struct.unpack_from("<III", data, 0)
        if magic != GLB_MAGIC or version != 2:
            raise ValueError(f"{path} is not a glTF 2.0 binary")
        offset, gltf, binary = 12, None, b""
        while offset < len(data):
            length, kind = struct.unpack_from("<II", data, offset)
            chunk = data[offset + 8:offset + 8 + length]
            if kind == CHUNK_JSON:
                gltf = json.loads(chunk)
            elif kind == CHUNK_BIN:
                binary = chunk
            offset += 8 + length
        return cls(gltf, binary)

    # ---- reading -------------------------------------------------------------------------

    def read(self, index: int) -> np.ndarray:
        """Accessor `index` as a (count, width) array in its stored dtype (SCALAR → (count,))."""
        accessor = self.gltf["accessors"][index]
        dtype = np.dtype(COMPONENT_DTYPES[accessor["componentType"]])
        width = TYPE_WIDTHS[accessor["type"]]
        count = accessor["count"]

        if "bufferView" in accessor:
            view = self.gltf["bufferViews"][accessor["bufferView"]]
            raw = self.views[accessor["bufferView"]]
            start = accessor.get("byteOffset", 0)
            element = dtype.itemsize * width
            stride = view.get("byteStride") or element
            if stride == element:
                array = np.frombuffer(raw, dtype=dtype, count=count * width, offset=start).reshape(count, width).copy()
            else:
                rows = np.frombuffer(raw, dtype=np.uint8, count=stride * (count - 1) + element, offset=start)
                rows = np.lib.stride_tricks.as_strided(rows, shape=(count, element), strides=(stride, 1))
                array = np.frombuffer(np.ascontiguousarray(rows).tobytes(), dtype=dtype).reshape(count, width).copy()
        else:
            array = np.zeros((count, width), dtype=dtype)

        sparse = accessor.get("sparse")
        if sparse:
            idx_info, val_info = sparse["indices"], sparse["values"]
            idx_dtype = COMPONENT_DTYPES[idx_info["componentType"]]
            indices = np.frombuffer(self.views[idx_info["bufferView"]], dtype=idx_dtype,
                                    count=sparse["count"], offset=idx_info.get("byteOffset", 0))
            values = np.frombuffer(self.views[val_info["bufferView"]], dtype=dtype,
                                   count=sparse["count"] * width, offset=val_info.get("byteOffset", 0))
            array[indices.astype(np.int64)] = values.reshape(-1, width)

        return array[:, 0] if width == 1 else array

    # ---- writing -------------------------------------------------------------------------

    def _add_view(self, data: bytes, target=None) -> int:
        view = {"buffer": 0, "byteLength": len(data)}
        if target:
            view["target"] = target
        self.gltf["bufferViews"].append(view)
        self.views.append(data)
        return len(self.gltf["bufferViews"]) - 1

    def add_accessor(self, array: np.ndarray, gltf_type: str = None, target=None, normalized=False, minmax=False) -> int:
        """Store `array` as a new accessor and return its index."""
        array = np.ascontiguousarray(array)
        if array.ndim == 1:
            array = array.reshape(-1, 1)
        width = array.shape[1]
        gltf_type = gltf_type or WIDTH_TYPES[width]
        accessor = {
            "bufferView": self._add_view(array.astype(array.dtype.newbyteorder("<")).tobytes(), target),
            "byteOffset": 0,
            "componentType": DTYPE_COMPONENTS[array.dtype],
            "count": int(array.shape[0]),
            "type": gltf_type,
        }
        if normalized:
            accessor["normalized"] = True
        if minmax:
            accessor["min"] = [float(v) for v in array.min(axis=0)]
            accessor["max"] = [float(v) for v in array.max(axis=0)]
        self.gltf["accessors"].append(accessor)
        return len(self.gltf["accessors"]) - 1

    def add_sparse_accessor(self, array: np.ndarray, gltf_type: str = None, minmax=False) -> int:
        """Store a mostly-zero array (e.g. a morph target) as a sparse accessor with no base view."""
        array = np.ascontiguousarray(array)
        if array.ndim == 1:
            array = array.reshape(-1, 1)
        nonzero = np.where(np.any(array != 0, axis=1))[0]
        if len(nonzero) == 0:
            nonzero = np.array([0])  # glTF requires at least one sparse entry
        index_dtype = np.uint16 if array.shape[0] <= 65535 else np.uint32
        accessor = {
            "componentType": DTYPE_COMPONENTS[array.dtype],
            "count": int(array.shape[0]),
            "type": gltf_type or WIDTH_TYPES[array.shape[1]],
            "sparse": {
                "count": int(len(nonzero)),
                "indices": {"bufferView": self._add_view(nonzero.astype(index_dtype).tobytes()), "componentType": DTYPE_COMPONENTS[np.dtype(index_dtype)]},
                "values": {"bufferView": self._add_view(array[nonzero].tobytes())},
            },
        }
        if minmax:
            accessor["min"] = [float(v) for v in array.min(axis=0)]
            accessor["max"] = [float(v) for v in array.max(axis=0)]
        self.gltf["accessors"].append(accessor)
        return len(self.gltf["accessors"]) - 1

    def save(self, path: str) -> int:
        """Write the GLB, dropping unreferenced views. Returns the file size in bytes."""
        gltf = self.gltf
        used = set()
        for accessor in gltf.get("accessors", []):
            if "bufferView" in accessor:
                used.add(accessor["bufferView"])
            sparse = accessor.get("sparse")
            if sparse:
                used.add(sparse["indices"]["bufferView"])
                used.add(sparse["values"]["bufferView"])
        for image in gltf.get("images", []):
            if "bufferView" in image:
                used.add(image["bufferView"])

        remap, views, chunks, offset = {}, [], [], 0
        for old in sorted(used):
            data = self.views[old]
            view = dict(gltf["bufferViews"][old])
            view["byteOffset"] = offset
            view["byteLength"] = len(data)
            remap[old] = len(views)
            views.append(view)
            padding = (-len(data)) % 4
            chunks.append(data + b"\x00" * padding)
            offset += len(data) + padding

        for accessor in gltf.get("accessors", []):
            if "bufferView" in accessor:
                accessor["bufferView"] = remap[accessor["bufferView"]]
            sparse = accessor.get("sparse")
            if sparse:
                sparse["indices"]["bufferView"] = remap[sparse["indices"]["bufferView"]]
                sparse["values"]["bufferView"] = remap[sparse["values"]["bufferView"]]
        for image in gltf.get("images", []):
            if "bufferView" in image:
                image["bufferView"] = remap[image["bufferView"]]

        gltf["bufferViews"] = views
        self.views = [self.views[old] for old in sorted(used)]
        binary = b"".join(chunks)
        gltf["buffers"] = [{"byteLength": len(binary)}]

        json_bytes = json.dumps(gltf, separators=(",", ":")).encode("utf-8")
        json_bytes += b" " * ((-len(json_bytes)) % 4)
        total = 12 + 8 + len(json_bytes) + 8 + len(binary)
        with open(path, "wb") as f:
            f.write(struct.pack("<III", GLB_MAGIC, 2, total))
            f.write(struct.pack("<II", len(json_bytes), CHUNK_JSON))
            f.write(json_bytes)
            f.write(struct.pack("<II", len(binary), CHUNK_BIN))
            f.write(binary)
        return total

    # ---- scene helpers --------------------------------------------------------------------

    def node_index(self, name: str) -> int:
        for i, node in enumerate(self.gltf["nodes"]):
            if node.get("name") == name:
                return i
        raise KeyError(name)

    def parents(self) -> dict:
        return {child: i for i, node in enumerate(self.gltf["nodes"]) for child in node.get("children", [])}

    def local_matrix(self, index: int) -> np.ndarray:
        node = self.gltf["nodes"][index]
        if "matrix" in node:
            return np.array(node["matrix"], dtype=np.float64).reshape(4, 4).T
        x, y, z, w = node.get("rotation", [0, 0, 0, 1])
        rotation = np.array([
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ])
        matrix = np.eye(4)
        matrix[:3, :3] = rotation @ np.diag(node.get("scale", [1, 1, 1]))
        matrix[:3, 3] = node.get("translation", [0, 0, 0])
        return matrix

    def world_matrix(self, index: int) -> np.ndarray:
        parents = self.parents()
        matrix = self.local_matrix(index)
        while index in parents:
            index = parents[index]
            matrix = self.local_matrix(index) @ matrix
        return matrix
