"""Strict application schemas for AI-produced plans and grounded summaries."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class SearchPlan(BaseModel):
    model_config = ConfigDict(extra="ignore")

    intent: Literal["single_cell_search"] = "single_cell_search"
    dataset_reference: str | int | None = None
    query_cell_index: int | None = Field(default=None, ge=0)
    top_k: int = Field(default=10, ge=1, le=100)
    filter_cell_type: str | None = None
    index_reference: str | int | None = None
    index_policy: Literal["explicit", "best_balanced", "latest_ready"] = "best_balanced"
    analysis_dimensions: list[Literal["distance", "cell_type", "disease", "age_group"]] = Field(
        default_factory=lambda: ["distance", "cell_type", "disease", "age_group"]
    )


PlanFieldName = Literal[
    "dataset_reference",
    "query_cell_index",
    "top_k",
    "filter_cell_type",
    "index_reference",
    "index_policy",
    "analysis_dimensions",
    "mode",
    "target_dataset_references",
    "joint_index_reference",
]


class AiTurnDecision(BaseModel):
    """One lightweight decision for either a search plan or a result follow-up."""

    model_config = ConfigDict(extra="ignore")

    intent: Literal[
        "analysis_request", "single_cell_search", "result_follow_up", "knowledge_question"
    ] = "analysis_request"
    operation: Literal["new_search", "refine_previous"] = "new_search"
    provided_fields: list[PlanFieldName] = Field(default_factory=list)
    dataset_reference: str | int | None = None
    query_cell_index: int | None = Field(default=None, ge=0)
    top_k: int | None = Field(default=None, ge=1, le=100)
    filter_cell_type: str | None = None
    index_reference: str | int | None = None
    index_policy: Literal["explicit", "best_balanced", "latest_ready"] | None = None
    analysis_dimensions: list[Literal["distance", "cell_type", "disease", "age_group"]] | None = None
    mode: Literal["auto", "single", "fanout", "joint"] = "auto"
    target_dataset_references: list[str | int] = Field(default_factory=list, max_length=20)
    joint_index_reference: str | int | None = None
    knowledge_scopes: list[Literal["platform", "dataset", "personal"]] = Field(
        default_factory=lambda: ["platform", "dataset", "personal"]
    )
    response_language: str = Field(default="zh-CN", max_length=20)
    goal: str = Field(default="", max_length=500)
    follow_up_dimensions: list[Literal["distance", "cell_type", "disease", "age_group"]] = Field(
        default_factory=list
    )


class AnalysisStep(BaseModel):
    model_config = ConfigDict(extra="ignore")

    tool: Literal[
        "get_dataset_profile", "retrieve_knowledge", "run_single_cell_search",
        "run_fanout_search", "run_joint_search", "compare_result_sets", "build_evidence_report",
    ]
    selection_mode: Literal["auto", "explicit"] = "explicit"
    dataset_reference: str | int | None = None
    dataset_id: int | None = None
    dataset_name: str | None = None
    index_reference: str | int | None = None
    index_id: int | None = None
    joint_index_reference: str | int | None = None
    joint_index_id: int | None = None
    query_cell_index: int | None = Field(default=None, ge=0)
    top_k: int = Field(default=10, ge=1, le=100)
    filter_cell_type: str | None = None
    target_dataset_references: list[str | int] = Field(default_factory=list, max_length=20)
    target_dataset_ids: list[int] = Field(default_factory=list, max_length=20)
    analysis_dimensions: list[Literal["distance", "cell_type", "disease", "age_group", "dataset"]] = Field(
        default_factory=lambda: ["distance", "cell_type", "disease", "age_group", "dataset"]
    )
    validation_errors: list[str] = Field(default_factory=list)


class AnalysisPlan(BaseModel):
    model_config = ConfigDict(extra="ignore")

    intent: Literal["analysis_request"] = "analysis_request"
    goal: str = Field(default="单细胞相似性分析", max_length=500)
    response_language: str = Field(default="zh-CN", max_length=20)
    knowledge_scopes: list[Literal["platform", "dataset", "personal"]] = Field(
        default_factory=lambda: ["platform", "dataset", "personal"]
    )
    steps: list[AnalysisStep] = Field(min_length=1, max_length=4)
    expected_outputs: list[str] = Field(default_factory=lambda: ["evidence_report"], max_length=8)
    validation_errors: list[str] = Field(default_factory=list)


class AnalysisFinding(BaseModel):
    model_config = ConfigDict(extra="ignore")

    statement: str = Field(min_length=1, max_length=300)
    evidence_keys: list[str] = Field(min_length=1, max_length=6)


class AnalysisSummary(BaseModel):
    model_config = ConfigDict(extra="ignore")

    headline: str = Field(min_length=1, max_length=120)
    summary: str = Field(min_length=1, max_length=800)
    findings: list[AnalysisFinding] = Field(default_factory=list, max_length=8)
    caveats: list[str] = Field(default_factory=list, max_length=6)
    next_actions: list[str] = Field(default_factory=list, max_length=6)
