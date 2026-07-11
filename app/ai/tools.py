"""Single source of truth for analysis, navigation, and approved AI tools."""
from __future__ import annotations


TOOL_REGISTRY = {
    "list_accessible_datasets": {
        "label": "列出可访问数据集", "description": "读取当前用户可查看的数据集与状态。",
        "requires_confirmation": False, "kind": "context", "risk_level": "read",
    },
    "get_dataset_status": {
        "label": "读取数据集状态", "description": "读取一个有权访问的数据集概况和处理状态。",
        "requires_confirmation": False, "kind": "context", "risk_level": "read",
    },
    "list_ready_indexes": {
        "label": "列出可用索引", "description": "读取数据集 ready/active 索引。",
        "requires_confirmation": False, "kind": "context", "risk_level": "read",
    },
    "get_index_details": {
        "label": "读取索引详情", "description": "读取索引算法、状态、指标和参数。",
        "requires_confirmation": False, "kind": "context", "risk_level": "read",
    },
    "list_joint_indexes": {
        "label": "列出联合索引", "description": "读取当前用户可使用的联合索引。",
        "requires_confirmation": False, "kind": "context", "risk_level": "read",
    },
    "get_task_status": {
        "label": "读取任务状态", "description": "读取当前用户有权查看的后台任务。",
        "requires_confirmation": False, "kind": "context", "risk_level": "read",
    },
    "get_user_capabilities": {
        "label": "读取当前权限", "description": "读取当前账号和数据集级能力，不扩大权限。",
        "requires_confirmation": False, "kind": "context", "risk_level": "read",
    },
    "get_dataset_profile": {
        "label": "读取数据集概况",
        "description": "读取细胞数、基因数和元数据分布，不执行 ANN。",
        "requires_confirmation": False,
        "kind": "context",
        "risk_level": "read",
    },
    "retrieve_knowledge": {
        "label": "检索知识库",
        "description": "从平台、数据集和个人知识空间检索可引用资料。",
        "requires_confirmation": False,
        "kind": "knowledge",
        "risk_level": "read",
    },
    "run_single_cell_search": {
        "label": "单数据集 ANN 检索",
        "description": "在一个数据集的 ready/active 索引中检索相似细胞。",
        "requires_confirmation": True,
        "kind": "ann",
        "risk_level": "analysis",
    },
    "run_fanout_search": {
        "label": "跨数据集 Fan-out 检索",
        "description": "使用兼容的独立索引检索多个可访问数据集并合并排序。",
        "requires_confirmation": True,
        "kind": "ann",
        "risk_level": "analysis",
    },
    "run_joint_search": {
        "label": "联合索引检索",
        "description": "在 ready 的 Harmony 联合空间中执行跨数据集检索。",
        "requires_confirmation": True,
        "kind": "ann",
        "risk_level": "analysis",
    },
    "compare_result_sets": {
        "label": "比较结果集",
        "description": "确定性比较已完成结果的分布和重叠，不新增 ANN 调用。",
        "requires_confirmation": False,
        "kind": "analysis",
        "risk_level": "read",
    },
    "build_evidence_report": {
        "label": "生成证据报告",
        "description": "用后端证据和知识引用生成可追溯报告。",
        "requires_confirmation": False,
        "kind": "analysis",
        "risk_level": "read",
    },
}


CLIENT_ACTIONS = {
    "open_page": "打开受控平台页面。",
    "open_dataset": "打开有权访问的数据集详情。",
    "open_task": "打开当前用户可查看的任务。",
    "prefill_query_lab": "使用受控参数预填检索实验室。",
    "prefill_index_lab": "使用受控参数预填索引实验室。",
    "handoff_to_ai_analysis": "在当前 AI 助手会话启动科学分析执行器。",
}


WRITE_TOOLS = {
    "submit_dataset_processing": "提交数据集处理任务。",
    "submit_index_build": "提交单索引构建任务。",
    "submit_index_experiment": "提交索引实验任务。",
    "submit_index_evaluation": "提交索引评估任务。",
    "submit_joint_index_build": "提交联合索引构建任务。",
    "reindex_knowledge_document": "重建有权维护的知识文档索引。",
    "create_personal_knowledge_note": "创建一份当前用户私有的 Markdown 知识笔记。",
}

WRITE_TOOL_ARGUMENTS = {
    "submit_dataset_processing": {"required": ["dataset_id"], "optional": []},
    "submit_index_build": {"required": ["dataset_id"], "optional": ["algorithm", "metric", "M", "ef_construction", "ef_search", "params"]},
    "submit_index_experiment": {"required": ["dataset_id"], "optional": ["metric", "sample_size", "top_k", "seed", "repetitions", "warmup_count", "candidate_keys"]},
    "submit_index_evaluation": {"required": ["dataset_id", "index_id"], "optional": ["sample_size", "top_k", "seed"]},
    "submit_joint_index_build": {"required": ["dataset_ids"], "optional": ["name", "metric", "M", "ef_construction", "ef_search", "n_pcs", "n_top_genes", "min_common_genes"]},
    "reindex_knowledge_document": {"required": ["document_id"], "optional": []},
    "create_personal_knowledge_note": {"required": ["title", "content"], "optional": []},
}

WRITE_TOOL_LABELS = {
    "submit_dataset_processing": "处理数据集",
    "submit_index_build": "构建单索引",
    "submit_index_experiment": "运行索引实验",
    "submit_index_evaluation": "评估索引",
    "submit_joint_index_build": "构建联合索引",
    "reindex_knowledge_document": "重建知识索引",
    "create_personal_knowledge_note": "创建个人知识笔记",
}

for _name, _description in CLIENT_ACTIONS.items():
    TOOL_REGISTRY[_name] = {
        "label": _name.replace("_", " "), "description": _description,
        "requires_confirmation": False, "kind": "client", "risk_level": "navigation",
    }

for _name, _description in WRITE_TOOLS.items():
    TOOL_REGISTRY[_name] = {
        "label": WRITE_TOOL_LABELS[_name], "description": _description,
        "requires_confirmation": True, "kind": "write", "risk_level": "write",
        "arguments": WRITE_TOOL_ARGUMENTS[_name],
    }


def tool_catalog() -> list[dict]:
    return [{"name": name, **definition} for name, definition in TOOL_REGISTRY.items()]


def is_ann_tool(name: str) -> bool:
    return TOOL_REGISTRY.get(name, {}).get("kind") == "ann"


def is_write_tool(name: str) -> bool:
    return name in WRITE_TOOLS


def write_tool_contracts() -> dict:
    return {
        name: {"description": WRITE_TOOLS[name], **WRITE_TOOL_ARGUMENTS[name]}
        for name in WRITE_TOOLS
    }
