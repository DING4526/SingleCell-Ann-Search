"""Pluggable ANN index backends used by persistent indexes and experiments."""
from __future__ import annotations

import json
import math
import pathlib
import time
from dataclasses import dataclass
from typing import Any

import hnswlib
import numpy as np


HNSWLIB_HNSW = "hnswlib_hnsw"
HNSWLIB_RP_HNSW = "hnswlib_rp_hnsw"
FAISS_FLAT = "faiss_flat"
FAISS_IVF_FLAT = "faiss_ivf_flat"
FAISS_IVF_PQ = "faiss_ivf_pq"

SUPPORTED_ALGORITHMS = [
    HNSWLIB_HNSW,
    HNSWLIB_RP_HNSW,
    FAISS_FLAT,
    FAISS_IVF_FLAT,
    FAISS_IVF_PQ,
]


def _json_params(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _int_param(params: dict, key: str, default: int, min_value: int | None = None, max_value: int | None = None) -> int:
    value = int(params.get(key, default))
    if min_value is not None:
        value = max(min_value, value)
    if max_value is not None:
        value = min(max_value, value)
    return value


def _default_nlist(n_cells: int) -> int:
    if n_cells <= 8:
        return max(1, n_cells)
    return max(2, min(4096, int(round(math.sqrt(n_cells)))))


def _default_pq_m(dim: int) -> int:
    target = min(8, dim)
    for candidate in range(target, 0, -1):
        if dim % candidate == 0:
            return candidate
    return 1


def normalize_algorithm(algorithm: str | None) -> str:
    if not algorithm or algorithm == "HNSW":
        return HNSWLIB_HNSW
    return algorithm


def default_params(algorithm: str, n_cells: int | None = None, dim: int | None = None) -> dict:
    algorithm = normalize_algorithm(algorithm)
    n = max(1, int(n_cells or 1000))
    d = max(1, int(dim or 20))
    if algorithm == HNSWLIB_HNSW:
        return {"M": 16, "ef_construction": 200, "ef_search": 100}
    if algorithm == HNSWLIB_RP_HNSW:
        return {"projection_dim": min(16, d), "random_state": 42, "M": 12, "ef_construction": 120, "ef_search": 64}
    if algorithm == FAISS_FLAT:
        return {}
    if algorithm == FAISS_IVF_FLAT:
        nlist = _default_nlist(n)
        return {"nlist": nlist, "nprobe": min(8, nlist)}
    if algorithm == FAISS_IVF_PQ:
        nlist = _default_nlist(n)
        return {"nlist": nlist, "nprobe": min(8, nlist), "pq_m": _default_pq_m(d), "nbits": 4}
    return {}


def merge_params(algorithm: str, params: dict | None, n_cells: int | None = None, dim: int | None = None) -> dict:
    merged = default_params(algorithm, n_cells=n_cells, dim=dim)
    for key, value in (params or {}).items():
        if value is not None and value != "":
            merged[key] = value
    algorithm = normalize_algorithm(algorithm)
    if algorithm in (HNSWLIB_HNSW, HNSWLIB_RP_HNSW):
        merged["M"] = _int_param(merged, "M", 16, 2, 128)
        merged["ef_construction"] = _int_param(merged, "ef_construction", 200, merged["M"], 2000)
        merged["ef_search"] = _int_param(merged, "ef_search", 100, 1, 5000)
    if algorithm == HNSWLIB_RP_HNSW:
        d = max(1, int(dim or merged.get("projection_dim", 16)))
        merged["projection_dim"] = _int_param(merged, "projection_dim", min(16, d), 1, d)
        merged["random_state"] = _int_param(merged, "random_state", 42)
    if algorithm in (FAISS_IVF_FLAT, FAISS_IVF_PQ):
        n = max(1, int(n_cells or 1))
        merged["nlist"] = _int_param(merged, "nlist", _default_nlist(n), 1, n)
        merged["nprobe"] = _int_param(merged, "nprobe", min(8, merged["nlist"]), 1, merged["nlist"])
    if algorithm == FAISS_IVF_PQ:
        d = max(1, int(dim or 1))
        merged["pq_m"] = _int_param(merged, "pq_m", _default_pq_m(d), 1, d)
        if d % merged["pq_m"] != 0:
            merged["pq_m"] = _default_pq_m(d)
        merged["nbits"] = _int_param(merged, "nbits", 4, 2, 8)
    return merged


def _import_faiss():
    try:
        import faiss  # type: ignore

        return faiss, None
    except Exception as exc:  # pragma: no cover - depends on optional wheel availability
        return None, str(exc)


def faiss_available() -> tuple[bool, str | None, str | None]:
    faiss, error = _import_faiss()
    if faiss is None:
        return False, None, error
    return True, getattr(faiss, "__version__", "unknown"), None


def algorithm_catalog(n_cells: int | None = None, dim: int | None = None) -> list[dict]:
    faiss_ok, faiss_version, faiss_error = faiss_available()
    catalog = [
        {
            "key": HNSWLIB_HNSW,
            "label": "HNSW (hnswlib)",
            "family": "graph",
            "available": True,
            "disabled_reason": None,
            "supports_metrics": ["l2", "cosine"],
            "default_params": default_params(HNSWLIB_HNSW, n_cells, dim),
            "backend_version": getattr(hnswlib, "__version__", "hnswlib"),
        },
        {
            "key": HNSWLIB_RP_HNSW,
            "label": "Random Projection + HNSW",
            "family": "graph+projection",
            "available": True,
            "disabled_reason": None,
            "supports_metrics": ["l2", "cosine"],
            "default_params": default_params(HNSWLIB_RP_HNSW, n_cells, dim),
            "backend_version": getattr(hnswlib, "__version__", "hnswlib"),
        },
    ]
    for key, label, family in [
        (FAISS_FLAT, "FAISS Flat", "exact"),
        (FAISS_IVF_FLAT, "FAISS IVF-Flat", "inverted-file"),
        (FAISS_IVF_PQ, "FAISS IVF-PQ", "compressed"),
    ]:
        catalog.append(
            {
                "key": key,
                "label": label,
                "family": family,
                "available": faiss_ok,
                "disabled_reason": None if faiss_ok else f"faiss-cpu unavailable: {faiss_error}",
                "supports_metrics": ["l2", "cosine"],
                "default_params": default_params(key, n_cells, dim),
                "backend_version": faiss_version,
            }
        )
    return catalog


def ensure_algorithm_available(algorithm: str):
    algorithm = normalize_algorithm(algorithm)
    if algorithm not in SUPPORTED_ALGORITHMS:
        raise ValueError(f"Unsupported ANN algorithm: {algorithm}")
    if algorithm.startswith("faiss_"):
        ok, _, error = faiss_available()
        if not ok:
            raise RuntimeError(f"FAISS backend is not available: {error}")


def _as_float32(vectors: np.ndarray) -> np.ndarray:
    return np.ascontiguousarray(np.asarray(vectors, dtype=np.float32))


def _space(metric: str) -> str:
    return "cosine" if metric == "cosine" else "l2"


def _projection_matrix(dim: int, target_dim: int, random_state: int) -> np.ndarray:
    rng = np.random.default_rng(random_state)
    matrix = rng.normal(0.0, 1.0 / math.sqrt(target_dim), size=(dim, target_dim))
    return matrix.astype(np.float32)


def _faiss_metric(faiss: Any, metric: str):
    return faiss.METRIC_INNER_PRODUCT if metric == "cosine" else faiss.METRIC_L2


def _faiss_vectors(faiss: Any, vectors: np.ndarray, metric: str) -> np.ndarray:
    prepared = _as_float32(vectors).copy()
    if metric == "cosine":
        faiss.normalize_L2(prepared)
    return prepared


@dataclass
class LoadedBackendIndex:
    algorithm: str
    metric: str
    index: Any
    params: dict
    projection: np.ndarray | None = None
    faiss: Any | None = None

    def query(self, query_vectors: np.ndarray, k: int) -> tuple[np.ndarray, np.ndarray]:
        q = _as_float32(query_vectors)
        if self.projection is not None:
            q = _as_float32(q @ self.projection)
        if self.faiss is not None:
            fq = _faiss_vectors(self.faiss, q, self.metric)
            distances, labels = self.index.search(fq, int(k))
            if self.metric == "cosine":
                distances = 1.0 - distances
            return labels.astype(np.int64), distances.astype(np.float32)
        labels, distances = self.index.knn_query(q, k=int(k))
        return labels.astype(np.int64), distances.astype(np.float32)


def build_backend_index(
    algorithm: str,
    vectors: np.ndarray,
    metric: str,
    index_path: pathlib.Path,
    params: dict | None = None,
    preprocess_path: pathlib.Path | None = None,
) -> dict:
    algorithm = normalize_algorithm(algorithm)
    ensure_algorithm_available(algorithm)
    if metric not in ("l2", "cosine"):
        raise ValueError("metric must be l2 or cosine")
    vectors = _as_float32(vectors)
    n_cells, dim = vectors.shape
    params = merge_params(algorithm, params or {}, n_cells=n_cells, dim=dim)
    t0 = time.perf_counter()

    if algorithm == HNSWLIB_HNSW:
        index = hnswlib.Index(space=_space(metric), dim=dim)
        index.init_index(max_elements=n_cells, ef_construction=params["ef_construction"], M=params["M"])
        index.set_ef(params["ef_search"])
        index.add_items(vectors, np.arange(n_cells, dtype=np.int64))
        index.save_index(str(index_path))
        backend_version = getattr(hnswlib, "__version__", "hnswlib")
    elif algorithm == HNSWLIB_RP_HNSW:
        if preprocess_path is None:
            raise ValueError("preprocess_path is required for random projection HNSW")
        matrix = _projection_matrix(dim, params["projection_dim"], params["random_state"])
        projected = _as_float32(vectors @ matrix)
        np.savez_compressed(str(preprocess_path), projection=matrix)
        index = hnswlib.Index(space=_space(metric), dim=projected.shape[1])
        index.init_index(max_elements=n_cells, ef_construction=params["ef_construction"], M=params["M"])
        index.set_ef(params["ef_search"])
        index.add_items(projected, np.arange(n_cells, dtype=np.int64))
        index.save_index(str(index_path))
        backend_version = getattr(hnswlib, "__version__", "hnswlib")
    else:
        faiss, _ = _import_faiss()
        if faiss is None:
            raise RuntimeError("FAISS backend is not available")
        x = _faiss_vectors(faiss, vectors, metric)
        metric_type = _faiss_metric(faiss, metric)
        if algorithm == FAISS_FLAT:
            index = faiss.IndexFlatIP(dim) if metric == "cosine" else faiss.IndexFlatL2(dim)
        elif algorithm == FAISS_IVF_FLAT:
            quantizer = faiss.IndexFlatIP(dim) if metric == "cosine" else faiss.IndexFlatL2(dim)
            index = faiss.IndexIVFFlat(quantizer, dim, params["nlist"], metric_type)
            index.train(x)
            index.nprobe = params["nprobe"]
        elif algorithm == FAISS_IVF_PQ:
            min_train = max(params["nlist"], 2 ** params["nbits"])
            if n_cells < min_train:
                raise ValueError(f"IVF-PQ needs at least {min_train} training vectors, got {n_cells}")
            quantizer = faiss.IndexFlatIP(dim) if metric == "cosine" else faiss.IndexFlatL2(dim)
            index = faiss.IndexIVFPQ(quantizer, dim, params["nlist"], params["pq_m"], params["nbits"], metric_type)
            index.train(x)
            index.nprobe = params["nprobe"]
        else:  # pragma: no cover - guarded by ensure_algorithm_available
            raise ValueError(f"Unsupported ANN algorithm: {algorithm}")
        index.add(x)
        faiss.write_index(index, str(index_path))
        backend_version = getattr(faiss, "__version__", "unknown")

    build_time_ms = (time.perf_counter() - t0) * 1000
    index_size = index_path.stat().st_size if index_path.exists() else None
    preprocess_size = preprocess_path.stat().st_size if preprocess_path and preprocess_path.exists() else 0
    return {
        "algorithm": algorithm,
        "params": params,
        "build_time_ms": build_time_ms,
        "index_size_bytes": int((index_size or 0) + preprocess_size),
        "backend_version": backend_version,
    }


def load_backend_index(
    algorithm: str,
    metric: str,
    dim: int,
    index_path: pathlib.Path,
    params: dict | None = None,
    preprocess_path: pathlib.Path | None = None,
) -> LoadedBackendIndex:
    algorithm = normalize_algorithm(algorithm)
    ensure_algorithm_available(algorithm)
    params = merge_params(algorithm, params or {}, dim=dim)
    if algorithm == HNSWLIB_HNSW:
        index = hnswlib.Index(space=_space(metric), dim=dim)
        index.load_index(str(index_path), max_elements=0)
        index.set_ef(params.get("ef_search", 100))
        return LoadedBackendIndex(algorithm, metric, index, params)
    if algorithm == HNSWLIB_RP_HNSW:
        if preprocess_path is None or not preprocess_path.exists():
            raise FileNotFoundError("Random projection preprocessing file is missing")
        payload = np.load(str(preprocess_path))
        projection = _as_float32(payload["projection"])
        index = hnswlib.Index(space=_space(metric), dim=projection.shape[1])
        index.load_index(str(index_path), max_elements=0)
        index.set_ef(params.get("ef_search", 64))
        return LoadedBackendIndex(algorithm, metric, index, params, projection=projection)

    faiss, _ = _import_faiss()
    if faiss is None:
        raise RuntimeError("FAISS backend is not available")
    index = faiss.read_index(str(index_path))
    if hasattr(index, "nprobe") and "nprobe" in params:
        index.nprobe = int(params["nprobe"])
    return LoadedBackendIndex(algorithm, metric, index, params, faiss=faiss)


def params_from_index(ann_index) -> dict:
    params = _json_params(getattr(ann_index, "params_json", None))
    if not params:
        params = {
            "M": getattr(ann_index, "M", 16),
            "ef_construction": getattr(ann_index, "ef_construction", 200),
            "ef_search": getattr(ann_index, "ef_search", 100),
        }
    return params
