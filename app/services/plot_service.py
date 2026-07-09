import json
import pathlib
import numpy as np
import pandas as pd
import scanpy as sc
import plotly.express as px
import plotly.graph_objects as go
from flask import current_app
from app.models import Dataset, Cell
from app.extensions import db

# ------------------ 配色 & 风格 ------------------
DARK_COLOR_CYCLE = [
    "#28c7c0", "#4dd4ff", "#7c8cff", "#b487ff", "#ff8fd8",
    "#ffb86b", "#f9f871", "#9bef83", "#5eead4", "#60a5fa", "#f472b6",
]

LIGHT_COLOR_CYCLE = [
    "#66cbc8", "#69d9c0", "#7ee5b0", "#a0ee9b", "#caf584",
    "#f9f871", "#417e7d", "#324b4b", "#95b1b0", "#6b7396", "#9fa6cc",
]

CHART_BG = "#050b16"
PLOT_BG = "#071225"
GRID_COLOR = "rgba(150, 185, 235, 0.2)"
FONT_COLOR = "#e3f0ff"


def _get_coords(dataset: Dataset):
    """获取 2D 坐标（优先 UMAP，否则 PCA 前两维）。"""
    adata = sc.read_h5ad(dataset.file_path)
    if "X_umap" in adata.obsm:
        return np.array(adata.obsm["X_umap"]), "UMAP", adata
    elif "X_pca" in adata.obsm:
        return np.array(adata.obsm["X_pca"])[:, :2], "PCA", adata
    return None, None, None


def _build_color_map(labels: list[str], use_dark_cycle: bool = True) -> dict[str, str]:
    """为分类标签构建稳定颜色映射。"""
    palette = DARK_COLOR_CYCLE if use_dark_cycle else LIGHT_COLOR_CYCLE
    unique_labels = sorted(set(labels))
    return {label: palette[i % len(palette)] for i, label in enumerate(unique_labels)}


# 年龄组固定配色：Ped 蓝色，Adult 橙色，未知灰色
_AGE_GROUP_FIXED = {
    "ped": "#4dd4ff",
    "pediatric": "#4dd4ff",
    "child": "#4dd4ff",
    "adult": "#ffb86b",
}
_AGE_GROUP_UNKNOWN = "#95b1b0"


def _build_age_group_color_map(labels: list[str]) -> dict[str, str]:
    """为年龄组标签构建固定颜色映射，不依赖排序顺序。

    Ped / Pediatric / Child → 明亮蓝色
    Adult → 橙色
    其他 → 灰色
    """
    unique_labels = sorted(set(labels))
    color_map = {}
    for label in unique_labels:
        key = label.strip().lower()
        color_map[label] = _AGE_GROUP_FIXED.get(key, _AGE_GROUP_UNKNOWN)
    return color_map


def _build_disease_color_map(labels: list[str]) -> dict[str, str]:
    """为疾病标签构建颜色映射。若仅有单一类别（如 normal），使用中性色。"""
    unique_labels = sorted(set(labels))
    if len(unique_labels) <= 1:
        return {label: "#95b1b0" for label in unique_labels}
    return _build_color_map(labels, use_dark_cycle=True)


def _muted_color(hex_color: str, alpha: float = 0.28, darken: float = 0.62) -> str:
    """压暗并透明化背景颜色。"""
    hex_color = hex_color.lstrip("#")
    r = int(int(hex_color[0:2], 16) * darken)
    g = int(int(hex_color[2:4], 16) * darken)
    b = int(int(hex_color[4:6], 16) * darken)
    return f"rgba({r},{g},{b},{alpha})"


def _apply_dark_layout(fig: go.Figure, title: str, xaxis_title: str, yaxis_title: str, height: int = 620):
    fig.update_layout(
        title=title,
        template="plotly_white",
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
        font=dict(color="#172033", size=12),
        height=height,
        margin=dict(l=54, r=156, t=58, b=58),
        xaxis=dict(title=xaxis_title, gridcolor="#edf2f7", zeroline=False, showline=True,
                   linecolor="#d8e1ec", mirror=False),
        yaxis=dict(title=yaxis_title, gridcolor="#edf2f7", zeroline=False, showline=True,
                   linecolor="#d8e1ec", mirror=False),
        legend=dict(
            orientation="v", y=1, x=1.02,
            xanchor="left", yanchor="top",
            title=dict(text="图例"),
            bgcolor="rgba(255, 255, 255, 0.92)",
            bordercolor="#e5eaf2",
            borderwidth=1,
            font=dict(size=11, color="#334155"),
        ),
        hovermode="closest",
        dragmode="pan",
    )


