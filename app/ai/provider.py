"""OpenAI-compatible provider client with structured-output fallbacks."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Callable, TypeVar

from pydantic import BaseModel, ValidationError


T = TypeVar("T", bound=BaseModel)


@dataclass
class ProviderUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    requests: int = 0
    latency_ms: float = 0.0

    def add(self, other: "ProviderUsage") -> None:
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.requests += other.requests
        self.latency_ms += other.latency_ms


class ProviderRequestError(RuntimeError):
    """Provider failure carrying request accounting without exposing credentials."""

    def __init__(self, message: str, usage: ProviderUsage):
        super().__init__(message)
        self.usage = usage


@dataclass
class StructuredCompletion:
    value: BaseModel
    raw_text: str
    usage: ProviderUsage


@dataclass
class EmbeddingCompletion:
    vectors: list[list[float]]
    dimensions: int
    usage: ProviderUsage


def _default_client_factory(**kwargs):
    from openai import OpenAI
    return OpenAI(**kwargs)


CLIENT_FACTORY = _default_client_factory


def _strict_schema(schema: dict) -> dict:
    result = json.loads(json.dumps(schema))

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            node.pop("default", None)
            if "const" in node and "enum" not in node:
                node["enum"] = [node.pop("const")]
            if node.get("type") == "object" or "properties" in node:
                properties = node.get("properties", {})
                node["additionalProperties"] = False
                node["required"] = list(properties.keys())
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)

    visit(result)
    return result


def _extract_json(text: str) -> dict:
    value = (text or "").strip()
    if value.startswith("```"):
        lines = value.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        value = "\n".join(lines).strip()
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        start = value.find("{")
        end = value.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("模型未返回 JSON 对象。")
        parsed = json.loads(value[start:end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("模型 JSON 顶层必须是对象。")
    return parsed


def _response_content(response) -> tuple[str, dict]:
    if not getattr(response, "choices", None):
        return "", {"finish_reason": None, "reasoning_content_length": 0}
    choice = response.choices[0]
    message = choice.message
    content = message.content
    if isinstance(content, str):
        text = content
    elif isinstance(content, list):
        text = "".join(str(getattr(part, "text", part)) for part in content)
    else:
        text = str(content or "")
    reasoning = getattr(message, "reasoning_content", None) or ""
    return text, {
        "finish_reason": getattr(choice, "finish_reason", None),
        "reasoning_content_length": len(reasoning),
    }


def _usage_from(response, elapsed_ms: float) -> ProviderUsage:
    usage = getattr(response, "usage", None)
    return ProviderUsage(
        input_tokens=int(getattr(usage, "prompt_tokens", 0) or 0),
        output_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
        requests=1,
        latency_ms=elapsed_ms,
    )


def _is_format_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(token in text for token in (
        "response_format", "json_schema", "unsupported parameter", "unknown parameter", "invalid parameter"
    ))


def _is_transient_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(token in text for token in (
        "timeout", "timed out", "connection", "temporarily", "rate limit", "429",
        "500", "502", "503", "504",
    ))


class OpenAICompatibleProvider:
    def __init__(self, *, provider: str, base_url: str, api_key: str, timeout_seconds: int = 180):
        self.provider = provider
        self.client = CLIENT_FACTORY(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout_seconds,
            max_retries=0,
        )

    def _create(self, *, model: str, messages: list[dict], max_tokens: int, response_format=None):
        kwargs = {
            "model": model,
            "messages": messages,
            "temperature": 0.1,
            "max_tokens": max_tokens,
            "stream": False,
        }
        if response_format is not None:
            kwargs["response_format"] = response_format
        started = time.perf_counter()
        attempts = 0
        while True:
            attempts += 1
            try:
                response = self.client.chat.completions.create(**kwargs)
                break
            except Exception as exc:
                if attempts == 1 and _is_transient_error(exc):
                    time.sleep(0.5)
                    continue
                elapsed = (time.perf_counter() - started) * 1000
                raise ProviderRequestError(
                    str(exc), ProviderUsage(requests=attempts, latency_ms=elapsed)
                ) from exc
        elapsed = (time.perf_counter() - started) * 1000
        text, metadata = _response_content(response)
        usage = _usage_from(response, elapsed)
        usage.requests = attempts
        return text, usage, metadata

    def test_connection(self, model: str) -> ProviderUsage:
        text, usage, metadata = self._create(
            model=model,
            messages=[{"role": "user", "content": "Reply with exactly OK."}],
            max_tokens=128,
        )
        if (
            not text.strip()
            and metadata.get("finish_reason") == "length"
            and metadata.get("reasoning_content_length", 0) > 0
        ):
            retry_text, retry_usage, _ = self._create(
                model=model,
                messages=[{"role": "user", "content": "Reply with exactly OK."}],
                max_tokens=256,
            )
            usage.add(retry_usage)
            text = retry_text
        if not text.strip():
            raise ValueError("模型连接成功但未返回内容。")
        return usage

    def embed_texts(self, *, model: str, texts: list[str]) -> EmbeddingCompletion:
        clean = [str(item or "").strip() for item in texts]
        if not clean or any(not item for item in clean):
            raise ValueError("嵌入输入不能为空。")
        started = time.perf_counter()
        attempts = 0
        while True:
            attempts += 1
            try:
                response = self.client.embeddings.create(model=model, input=clean, encoding_format="float")
                break
            except Exception as exc:
                if attempts == 1 and _is_transient_error(exc):
                    time.sleep(0.5)
                    continue
                elapsed = (time.perf_counter() - started) * 1000
                raise ProviderRequestError(
                    str(exc), ProviderUsage(requests=attempts, latency_ms=elapsed)
                ) from exc
        elapsed = (time.perf_counter() - started) * 1000
        ordered = sorted(response.data, key=lambda item: int(getattr(item, "index", 0)))
        vectors = [list(map(float, getattr(item, "embedding", []) or [])) for item in ordered]
        if len(vectors) != len(clean) or not vectors or not vectors[0]:
            raise ValueError("嵌入接口未返回有效向量。")
        dimensions = len(vectors[0])
        if any(len(vector) != dimensions for vector in vectors):
            raise ValueError("嵌入接口返回了不一致的向量维度。")
        usage_obj = getattr(response, "usage", None)
        usage = ProviderUsage(
            input_tokens=int(
                getattr(usage_obj, "prompt_tokens", None)
                or getattr(usage_obj, "total_tokens", 0)
                or 0
            ),
            requests=attempts,
            latency_ms=elapsed,
        )
        return EmbeddingCompletion(vectors=vectors, dimensions=dimensions, usage=usage)

    def test_embedding(self, model: str) -> EmbeddingCompletion:
        return self.embed_texts(model=model, texts=["单细胞相似性检索测试"])

    def complete_text_stream(
        self,
        *,
        model: str,
        messages: list[dict],
        max_tokens: int,
        on_delta: Callable[[str], None],
    ) -> tuple[str, ProviderUsage]:
        """Stream qualitative text while keeping provider details behind one adapter."""
        started = time.perf_counter()
        try:
            stream = self.client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.1,
                max_tokens=max_tokens,
                stream=True,
            )
            parts: list[str] = []
            for chunk in stream:
                choices = getattr(chunk, "choices", None) or []
                if not choices:
                    continue
                delta = getattr(choices[0], "delta", None)
                content = getattr(delta, "content", None) if delta is not None else None
                if isinstance(content, str) and content:
                    parts.append(content)
                    on_delta(content)
        except Exception as exc:
            elapsed = (time.perf_counter() - started) * 1000
            raise ProviderRequestError(
                str(exc), ProviderUsage(requests=1, latency_ms=elapsed)
            ) from exc
        return "".join(parts), ProviderUsage(
            requests=1,
            latency_ms=(time.perf_counter() - started) * 1000,
        )

    def complete_structured(
        self,
        *,
        model: str,
        messages: list[dict],
        schema_model: type[T],
        max_tokens: int,
    ) -> StructuredCompletion:
        schema = _strict_schema(schema_model.model_json_schema())
        schema_name = schema_model.__name__.lower()
        json_instruction = (
            "Return only one JSON object matching this JSON Schema. Do not use markdown fences:\n"
            + json.dumps(schema, ensure_ascii=False)
        )
        structured_messages = [*messages, {"role": "system", "content": json_instruction}]
        if self.provider == "openai":
            response_format = {
                "type": "json_schema",
                "json_schema": {"name": schema_name, "strict": True, "schema": schema},
            }
        elif self.provider in {"deepseek", "zhipu", "qwen"}:
            response_format = {"type": "json_object"}
        else:
            response_format = None

        total = ProviderUsage()
        try:
            raw, usage, _ = self._create(
                model=model,
                messages=structured_messages,
                max_tokens=max_tokens,
                response_format=response_format,
            )
            total.add(usage)
        except Exception as exc:
            exc_usage = getattr(exc, "usage", None)
            if exc_usage:
                total.add(exc_usage)
            if response_format is None or not _is_format_error(exc):
                if hasattr(exc, "usage"):
                    exc.usage = total
                raise
            try:
                raw, usage, _ = self._create(
                    model=model,
                    messages=structured_messages,
                    max_tokens=max_tokens,
                    response_format=None,
                )
            except Exception as fallback_exc:
                fallback_usage = getattr(fallback_exc, "usage", None)
                if fallback_usage:
                    total.add(fallback_usage)
                    fallback_exc.usage = total
                raise
            total.add(usage)

        try:
            value = schema_model.model_validate(_extract_json(raw))
            return StructuredCompletion(value=value, raw_text=raw, usage=total)
        except (ValueError, ValidationError, json.JSONDecodeError) as first_error:
            repair_messages = [
                *structured_messages,
                {"role": "assistant", "content": raw},
                {
                    "role": "user",
                    "content": f"The JSON was invalid ({first_error}). Return one corrected JSON object only.",
                },
            ]
            try:
                repaired, usage, _ = self._create(
                    model=model,
                    messages=repair_messages,
                    max_tokens=max_tokens,
                    response_format=None,
                )
            except Exception as repair_exc:
                repair_usage = getattr(repair_exc, "usage", None)
                if repair_usage:
                    total.add(repair_usage)
                    repair_exc.usage = total
                raise
            total.add(usage)
            value = schema_model.model_validate(_extract_json(repaired))
            return StructuredCompletion(value=value, raw_text=repaired, usage=total)
