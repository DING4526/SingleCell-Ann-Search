"""Single source of truth for read-only AI analysis tools."""
from __future__ import annotations


TOOL_REGISTRY = {
    "get_dataset_profile": {
        "label": "读取数据集概况",
        "description": "读取细胞数、基因数和元数据分布，不执行 ANN。",
        "requires_confirmation": False,
        "kind": "context",
    },
    "retrieve_knowledge": {
        "label": "检索知识库",
        "description": "从平台、数据集和个人知识空间检索可引用资料。",
        "requires_confirmation": False,
        "kind": "knowledge",
    },
    "run_single_cell_search": {
        "label": "单数据集 ANN 检索",
        "description": "在一个数据集的 ready/active 索引中检索相似细胞。",
        "requires_confirmation": True,
        "kind": "ann",
    },
    "run_fanout_search": {
        "label": "跨数据集 Fan-out 检索",
        "description": "使用兼容的独立索引检索多个可访问数据集并合并排序。",
        "requires_confirmation": True,
        "kind": "ann",
    },
    "run_joint_search": {
        "label": "联合索引检索",
        "description": "在 ready 的 Harmony 联合空间中执行跨数据集检索。",
        "requires_confirmation": True,
        "kind": "ann",
    },
    "compare_result_sets": {
        "label": "比较结果集",
        "description": "确定性比较已完成结果的分布和重叠，不新增 ANN 调用。",
        "requires_confirmation": False,
        "kind": "analysis",
    },
    "build_evidence_report": {
        "label": "生成证据报告",
        "description": "用后端证据和知识引用生成可追溯报告。",
        "requires_confirmation": False,
        "kind": "analysis",
    },
}


def tool_catalog() -> list[dict]:
    return [{"name": name, **definition} for name, definition in TOOL_REGISTRY.items()]


def is_ann_tool(name: str) -> bool:
    return TOOL_REGISTRY.get(name, {}).get("kind") == "ann"