def _fig_to_plotly_json(fig: go.Figure) -> dict:
    raw = json.loads(fig.to_json())
    return {"data": raw.get("data", []), "layout": raw.get("layout", {})}


# ------------------ 数据集详情页缓存（v3 格式） ------------------
def generate_scatter_cache(dataset_id: int) -> str:
    dataset = db.session.get(Dataset, dataset_id)
    if not dataset:
        raise ValueError(f"Dataset {dataset_id} 不存在")

    coords, coord_label, adata = _get_coords(dataset)
    if coords is None:
        raise ValueError("无可用坐标")

    cells = db.session.query(Cell.cell_index, Cell.cell_type, Cell.disease, Cell.age_group)\
        .filter_by(dataset_id=dataset_id).order_by(Cell.cell_index).all()
    if not cells:
        raise ValueError("无细胞信息")

    usable_count = min(len(cells), coords.shape[0])
    cells = cells[:usable_count]
    coords = coords[:usable_count, :]

    cell_indices = [c.cell_index for c in cells]
    cell_types = [c.cell_type or "未知" for c in cells]
    diseases = [c.disease or "未知" for c in cells]
    age_groups = [c.age_group or "未知" for c in cells]

    # 三个维度的颜色映射（年龄组/疾病使用专用配色函数）
    cell_type_color_map = _build_color_map(cell_types, use_dark_cycle=True)
    disease_color_map = _build_disease_color_map(diseases)
    age_group_color_map = _build_age_group_color_map(age_groups)

    # 默认按 cell_type 着色
    marker_colors = [cell_type_color_map[ct] for ct in cell_types]

    # customdata: [cell_index, cell_type, disease, age_group]
    customdata = [
        [c.cell_index, c.cell_type or "未知", c.disease or "未知", c.age_group or "未知"]
        for c in cells
    ]

    fig = go.Figure()

    # 单条 Scattergl 轨迹承载全部点，便于前端颜色重映射
    fig.add_trace(go.Scattergl(
        x=coords[:, 0].tolist(),
        y=coords[:, 1].tolist(),
        mode="markers",
        marker=dict(size=3.2, opacity=0.38, color=marker_colors),
        customdata=customdata,
        hovertemplate="类型: %{customdata[1]}<br>疾病: %{customdata[2]}<br>年龄: %{customdata[3]}<extra>索引 #%{customdata[0]}</extra>",
        name="细胞",
    ))

    # 伪图例条目：每种 cell_type 一条不可见轨迹，仅用于图例显示
    for label, color in cell_type_color_map.items():
        fig.add_trace(go.Scatter(
            x=[None], y=[None],
            mode="markers",
            marker=dict(size=8, color=color),
            name=label,
            showlegend=True,
            hoverinfo="skip",
        ))

    _apply_dark_layout(fig, title=f"{dataset.name} · {coord_label} 预览", xaxis_title=f"{coord_label}1", yaxis_title=f"{coord_label}2", height=640)

    plot_json = _fig_to_plotly_json(fig)

    # v3 元数据：颜色映射表，供前端颜色切换使用
    plot_json["metadata"] = {
        "color_domains": {
            "cell_type": cell_type_color_map,
            "disease": disease_color_map,
            "age_group": age_group_color_map,
        }
    }

    cache_dir = pathlib.Path(current_app.config["CACHE_DIR"])
    cache_dir.mkdir(parents=True, exist_ok=True)
    filename = f"scatter_v3_{dataset_id}.json"
    cache_path = cache_dir / filename

    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(plot_json, f, ensure_ascii=False)

    dataset.scatter_cache_path = filename
    db.session.commit()
    return str(cache_path)


