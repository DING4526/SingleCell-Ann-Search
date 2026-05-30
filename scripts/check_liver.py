import scanpy as sc

path = "data/raw/liver.h5ad"

adata = sc.read_h5ad(path)

print(adata)
print("细胞数:", adata.n_obs)
print("基因数:", adata.n_vars)

print("\nobs columns:")
print(list(adata.obs.columns))

print("\nobsm keys:")
print(list(adata.obsm.keys()))

if "X_pca" in adata.obsm:
    print("\nX_pca shape:", adata.obsm["X_pca"].shape)
else:
    print("\n错误：没有找到 adata.obsm['X_pca']")

if "X_umap" in adata.obsm:
    print("X_umap shape:", adata.obsm["X_umap"].shape)
else:
    print("提示：没有 X_umap，系统会用 X_pca 前两维画图")

for col in ["cell_type", "disease", "AgeGroup"]:
    if col in adata.obs.columns:
        print(f"\n{col} value counts:")
        print(adata.obs[col].value_counts().head(20))
    else:
        print(f"\n提示：obs 中没有字段 {col}")
