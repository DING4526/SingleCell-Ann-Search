"""数据处理服务测试：demo h5ad 生成与 X_pca 提取。"""
import os
import sys
import tempfile
import numpy as np
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_demo_h5ad_creation():
    """测试 demo h5ad 文件可以生成并正确读取。"""
    from scripts.create_demo_h5ad import create_demo_h5ad
    import scanpy as sc

    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "test_demo.h5ad")
        create_demo_h5ad(path)

        assert os.path.exists(path)

        adata = sc.read_h5ad(path)
        assert adata.n_obs == 400
        assert adata.n_vars == 80
        assert "cell_type" in adata.obs.columns
        assert "disease" in adata.obs.columns
        assert "AgeGroup" in adata.obs.columns


def test_x_pca_extraction():
    """测试 X_pca 可以从 demo h5ad 中正确提取。"""
    from scripts.create_demo_h5ad import create_demo_h5ad
    import scanpy as sc

    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "test_demo.h5ad")
        create_demo_h5ad(path)

        adata = sc.read_h5ad(path)
        assert "X_pca" in adata.obsm
        X_pca = np.array(adata.obsm["X_pca"], dtype=np.float32)
        assert X_pca.shape == (400, 20)
        assert X_pca.dtype == np.float32


def test_x_umap_extraction():
    """测试 X_umap 可以从 demo h5ad 中正确提取。"""
    from scripts.create_demo_h5ad import create_demo_h5ad
    import scanpy as sc

    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "test_demo.h5ad")
        create_demo_h5ad(path)

        adata = sc.read_h5ad(path)
        assert "X_umap" in adata.obsm
        X_umap = np.array(adata.obsm["X_umap"])
        assert X_umap.shape == (400, 2)
