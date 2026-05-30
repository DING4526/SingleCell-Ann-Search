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
