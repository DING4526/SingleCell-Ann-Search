import json
import numpy as np
import scanpy as sc
import plotly.graph_objects as go
from app.models import Dataset, Cell
from app.extensions import db

DARK_COLOR_CYCLE = [
    "#28c7c0",
    "#4dd4ff",
    "#7c8cff",
    "#b487ff",
    "#ff8fd8",
    "#ffb86b",
    "#f9f871",
    "#9bef83",
    "#5eead4",
    "#60a5fa",
    "#f472b6",
]

LIGHT_COLOR_CYCLE = [
    "#66cbc8",
    "#69d9c0",
    "#7ee5b0",
    "#a0ee9b",
    "#caf584",
    "#f9f871",
    "#417e7d",
    "#324b4b",
    "#95b1b0",
    "#6b7396",
    "#9fa6cc",
]

CHART_BG = "#050b16"
PLOT_BG = "#071225"
GRID_COLOR = "rgba(150, 185, 235, 0.2)"
FONT_COLOR = "#e3f0ff"


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


def _build_color_map(labels: list[str], use_dark_cycle: bool = True) -> dict[str, str]:
    """为分类标签构建稳定颜色映射。"""
    unique_labels = sorted(set(labels))
    palette = DARK_COLOR_CYCLE if use_dark_cycle else LIGHT_COLOR_CYCLE
    return {label: palette[i % len(palette)] for i, label in enumerate(unique_labels)}


def _apply_dark_layout(fig: go.Figure, title: str, xaxis_title: str, yaxis_title: str, height: int = 620):
    """统一深色图表风格，便于课堂投影展示。"""
    fig.update_layout(
        title=title,
        template="plotly_dark",
        paper_bgcolor=CHART_BG,
        plot_bgcolor=PLOT_BG,
        font=dict(color=FONT_COLOR, size=12),
        height=height,
        margin=dict(l=18, r=18, t=58, b=70),
        xaxis=dict(
            title=xaxis_title,
            gridcolor=GRID_COLOR,
            zeroline=False,
            showline=True,
            linecolor="rgba(144, 180, 233, 0.22)",
        ),
        yaxis=dict(
            title=yaxis_title,
            gridcolor=GRID_COLOR,
            zeroline=False,
            showline=True,
            linecolor="rgba(144, 180, 233, 0.22)",
        ),
        legend=dict(
            orientation="h",
            y=-0.18,
            x=0,
            bgcolor="rgba(12, 22, 40, 0.55)",
            bordercolor="rgba(148, 180, 228, 0.22)",
            borderwidth=1,
            font=dict(size=11),
        ),
    )


def dataset_scatter_html(dataset_id: int) -> str:
    """生成全量细胞散点图，按 cell_type 着色。"""
    dataset = db.session.get(Dataset, dataset_id)
    if not dataset:
        return "<p>数据集不存在</p>"

    coords, coord_label, adata = _get_coords(dataset)
    if coords is None:
        return "<p>无可用的 UMAP 或 PCA 坐标</p>"

    cells = Cell.query.filter_by(dataset_id=dataset_id).order_by(Cell.cell_index).all()
    if not cells:
        return "<p>暂无细胞元信息可视化</p>"

    cell_types = [c.cell_type or "未知" for c in cells]
    cell_indices = [c.cell_index for c in cells]
    diseases = [c.disease or "N/A" for c in cells]
    age_groups = [c.age_group or "N/A" for c in cells]
    cell_names = [c.cell_name or "N/A" for c in cells]
    color_map = _build_color_map(cell_types, use_dark_cycle=True)
    fig = go.Figure()

    for cell_type in sorted(set(cell_types)):
        type_indices = [i for i, value in enumerate(cell_types) if value == cell_type]
        customdata = [
            [
                cell_indices[i],
                cell_names[i],
                cell_types[i],
                diseases[i],
                age_groups[i],
            ]
            for i in type_indices
        ]

        fig.add_trace(
            go.Scatter(
                x=coords[type_indices, 0],
                y=coords[type_indices, 1],
                mode="markers",
                marker=dict(
                    size=5.2,
                    color=color_map[cell_type],
                    opacity=0.93,
                    line=dict(width=0.35, color="rgba(232,244,255,0.35)"),
                ),
                name=f"{cell_type} ({len(type_indices)})",
                customdata=customdata,
                hovertemplate=(
                    "cell_index: %{customdata[0]}<br>"
                    "cell_name: %{customdata[1]}<br>"
                    "cell_type: %{customdata[2]}<br>"
                    "disease: %{customdata[3]}<br>"
                    "age_group: %{customdata[4]}<extra></extra>"
                ),
            )
        )

    _apply_dark_layout(
        fig,
        title=f"{dataset.name} · {coord_label} 预览",
        xaxis_title=f"{coord_label}1",
        yaxis_title=f"{coord_label}2",
        height=640,
    )
    return fig.to_html(full_html=False, include_plotlyjs="cdn")


# ---------------------------------------------------------------------------
# JSON 版本：供 AJAX 接口返回，前端用 Plotly.react 渲染，避免 innerHTML 不执行脚本
# ---------------------------------------------------------------------------

def _fig_to_plotly_json(fig: go.Figure) -> dict:
    """将 Plotly Figure 序列化为可 JSON 传输的 dict（data + layout）。"""
    raw = json.loads(fig.to_json())
    return {"data": raw.get("data", []), "layout": raw.get("layout", {})}