# ------------------ 检索结果散点图 ------------------
def search_scatter_json(dataset_id: int, query_cell_index: int, result_cell_indices: list, max_background_points: int = 15_000) -> dict:
    dataset = db.session.get(Dataset, dataset_id)
    if not dataset:
        raise ValueError("数据集不存在")

    coords, coord_label, adata = _get_coords(dataset)
    if coords is None:
        raise ValueError("无可用坐标")

    cells = db.session.query(Cell.cell_index, Cell.cell_type).filter_by(dataset_id=dataset_id).order_by(Cell.cell_index).all()
    if not cells:
        raise ValueError("无细胞信息")

    usable_count = min(len(cells), coords.shape[0])
    cells = cells[:usable_count]
    coords = coords[:usable_count, :]

    cell_indices = [c.cell_index for c in cells]
    cell_types = [c.cell_type or "未知" for c in cells]
    color_map = _build_color_map(cell_types, use_dark_cycle=True)
    pos_by_cell_index = {ci: i for i, ci in enumerate(cell_indices)}

    result_set = set([ci for ci in result_cell_indices if ci in pos_by_cell_index])
    query_pos = pos_by_cell_index.get(query_cell_index)
    if query_pos is None:
        raise ValueError("查询细胞不在数据集中")

    # 背景点
    background_positions = [i for i, ci in enumerate(cell_indices) if ci != query_cell_index and ci not in result_set]
    if len(background_positions) > max_background_points:
        rng = np.random.default_rng(seed=dataset_id)
        background_positions = sorted(rng.choice(background_positions, size=max_background_points, replace=False).tolist())

    bg_df = pd.DataFrame({
        "x": coords[background_positions, 0],
        "y": coords[background_positions, 1],
        "cell_type": [cell_types[i] for i in background_positions],
        "cell_index": [cell_indices[i] for i in background_positions],
    })

    # 背景低亮 PX
    muted_color_map = {ct: _muted_color(color) for ct, color in color_map.items()}
    fig = px.scatter(
        bg_df,
        x="x", y="y",
        color="cell_type",
        color_discrete_map=muted_color_map,
        custom_data=["cell_index", "cell_type"],
        render_mode="webgl",
    )
    fig.update_traces(marker=dict(size=3, opacity=0.92), hovertemplate="cell_type: %{customdata[1]}<br>cell_index: %{customdata[0]}<extra></extra>")

    # 结果点高亮
    result_positions = [pos_by_cell_index[ci] for ci in result_set if ci != query_cell_index]
    if result_positions:
        result_info_rows = db.session.query(Cell.cell_index, Cell.cell_name, Cell.cell_type, Cell.disease, Cell.age_group)\
            .filter(Cell.dataset_id == dataset_id, Cell.cell_index.in_([cell_indices[i] for i in result_positions])).all()
        result_info_map = {r.cell_index: r for r in result_info_rows}

        result_x, result_y, result_customdata = [], [], []
        for pos in result_positions:
            ci = cell_indices[pos]
            row = result_info_map.get(ci)
            if not row: continue
            result_x.append(float(coords[pos, 0]))
            result_y.append(float(coords[pos, 1]))
            result_customdata.append([row.cell_index, row.cell_name or "N/A", row.cell_type or "未知", row.disease or "N/A", row.age_group or "N/A"])

        if result_x:
            fig.add_trace(go.Scattergl(
                x=result_x, y=result_y,
                mode="markers",
                marker=dict(size=8, color="#0891b2", opacity=0.98, line=dict(width=1.4, color="#ffffff")),
                name="相似细胞",
                customdata=result_customdata,
                hovertemplate="cell_index: %{customdata[0]}<br>cell_name: %{customdata[1]}<br>cell_type: %{customdata[2]}<br>disease: %{customdata[3]}<br>age_group: %{customdata[4]}<extra></extra>",
            ))

    # 查询点星形突出
    query_info = db.session.query(Cell.cell_index, Cell.cell_name, Cell.cell_type, Cell.disease, Cell.age_group)\
        .filter(Cell.dataset_id == dataset_id, Cell.cell_index == query_cell_index).first()
    query_customdata = [[
        query_info.cell_index if query_info else query_cell_index,
        query_info.cell_name if query_info and query_info.cell_name else "N/A",
        query_info.cell_type if query_info and query_info.cell_type else "未知",
        query_info.disease if query_info and query_info.disease else "N/A",
        query_info.age_group if query_info and query_info.age_group else "N/A"
    ]]
    fig.add_trace(go.Scattergl(
        x=[float(coords[query_pos, 0])], y=[float(coords[query_pos, 1])],
        mode="markers",
        marker=dict(size=16, color="#d97706", symbol="star", line=dict(width=2.4, color="#ffffff"), opacity=1.0),
        name="查询细胞",
        customdata=query_customdata,
        hovertemplate="查询细胞<br>cell_index: %{customdata[0]}<br>cell_name: %{customdata[1]}<br>cell_type: %{customdata[2]}<br>disease: %{customdata[3]}<br>age_group: %{customdata[4]}<extra></extra>",
    ))

    _apply_dark_layout(fig, title=f"检索结果高亮 · {coord_label} 视图", xaxis_title=f"{coord_label}1", yaxis_title=f"{coord_label}2", height=640)
    return _fig_to_plotly_json(fig)


# ------------------ 检索性能柱状图 ------------------
def eval_bar_json(metrics: dict) -> dict:
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
            text=(f"Recall@{metrics.get('top_k', 'K')}: {metrics['avg_recall_at_k']:.2%}  |  加速比: {metrics['speedup']:.1f}x"),
            xref="paper", yref="paper", x=0.5, y=1.08, showarrow=False, font=dict(size=14),
        )],
    )
    return _fig_to_plotly_json(fig)
