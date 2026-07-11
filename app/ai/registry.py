"""Static provider metadata; model IDs remain editable administrator suggestions."""
from __future__ import annotations


PROVIDER_CATALOG = {
    "openai": {
        "label": "OpenAI",
        "default_base_url": "https://api.openai.com/v1",
        "base_url_options": [],
        "suggested_models": ["gpt-4.1-mini", "gpt-4.1"],
        "suggested_embedding_models": ["text-embedding-3-small", "text-embedding-3-large"],
    },
    "deepseek": {
        "label": "DeepSeek",
        "default_base_url": "https://api.deepseek.com",
        "base_url_options": [],
        "suggested_models": ["deepseek-v4-flash", "deepseek-v4-pro"],
        "suggested_embedding_models": [],
    },
    "zhipu": {
        "label": "智谱 AI",
        "default_base_url": "https://open.bigmodel.cn/api/paas/v4/",
        "base_url_options": [],
        "suggested_models": ["glm-5.2", "glm-4.7-flash"],
        "suggested_embedding_models": ["embedding-3", "embedding-2"],
    },
    "qwen": {
        "label": "Qwen / 阿里云百炼",
        "default_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "base_url_options": [
            {
                "label": "中国区公共 Endpoint",
                "value": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            },
            {
                "label": "国际区公共 Endpoint",
                "value": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
            },
        ],
        "suggested_models": ["qwen3.7-plus", "qwen3.6-flash"],
        "suggested_embedding_models": ["text-embedding-v4", "text-embedding-v3"],
    },
    "custom": {
        "label": "自定义 OpenAI-compatible",
        "default_base_url": "",
        "base_url_options": [],
        "suggested_models": [],
        "suggested_embedding_models": [],
    },
}


def provider_catalog() -> list[dict]:
    return [{"key": key, **value} for key, value in PROVIDER_CATALOG.items()]


def provider_definition(provider: str) -> dict:
    key = (provider or "").strip().lower()
    if key not in PROVIDER_CATALOG:
        raise ValueError("不支持的模型供应商。")
    return PROVIDER_CATALOG[key]


def default_base_url(provider: str) -> str:
    return str(provider_definition(provider)["default_base_url"])