def search_scatter_json(dataset_id: int, query_cell_index: int, result_cell_indices: list) -> dict:
    """生成检索结果散点图的 Plotly JSON，供 /api/search 返回后前端用 Plotly.react 渲染。"""
    dataset = db.session.get(Dataset, dataset_id)
    if not dataset:
        raise ValueError("数据集不存在")

    coords, coord_label, adata = _get_coords(dataset)
    if coords is None:
        raise ValueError("无可用的 UMAP 或 PCA 坐标")

    cells = Cell.query.filter_by(dataset_id=dataset_id).order_by(Cell.cell_index).all()
    if not cells:
        raise ValueError("暂无细胞元信息，无法绘图")

    result_set = set(result_cell_indices)
    highlight = []
    for i in range(len(cells)):
        if i == query_cell_index:
            highlight.append("Query")
        elif i in result_set:
            highlight.append("Result")
        else:
            highlight.append("Other")

    cell_info = {
        c.cell_index: {
            "cell_name": c.cell_name or "N/A",
            "cell_type": c.cell_type or "N/A",
            "disease": c.disease or "N/A",
            "age_group": c.age_group or "N/A",
        }
        for c in cells
    }
    all_cell_types = [cell_info[i]["cell_type"] for i in range(len(cells))]
    color_map = _build_color_map(all_cell_types, use_dark_cycle=True)
    fig = go.Figure()

    # 背景点
    other_indices = [i for i, h in enumerate(highlight) if h == "Other"]
    if other_indices:
        grouped_other = {}
        for idx in other_indices:
            grouped_other.setdefault(cell_info[idx]["cell_type"], []).append(idx)
        for cell_type, idx_list in grouped_other.items():
            fig.add_trace(go.Scatter(
                x=coords[idx_list, 0].tolist(), y=coords[idx_list, 1].tolist(),
                mode="markers",
                marker=dict(size=3.6, color=color_map.get(cell_type, "#95b1b0"), opacity=0.46,
                            line=dict(width=0.2, color="rgba(232,244,255,0.2)")),
                name=f"{cell_type} 背景", showlegend=False, hoverinfo="skip",
            ))

    # 结果细胞
    result_indices = [i for i, h in enumerate(highlight) if h == "Result"]
    if result_indices:
        grouped_result = {}
        for idx in result_indices:
            grouped_result.setdefault(cell_info[idx]["cell_type"], []).append(idx)
        for cell_type, idx_list in grouped_result.items():
            customdata = [
                [idx, cell_info[idx]["cell_name"], cell_info[idx]["cell_type"],
                 cell_info[idx]["disease"], cell_info[idx]["age_group"]]
                for idx in idx_list
            ]
            fig.add_trace(go.Scatter(
                x=coords[idx_list, 0].tolist(), y=coords[idx_list, 1].tolist(),
                mode="markers",
                marker=dict(size=9.2, color=color_map.get(cell_type, "#69d9c0"), opacity=0.98,
                            line=dict(width=1.6, color="#f5fbff")),
                name=f"相似细胞 · {cell_type}", customdata=customdata,
                hovertemplate=(
                    "cell_index: %{customdata[0]}<br>cell_name: %{customdata[1]}<br>"
                    "cell_type: %{customdata[2]}<br>disease: %{customdata[3]}<br>"
                    "age_group: %{customdata[4]}<extra></extra>"
                ),
            ))

    # 查询细胞
    qi = cell_info.get(query_cell_index, {})
    fig.add_trace(go.Scatter(
        x=[float(coords[query_cell_index, 0])], y=[float(coords[query_cell_index, 1])],
        mode="markers",
        marker=dict(size=16, color="#f9f871", symbol="star", line=dict(width=2.4, color="#ffd166")),
        name="查询细胞",
        customdata=[[query_cell_index, qi.get("cell_name", "N/A"), qi.get("cell_type", "N/A"),
                     qi.get("disease", "N/A"), qi.get("age_group", "N/A")]],
        hovertemplate=(
            "查询细胞<br>cell_index: %{customdata[0]}<br>cell_name: %{customdata[1]}<br>"
            "cell_type: %{customdata[2]}<br>disease: %{customdata[3]}<br>"
            "age_group: %{customdata[4]}<extra></extra>"
        ),
    ))

    _apply_dark_layout(fig, title=f"检索结果高亮 · {coord_label} 视图",
                       xaxis_title=f"{coord_label}1", yaxis_title=f"{coord_label}2", height=640)
    return _fig_to_plotly_json(fig)


def eval_bar_json(metrics: dict) -> dict:
    """生成性能对比柱状图的 Plotly JSON，供 /api/evaluate 返回后前端用 Plotly.react 渲染。"""
    categories = ["ANN 耗时 (ms)", "精确检索耗时 (ms)"]
    values = [metrics["avg_ann_time_ms"], metrics["avg_exact_time_ms"]]
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=categories, y=values,
        marker_color=["#8b5cf6", "#fb7185"],
        text=[f"{v:.4f} ms" for v in values],
        textposition="auto",
        width=[0.45, 0.45],
    ))
    fig.update_layout(
        title="ANN 与精确检索性能对比",
        yaxis_title="耗时 (ms)",
        template="plotly_dark",
        paper_bgcolor=CHART_BG, plot_bgcolor=PLOT_BG,
        font=dict(color=FONT_COLOR),
        height=320, bargap=0.5, bargroupgap=0.15,
        margin=dict(l=20, r=20, t=70, b=40),
        annotations=[dict(
            text=(
                f"Recall@{metrics.get('top_k', 'K')}: {metrics['avg_recall_at_k']:.2%}"
                f"  |  加速比: {metrics['speedup']:.1f}x"
            ),
            xref="paper", yref="paper", x=0.5, y=1.08,
            showarrow=False, font=dict(size=14),
        )],
    )
    return _fig_to_plotly_json(fig)
