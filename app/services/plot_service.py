import numpy as np
import scanpy as sc
import plotly.graph_objects as go
import plotly.express as px
from flask import current_app
from app.models import Dataset, Cell
from app.extensions import db


def _get_coords(dataset: Dataset):
    """从 h5ad 中获取 2D 坐标（优先 UMAP，否则用 PCA 前两维）。"""
    adata = sc.read_h5ad(dataset.file_path)
    if "X_umap" in adata.obsm:
        coords = np.array(adata.obsm["X_umap"])
        coord_label = "UMAP"
    elif "X_pca" in adata.obsm:
        coords = np.array(adata.obsm["X_pca"])[:, :2]
        coord_label = "PCA"
    else:
        return None, None, None
    return coords, coord_label, adata


def dataset_scatter_html(dataset_id: int) -> str:
    """生成全量细胞散点图，按 cell_type 着色。"""
    dataset = db.session.get(Dataset, dataset_id)
    if not dataset:
        return "<p>数据集不存在</p>"

    coords, coord_label, adata = _get_coords(dataset)
    if coords is None:
        return "<p>无可用的 UMAP 或 PCA 坐标</p>"

    cells = Cell.query.filter_by(dataset_id=dataset_id).order_by(Cell.cell_index).all()
    cell_types = [c.cell_type or "未知" for c in cells]

    fig = px.scatter(
        x=coords[:, 0],
        y=coords[:, 1],
        color=cell_types,
        labels={"x": f"{coord_label}1", "y": f"{coord_label}2", "color": "细胞类型"},
        title=f"{coord_label} 可视化 ({dataset.name})",
        hover_data={"cell_index": list(range(len(cells)))},
    )
    fig.update_layout(
        template="plotly_white",
        height=600,
        legend=dict(orientation="h", y=-0.15),
    )
    return fig.to_html(full_html=False, include_plotlyjs="cdn")


def search_scatter_html(dataset_id: int, query_cell_index: int, result_cell_indices: list) -> str:
    """生成检索结果散点图，高亮查询细胞和结果细胞。"""
    dataset = db.session.get(Dataset, dataset_id)
    if not dataset:
        return "<p>数据集不存在</p>"

    coords, coord_label, adata = _get_coords(dataset)
    if coords is None:
        return "<p>无可用的 UMAP 或 PCA 坐标</p>"

    cells = Cell.query.filter_by(dataset_id=dataset_id).order_by(Cell.cell_index).all()

    # 构建高亮分类标签
    result_set = set(result_cell_indices)
    highlight = []
    for i in range(len(cells)):
        if i == query_cell_index:
            highlight.append("Query")
        elif i in result_set:
            highlight.append("Result")
        else:
            highlight.append("Other")

    fig = go.Figure()

    # 背景点（其他细胞）
    other_mask = [h == "Other" for h in highlight]
    fig.add_trace(
        go.Scatter(
            x=coords[other_mask, 0],
            y=coords[other_mask, 1],
            mode="markers",
            marker=dict(size=4, color="lightgray", opacity=0.5),
            name="其他",
            hoverinfo="skip",
        )
    )

    # 结果细胞
    result_mask = [h == "Result" for h in highlight]
    if any(result_mask):
        fig.add_trace(
            go.Scatter(
                x=coords[result_mask, 0],
                y=coords[result_mask, 1],
                mode="markers",
                marker=dict(size=8, color="#2ecc71", line=dict(width=1, color="white")),
                name="相似细胞",
            )
        )

    # 查询细胞
    fig.add_trace(
        go.Scatter(
            x=[coords[query_cell_index, 0]],
            y=[coords[query_cell_index, 1]],
            mode="markers",
            marker=dict(size=14, color="#e74c3c", symbol="star", line=dict(width=2, color="white")),
            name="查询细胞",
        )
    )

    fig.update_layout(
        title=f"检索结果 - {coord_label} 视图",
        xaxis_title=f"{coord_label}1",
        yaxis_title=f"{coord_label}2",
        template="plotly_white",
        height=600,
        legend=dict(orientation="h", y=-0.15),
    )
    return fig.to_html(full_html=False, include_plotlyjs="cdn")


def eval_bar_html(metrics: dict) -> str:
    """生成 ANN 与精确检索性能对比柱状图。"""
    categories = ["ANN 耗时 (ms)", "精确检索耗时 (ms)"]
    values = [metrics["avg_ann_time_ms"], metrics["avg_exact_time_ms"]]

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=categories,
            y=values,
            marker_color=["#3498db", "#e74c3c"],
            text=[f"{v:.4f} ms" for v in values],
            textposition="auto",
        )
    )
    fig.update_layout(
        title="检索性能对比",
        yaxis_title="耗时 (ms)",
        template="plotly_white",
        height=400,
        annotations=[
            dict(
                text=f"Recall@{metrics.get('top_k', 'K')}: {metrics['avg_recall_at_k']:.2%}  |  加速比: {metrics['speedup']:.1f}x",
                xref="paper",
                yref="paper",
                x=0.5,
                y=1.08,
                showarrow=False,
                font=dict(size=14),
            )
        ],
    )
    return fig.to_html(full_html=False, include_plotlyjs="cdn")
