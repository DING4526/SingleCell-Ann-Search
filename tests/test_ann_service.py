"""HNSW 索引测试：构建、保存、加载、查询。"""
import os
import sys
import tempfile
import numpy as np
import hnswlib
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def _build_test_index(vectors, tmpdir, metric="l2"):
    """辅助函数：构建并保存一个 HNSW 索引。"""
    n, dim = vectors.shape
    space = "cosine" if metric == "cosine" else "l2"
    index = hnswlib.Index(space=space, dim=dim)
    index.init_index(max_elements=n, ef_construction=200, M=16)
    index.set_ef(100)
    labels = np.arange(n, dtype=np.int64)
    index.add_items(vectors, labels)

    path = os.path.join(tmpdir, f"test_{metric}.bin")
    index.save_index(path)
    return index, path


def test_hnsw_build_and_query():
    """测试 HNSW 索引可以构建和查询。"""
    np.random.seed(0)
    vectors = np.random.randn(100, 20).astype(np.float32)

    with tempfile.TemporaryDirectory() as tmpdir:
        index, path = _build_test_index(vectors, tmpdir)

        # 查询
        query = vectors[0:1]
        labels, distances = index.knn_query(query, k=10)

        assert labels.shape == (1, 10)
        assert distances.shape == (1, 10)


def test_hnsw_result_count_equals_top_k():
    """测试查询结果数量等于 top_k。"""
    np.random.seed(1)
    vectors = np.random.randn(200, 20).astype(np.float32)
    top_k = 15

    with tempfile.TemporaryDirectory() as tmpdir:
        index, _ = _build_test_index(vectors, tmpdir)

        query = vectors[5:6]
        labels, distances = index.knn_query(query, k=top_k)

        assert len(labels[0]) == top_k
        assert len(distances[0]) == top_k


def test_exclude_self():
    """测试 exclude_self 可以排除查询细胞自身。"""
    np.random.seed(2)
    vectors = np.random.randn(100, 20).astype(np.float32)

    with tempfile.TemporaryDirectory() as tmpdir:
        index, _ = _build_test_index(vectors, tmpdir)

        query_idx = 42
        query = vectors[query_idx : query_idx + 1]
        labels, distances = index.knn_query(query, k=11)

        # 第一个结果是自身（距离约为 0），过滤掉
        filtered = [l for l in labels[0].tolist() if l != query_idx]
        assert query_idx not in filtered
        assert len(filtered) == 10


def test_hnsw_save_and_load():
    """测试 HNSW 索引可以保存和加载。"""
    np.random.seed(3)
    vectors = np.random.randn(100, 20).astype(np.float32)

    with tempfile.TemporaryDirectory() as tmpdir:
        index, path = _build_test_index(vectors, tmpdir)

        # 加载索引
        loaded = hnswlib.Index(space="l2", dim=20)
        loaded.load_index(path, max_elements=0)
        loaded.set_ef(100)

        query = vectors[10:11]
        labels1, _ = index.knn_query(query, k=5)
        labels2, _ = loaded.knn_query(query, k=5)

        assert labels1[0].tolist() == labels2[0].tolist()


def test_cosine_metric():
    """测试 HNSW 支持 cosine 距离度量。"""
    np.random.seed(4)
    vectors = np.random.randn(100, 20).astype(np.float32)

    with tempfile.TemporaryDirectory() as tmpdir:
        index, _ = _build_test_index(vectors, tmpdir, metric="cosine")

        query = vectors[0:1]
        labels, distances = index.knn_query(query, k=5)

        assert labels.shape == (1, 5)
        # 余弦距离应在 [0, 2] 范围内
        assert all(0 <= d <= 2 for d in distances[0])


