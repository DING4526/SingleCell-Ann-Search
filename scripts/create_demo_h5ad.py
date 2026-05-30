"""生成用于测试的 demo h5ad 数据集。"""
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import numpy as np
import pandas as pd
import anndata as ad


def create_demo_h5ad(output_path: str = None):
    """生成一个包含 400 个细胞、80 个基因的 demo 数据集。

    包含 cell_type、disease、AgeGroup 元信息，
    以及 X_pca（20 维）和 X_umap（2 维）降维结果。
    """
    if output_path is None:
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        output_path = os.path.join(base_dir, "data", "raw", "demo_liver.h5ad")

    np.random.seed(42)
    n_cells = 400
    n_genes = 80

    # 随机表达矩阵
    X = np.random.poisson(2, size=(n_cells, n_genes)).astype(np.float32)

    # 细胞元信息
    cell_types = np.random.choice(
        ["Hepatocyte", "Kupffer cell", "Endothelial", "Stellate cell", "Cholangiocyte"],
        size=n_cells,
        p=[0.4, 0.2, 0.15, 0.15, 0.1],
    )
    diseases = np.random.choice(["Healthy", "NAFLD", "Fibrosis"], size=n_cells, p=[0.6, 0.25, 0.15])
    age_groups = np.random.choice(["Infant", "Child", "Adolescent", "Adult"], size=n_cells, p=[0.2, 0.3, 0.25, 0.25])

    obs = pd.DataFrame(
        {
            "cell_type": pd.Categorical(cell_types),
            "disease": pd.Categorical(diseases),
            "AgeGroup": pd.Categorical(age_groups),
        },
        index=[f"cell_{i:04d}" for i in range(n_cells)],
    )

    var = pd.DataFrame(index=[f"gene_{i:03d}" for i in range(n_genes)])

    adata = ad.AnnData(X=X, obs=obs, var=var)

    # PCA 降维：20 维
    adata.obsm["X_pca"] = np.random.randn(n_cells, 20).astype(np.float32)

    # UMAP 降维：2 维（带聚类结构）
    unique_types = ["Hepatocyte", "Kupffer cell", "Endothelial", "Stellate cell", "Cholangiocyte"]
    base_coords = np.random.randn(len(unique_types), 2) * 5  # 聚类中心
    type_to_cluster = {t: i for i, t in enumerate(unique_types)}
    cluster_ids = np.array([type_to_cluster[ct] for ct in cell_types])
    umap = base_coords[cluster_ids] + np.random.randn(n_cells, 2) * 0.8
    adata.obsm["X_umap"] = umap.astype(np.float32)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    adata.write_h5ad(output_path)
    print(f"Demo 数据集已生成: {output_path}")
    print(f"  细胞数: {n_cells}, 基因数: {n_genes}")
    print(f"  PCA 维度: 20, UMAP 维度: 2")
    print(f"  细胞类型分布: {dict(zip(*np.unique(cell_types, return_counts=True)))}")
    return output_path


if __name__ == "__main__":
    create_demo_h5ad()
