"""Developer-only live quality loop for the global assistant.

This script never creates product conversations or executes tools. It loads an
enabled provider credential through the existing encrypted configuration, calls
one selected model, and stores only sanitized decisions under an ignored path.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import json
import math
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import create_app
from app.ai.prompts import ASSISTANT_EXAMPLES, GLOBAL_ASSISTANT_SYSTEM, PLATFORM_INVARIANTS, PROMPT_REVISION
from app.ai.schemas import AssistantTurnDecision
from app.ai.service import configured_provider
from app.models import AiModelConfig, AiProviderConfig
from app.ai.tools import write_tool_contracts


RAW_DIR = ROOT / "reports" / "ai-eval" / "raw"
CASES_PATH = ROOT / "scripts" / "ai_quality_cases.json"
PROVIDER_ORDER = ["qwen", "deepseek", "zhipu"]
MODEL_LADDERS = {
    "qwen": ["qwen3.7-plus", "qwen3.7-max"],
    "deepseek": ["deepseek-v4-flash", "deepseek-v4-pro"],
    "zhipu": ["glm-4.7"],
}


def _load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _budget_path() -> Path:
    return RAW_DIR / "budget.json"


def _completion_tokens(raw: str, reported: int) -> int:
    return max(int(reported or 0), math.ceil(len(raw or "") / 2))


def _chinese_dominant(text: str) -> bool:
    sentences = [part for part in re.split(r"[。！？.!?]+", text or "") if part.strip()]
    return bool(sentences) and sum(bool(re.search(r"[\u4e00-\u9fff]", part)) for part in sentences) / len(sentences) >= 0.6


def _score(case: dict, value: AssistantTurnDecision) -> dict:
    failures = []
    if value.intent != case["intent"]:
        failures.append(f"intent:{value.intent}!={case['intent']}")
    if case.get("target") and value.navigation_target != case["target"]:
        failures.append(f"target:{value.navigation_target}!={case['target']}")
    if case.get("action") and value.action != case["action"]:
        failures.append(f"action:{value.action}!={case['action']}")
    if value.action:
        contract = write_tool_contracts().get(value.action, {})
        missing = [key for key in contract.get("required", []) if value.action_args.get(key) is None]
        if missing:
            failures.append("missing_action_args:" + ",".join(missing))
    if case.get("forbidden_action") and value.action is not None:
        failures.append("forbidden_action_proposed")
    natural = value.direct_answer or value.clarification_question or ""
    if not _chinese_dominant(natural):
        failures.append("not_chinese_dominant")
    if value.intent == "propose_action" and re.search(r"(?:已经|已为你|成功)(?:执行|删除|修改|提交)", natural):
        failures.append("claims_unapproved_execution")
    if case.get("must_include") and not all(item in natural for item in case["must_include"]):
        failures.append("missing_required_text")
    if case.get("must_include_any") and not any(item in natural for item in case["must_include_any"]):
        failures.append("missing_required_semantics")
    if case.get("must_not_include") and any(item in natural for item in case["must_not_include"]):
        failures.append("contains_forbidden_text")
    return {"passed": not failures, "failures": failures}


def _synthetic_resources(case: dict) -> dict:
    first_status = case.get("dataset_status") or "indexed"
    return {
        "page": case.get("page") or {"path": "/overview", "name": "overview", "resources": {}},
        "datasets": [
            {"id": 1, "name": "demo_liver", "status": first_status, "role": "owner", "n_cells": 1000,
             "ready_indexes": [] if first_status != "indexed" else [{"id": 3, "algorithm": "hnswlib_hnsw", "metric": "l2"}]},
            {"id": 2, "name": "demo_pbmc", "status": "indexed", "role": "editor", "n_cells": 800,
             "ready_indexes": [{"id": 5, "algorithm": "hnswlib_hnsw", "metric": "cosine"}]},
        ],
        "joint_indexes": [{"id": 2, "name": "liver-pbmc", "status": "ready", "dataset_ids": [1, 2]}],
        "recent_tasks": [{"id": 8, "type": "build_index", "status": "running", "progress": 65, "dataset_id": 1}],
        "evidence": {"dataset_count": 2, "ready_index_count": 2, "active_task_count": 1},
        "user": {"id": 7, "username": "researcher", "system_role": "user"},
    }


def _select_model(provider_name: str, model_id: str | None):
    query = AiModelConfig.query.join(AiProviderConfig).filter(
        AiProviderConfig.provider == provider_name,
        AiProviderConfig.enabled.is_(True),
        AiModelConfig.capability == "chat",
        AiModelConfig.enabled.is_(True),
        AiModelConfig.last_test_status == "success",
    )
    model = query.filter(AiModelConfig.model_id == model_id).first() if model_id else query.filter(AiModelConfig.is_default.is_(True)).first()
    model = model or query.order_by(AiModelConfig.id.asc()).first()
    if not model:
        raise RuntimeError(f"没有已测试并启用的 {provider_name} Chat 模型。")
    return model


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", choices=PROVIDER_ORDER, default="qwen")
    parser.add_argument("--model-id")
    parser.add_argument("--case", action="append", dest="case_ids")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--max-output-tokens", type=int, default=1_000_000)
    parser.add_argument("--unseen", action="store_true", help="Skip case IDs already recorded for this provider")
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args()

    cases = _load_json(CASES_PATH, [])
    if args.case_ids:
        cases = [case for case in cases if case["id"] in set(args.case_ids)]
    if args.unseen:
        seen = set()
        for report in RAW_DIR.glob(f"*-{args.provider}.json") if RAW_DIR.exists() else []:
            for row in _load_json(report, {}).get("results", []):
                seen.add(row.get("case_id"))
        cases = [case for case in cases if case["id"] not in seen]
    if args.limit:
        cases = cases[:max(0, args.limit)]
    if args.list:
        print("\n".join(case["id"] for case in cases))
        return 0

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    budget = _load_json(_budget_path(), {})
    provider_budget = budget.setdefault(args.provider, {"output_tokens": 0, "calls": 0})
    app = create_app()
    results = []
    with app.app_context():
        model = _select_model(args.provider, args.model_id)
        provider = configured_provider(model)
        for case in cases:
            if provider_budget["output_tokens"] >= args.max_output_tokens:
                break
            resources = _synthetic_resources(case)
            messages = [
                {"role": "system", "content": GLOBAL_ASSISTANT_SYSTEM},
                {"role": "system", "content": ASSISTANT_EXAMPLES},
                {"role": "system", "content": PLATFORM_INVARIANTS},
                {"role": "system", "content": "实时平台上下文：" + json.dumps(resources, ensure_ascii=False)},
                {"role": "system", "content": "最近对话：" + json.dumps(case.get("dialogue") or [], ensure_ascii=False)},
                {"role": "system", "content": "可引用知识：" + json.dumps(case.get("knowledge") or [], ensure_ascii=False)},
                {"role": "system", "content": "安全写操作参数契约：" + json.dumps(write_tool_contracts(), ensure_ascii=False)},
                {"role": "user", "content": case["prompt"]},
            ]
            try:
                completion = provider.complete_structured(
                    model=args.model_id or model.model_id, messages=messages,
                    schema_model=AssistantTurnDecision, max_tokens=1400,
                )
                used = _completion_tokens(completion.raw_text, completion.usage.output_tokens)
                provider_budget["output_tokens"] += used
                provider_budget["calls"] += completion.usage.requests
                result = {
                    "case_id": case["id"], "provider": args.provider,
                    "model_id": args.model_id or model.model_id, "prompt_revision": PROMPT_REVISION,
                    "decision": completion.value.model_dump(), "score": _score(case, completion.value),
                    "usage": {"input_tokens": completion.usage.input_tokens, "output_tokens": used,
                              "requests": completion.usage.requests, "latency_ms": completion.usage.latency_ms},
                }
            except Exception as exc:
                provider_budget["calls"] += int(getattr(getattr(exc, "usage", None), "requests", 1) or 1)
                result = {"case_id": case["id"], "provider": args.provider,
                          "model_id": args.model_id or model.model_id,
                          "score": {"passed": False, "failures": [f"provider_error:{exc.__class__.__name__}"]}}
            results.append(result)
            _budget_path().write_text(json.dumps(budget, ensure_ascii=False, indent=2), encoding="utf-8")

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    output = RAW_DIR / f"{timestamp}-{args.provider}.json"
    output.write_text(json.dumps({"results": results, "budget": budget}, ensure_ascii=False, indent=2), encoding="utf-8")
    passed = sum(row["score"]["passed"] for row in results)
    print(json.dumps({"provider": args.provider, "model": args.model_id or model.model_id,
                      "cases": len(results), "passed": passed, "failed": len(results) - passed,
                      "output_tokens_total": provider_budget["output_tokens"], "report": str(output)}, ensure_ascii=False))
    return 0 if passed == len(results) else 2


if __name__ == "__main__":
    raise SystemExit(main())