def test_backend_registry_reports_faiss_unavailable(monkeypatch):
    import app.services.ann_backend_service as svc

    monkeypatch.setattr(svc, "_import_faiss", lambda: (None, "missing faiss"))
    catalog = {row["key"]: row for row in svc.algorithm_catalog(n_cells=100, dim=20)}
    assert catalog["hnswlib_hnsw"]["available"] is True
    assert catalog["hnswlib_rp_hnsw"]["available"] is True
    assert catalog["faiss_flat"]["available"] is False
    assert "missing faiss" in catalog["faiss_flat"]["disabled_reason"]


def test_pluggable_hnsw_and_rp_hnsw_backends_roundtrip():
    from pathlib import Path
    from app.services.ann_backend_service import build_backend_index, load_backend_index

    rng = np.random.default_rng(11)
    vectors = rng.normal(size=(160, 20)).astype(np.float32)
    with tempfile.TemporaryDirectory() as tmpdir:
        index_path = Path(tmpdir) / "hnsw.bin"
        info = build_backend_index("hnswlib_hnsw", vectors, "l2", index_path, {"M": 8, "ef_construction": 80, "ef_search": 50})
        loaded = load_backend_index("hnswlib_hnsw", "l2", 20, index_path, info["params"])
        labels, distances = loaded.query(vectors[0:1], 6)
        assert labels.shape == (1, 6)
        assert distances.shape == (1, 6)

        rp_path = Path(tmpdir) / "rp.bin"
        prep_path = Path(tmpdir) / "rp.npz"
        rp_info = build_backend_index(
            "hnswlib_rp_hnsw",
            vectors,
            "l2",
            rp_path,
            {"projection_dim": 10, "random_state": 42, "M": 8, "ef_construction": 80, "ef_search": 50},
            preprocess_path=prep_path,
        )
        rp_loaded = load_backend_index("hnswlib_rp_hnsw", "l2", 20, rp_path, rp_info["params"], prep_path)
        rp_labels, _ = rp_loaded.query(vectors[0:1], 6)
        assert rp_labels.shape == (1, 6)


def test_faiss_backends_roundtrip_when_available():
    pytest.importorskip("faiss")
    from pathlib import Path
    from app.services.ann_backend_service import build_backend_index, load_backend_index

    rng = np.random.default_rng(12)
    vectors = rng.normal(size=(320, 20)).astype(np.float32)
    with tempfile.TemporaryDirectory() as tmpdir:
        for algorithm, params in [
            ("faiss_flat", {}),
            ("faiss_ivf_flat", {"nlist": 8, "nprobe": 4}),
            ("faiss_ivf_pq", {"nlist": 8, "nprobe": 4, "pq_m": 4, "nbits": 4}),
        ]:
            path = Path(tmpdir) / f"{algorithm}.index"
            info = build_backend_index(algorithm, vectors, "l2", path, params)
            loaded = load_backend_index(algorithm, "l2", vectors.shape[1], path, info["params"])
            labels, distances = loaded.query(vectors[0:1], 6)
            assert labels.shape == (1, 6)
            assert distances.shape == (1, 6)
            assert info["index_size_bytes"] > 0


def test_recommendation_tags_allow_tied_best_recall_and_gate_speed():
    from types import SimpleNamespace
    from app.services.recommendation_service import assign_recommendation_tags

    rows = [
        SimpleNamespace(id=1, status="success", recall_at_k=1.0, avg_query_time_ms=0.20, p95_query_time_ms=0.30, index_size_bytes=10_000),
        SimpleNamespace(id=2, status="success", recall_at_k=1.0, avg_query_time_ms=0.25, p95_query_time_ms=0.35, index_size_bytes=12_000),
        SimpleNamespace(id=3, status="success", recall_at_k=0.35, avg_query_time_ms=0.01, p95_query_time_ms=0.02, index_size_bytes=1_000),
    ]

    tags = assign_recommendation_tags(rows)

    assert "best_recall" in tags[1]
    assert "best_recall" in tags[2]
    assert "best_speed" in tags[1]
    assert "best_speed" not in tags[3]
    assert "fast_but_low_recall" in tags[3]
    assert "not_recommended" in tags[3]


def test_balanced_tag_requires_high_recall():
    from types import SimpleNamespace
    from app.services.recommendation_service import assign_recommendation_tags

    rows = [
        SimpleNamespace(id=1, status="success", recall_at_k=0.94, avg_query_time_ms=0.01, p95_query_time_ms=0.02, index_size_bytes=10_000),
        SimpleNamespace(id=2, status="success", recall_at_k=0.96, avg_query_time_ms=0.20, p95_query_time_ms=0.30, index_size_bytes=12_000),
    ]

    tags = assign_recommendation_tags(rows)

    assert "best_balanced" not in tags[1]
    assert "best_balanced" in tags[2]


def test_selection_recommendations_are_distinct_and_quality_gated():
    from types import SimpleNamespace
    from app.services.recommendation_service import assign_selection_recommendations

    rows = [
        SimpleNamespace(id=1, status="success", recall_at_k=1.0, speedup=5.0, p95_query_time_ms=0.40, index_size_bytes=20_000),
        SimpleNamespace(id=2, status="success", recall_at_k=0.98, speedup=12.0, p95_query_time_ms=0.12, index_size_bytes=15_000),
        SimpleNamespace(id=5, status="success", recall_at_k=0.96, speedup=7.0, p95_query_time_ms=0.30, index_size_bytes=18_000),
        SimpleNamespace(id=3, status="success", recall_at_k=0.92, speedup=20.0, p95_query_time_ms=0.08, index_size_bytes=8_000),
        SimpleNamespace(id=4, status="success", recall_at_k=0.70, speedup=100.0, p95_query_time_ms=0.01, index_size_bytes=1_000),
    ]

    labels, selected = assign_selection_recommendations(rows)

    assert labels[1] == ["best_recall"]
    assert "best_speed" in labels[3]
    assert "best_balanced" in labels[2]
    assert selected == [1, 3, 2]
    assert 4 not in selected


def test_candidate_config_validation_rejects_duplicates_and_exact_baseline():
    from types import SimpleNamespace
    from app.services.index_experiment_service import validate_candidate_configs

    dataset = SimpleNamespace(n_cells=320, vector_dim=20)
    duplicate = {"key": "a", "name": "A", "algorithm": "hnswlib_hnsw", "params": {"M": 8, "ef_construction": 80, "ef_search": 32}}
    with pytest.raises(ValueError, match="重复配置"):
        validate_candidate_configs(dataset, [duplicate, {**duplicate, "key": "b", "name": "B"}])

    with pytest.raises(ValueError, match="精确基线"):
        validate_candidate_configs(dataset, [
            {"key": "flat", "name": "Flat", "algorithm": "faiss_flat", "params": {}},
            {"key": "hnsw", "name": "HNSW", "algorithm": "hnswlib_hnsw", "params": {}},
        ])

    with pytest.raises(ValueError, match="2 到 12"):
        validate_candidate_configs(dataset, [duplicate])


def test_candidate_cleanup_rejects_paths_outside_index_root():
    from types import SimpleNamespace
    from flask import Flask
    from app.services.index_experiment_service import _discard_index_artifact

    with tempfile.TemporaryDirectory() as tmpdir:
        app = Flask(__name__)
        app.config["INDEX_DIR"] = os.path.join(tmpdir, "indexes")
        os.makedirs(app.config["INDEX_DIR"], exist_ok=True)
        index = SimpleNamespace(
            lifecycle="candidate",
            discarded_at=None,
            index_path="../outside.bin",
            preprocess_path=None,
            status="ready",
            error_message=None,
        )
        with app.app_context():
            removed, errors = _discard_index_artifact(index)

        assert removed == 0
        assert errors
        assert index.lifecycle == "discarded"
        assert index.status == "cleanup_error"
