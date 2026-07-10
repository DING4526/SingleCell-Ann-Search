"""AI provider governance, privacy, and confirmed-search workflow tests."""
import json
import os
import tempfile
from types import SimpleNamespace

from cryptography.fernet import Fernet


class _FakeCompletions:
    def __init__(self, calls, *, reject_format=False):
        self.calls = calls
        self.reject_format = reject_format

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.reject_format and kwargs.get("response_format"):
            raise ValueError("unsupported response_format")
        text = "\n".join(str(item.get("content", "")) for item in kwargs.get("messages", []))
        user_contents = [
            str(item.get("content", "")) for item in kwargs.get("messages", [])
            if item.get("role") == "user"
        ]
        last_content = user_contents[-1] if user_contents else ""
        if "Reply with exactly OK" in text:
            content = "OK"
        elif "这些结果的疾病分布" in last_content:
            content = json.dumps({
                "intent": "result_follow_up",
                "operation": "refine_previous",
                "provided_fields": [],
                "dataset_reference": None,
                "query_cell_index": None,
                "top_k": None,
                "filter_cell_type": None,
                "index_reference": None,
                "index_policy": None,
                "analysis_dimensions": None,
                "follow_up_dimensions": ["disease"],
            }, ensure_ascii=False)
        elif "再找与 1 号" in last_content:
            content = json.dumps({
                "intent": "single_cell_search",
                "operation": "refine_previous",
                "provided_fields": ["query_cell_index"],
                "dataset_reference": None,
                "query_cell_index": 1,
                "top_k": None,
                "filter_cell_type": None,
                "index_reference": None,
                "index_policy": None,
                "analysis_dimensions": None,
                "follow_up_dimensions": [],
            }, ensure_ascii=False)
        elif "检索结果解释器" in text:
            content = json.dumps({
                "headline": "相似细胞检索完成",
                "summary": "结果显示近邻组成具有明确的类型与分组特征。",
                "findings": [{"statement": "近邻类型构成可由证据验证。", "evidence_keys": ["cell_type_distribution"]}],
                "caveats": ["嵌入空间相似性不构成临床诊断。"],
                "next_actions": ["可在检索实验室查看完整结果。"],
            }, ensure_ascii=False)
        else:
            content = json.dumps({
                "intent": "single_cell_search",
                "dataset_reference": "study",
                "query_cell_index": 0,
                "top_k": 2,
                "filter_cell_type": None,
                "index_reference": None,
                "index_policy": "best_balanced",
                "analysis_dimensions": ["distance", "cell_type", "disease", "age_group"],
            }, ensure_ascii=False)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
            usage=SimpleNamespace(prompt_tokens=11, completion_tokens=7),
        )


class _FakeClient:
    def __init__(self, calls, *, reject_format=False):
        self.chat = SimpleNamespace(completions=_FakeCompletions(calls, reject_format=reject_format))


def _make_app(tmpdir, *, encryption_key=None):
    from app import create_app
    from app.config import Config

    class TestConfig(Config):
        TESTING = True
        SECRET_KEY = "ai-test-secret"
        SQLALCHEMY_DATABASE_URI = "sqlite:///" + os.path.join(tmpdir, "ai.db").replace("\\", "/")
        RAW_DIR = os.path.join(tmpdir, "raw")
        CACHE_DIR = os.path.join(tmpdir, "cache")
        INDEX_DIR = os.path.join(tmpdir, "indexes")
        AI_CREDENTIAL_ENCRYPTION_KEY = encryption_key or ""

    return create_app(TestConfig)


def _user(username, role="user"):
    from app.models import User
    row = User(username=username, role=role)
    row.set_password("pass1234")
    return row


def _login(client, username):
    return client.post("/api/auth/login", data={"username": username, "password": "pass1234"})


def test_admin_provider_and_confirmed_ai_search_workflow(monkeypatch):
    import app.ai.provider as provider_module
    import app.routes.ai as ai_routes
    import app.services.search_service as search_service
    import app.ai.service as ai_service
    from app.ai.service import run_execution, run_planning, run_summary_enhancement
    from app.extensions import db
    from app.models import AiProviderConfig, AiRun, AuditLog, Cell, Dataset, AnnIndex

    calls = []
    monkeypatch.setattr(provider_module, "CLIENT_FACTORY", lambda **kwargs: _FakeClient(calls))
    monkeypatch.setattr(ai_routes, "submit_planning", lambda *args: None)
    monkeypatch.setattr(ai_routes, "submit_execution", lambda *args: None)
    monkeypatch.setattr(ai_service, "submit_summary", lambda *args: None)
    search_calls = []

    def fake_search(**kwargs):
        search_calls.append(kwargs)
        results = [
            {"rank": 1, "cell_id": 1, "cell_index": 1, "cell_name": "c1", "distance": 0.1, "cell_type": "T", "disease": "normal", "age_group": "adult"},
            {"rank": 2, "cell_id": 2, "cell_index": 2, "cell_name": "c2", "distance": 0.2, "cell_type": "B", "disease": "disease", "age_group": "adult"},
        ]
        return {
            "result_data": {"results": results, "query_time_ms": 1.5, "query_cell_index": 0, "top_k": 2},
            "interpretation": {
                "distance_range": {"min": 0.1, "max": 0.2, "median": 0.15},
                "cell_type_distribution": {"T": 1, "B": 1},
                "disease_distribution": {"normal": 1, "disease": 1},
                "age_group_distribution": {"adult": 2},
                "result_count": 2,
                "same_type_count": 1,
                "same_type_fraction": 0.5,
                "query_cell_type": "T",
            },
            "scatter_plot": {"data": [], "layout": {"title": "AI test"}},
        }

    monkeypatch.setattr(search_service, "execute_single_search", fake_search)

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        app = _make_app(tmpdir, encryption_key=Fernet.generate_key().decode())
        with app.app_context():
            db.create_all()
            admin = _user("admin", "admin")
            researcher = _user("researcher")
            outsider = _user("outsider")
            db.session.add_all([admin, researcher, outsider])
            db.session.flush()
            dataset = Dataset(name="study", file_path="study.h5ad", owner_id=researcher.id, n_cells=3, status="indexed")
            db.session.add(dataset)
            db.session.flush()
            db.session.add_all([
                Cell(dataset_id=dataset.id, cell_index=0, cell_name="q", cell_type="T", disease="normal", age_group="adult"),
                Cell(dataset_id=dataset.id, cell_index=1, cell_name="c1", cell_type="T", disease="normal", age_group="adult"),
                Cell(dataset_id=dataset.id, cell_index=2, cell_name="c2", cell_type="B", disease="disease", age_group="adult"),
            ])
            db.session.add(AnnIndex(
                dataset_id=dataset.id, algorithm="hnswlib_hnsw", metric="cosine", index_path="fake.bin",
                status="ready", lifecycle="active", selection_labels="best_balanced",
            ))
            db.session.commit()
            researcher_id = researcher.id

        admin_client = app.test_client()
        user_client = app.test_client()
        outsider_client = app.test_client()
        assert _login(admin_client, "admin").status_code == 200
        secret = "sk-super-secret-value"
        created = admin_client.post("/api/ai/admin/providers", json={
            "provider": "openai", "name": "OpenAI shared", "api_key": secret,
            "base_url": "https://api.openai.com/v1",
        })
        assert created.status_code == 201
        provider_json = created.get_json()["provider"]
        assert secret not in json.dumps(provider_json)
        provider_id = provider_json["id"]
        model = admin_client.post("/api/ai/admin/models", json={
            "provider_config_id": provider_id, "model_id": "test-model", "display_name": "Test model",
        }).get_json()["model"]
        assert admin_client.post(f"/api/ai/admin/models/{model['id']}/test").status_code == 200
        assert admin_client.patch(f"/api/ai/admin/models/{model['id']}", json={"enabled": True}).status_code == 200

        with app.app_context():
            stored = db.session.get(AiProviderConfig, provider_id)
            assert secret not in stored.api_key_ciphertext

        assert _login(user_client, "researcher").status_code == 200
        assert len(user_client.get("/api/ai/models").get_json()["models"]) == 1
        conversation_id = user_client.post("/api/ai/conversations", json={}).get_json()["conversation"]["id"]
        submitted = user_client.post(f"/api/ai/conversations/{conversation_id}/messages", json={
            "content": "在 study 中查找与零号细胞最相似的两个细胞", "model_config_id": model["id"],
        })
        assert submitted.status_code == 202
        run_id = submitted.get_json()["run"]["id"]
        assert search_calls == []

        run_planning(app, run_id)
        planned = user_client.get(f"/api/ai/runs/{run_id}").get_json()["run"]
        assert planned["status"] == "awaiting_confirmation"
        assert planned["plan"]["dataset_id"]
        assert planned["stage"]["started_at"].endswith("Z")
        assert search_calls == []
        assert user_client.post(f"/api/ai/runs/{run_id}/approve").status_code == 202
        run_execution(app, run_id)
        completed = user_client.get(f"/api/ai/runs/{run_id}").get_json()["run"]
        assert completed["status"] == "success"
        assert completed["result"]["evidence"]["result_count"] == 2
        assert completed["result"]["summary"]["generated_by"] == "deterministic_fallback"
        assert completed["summary_status"] == "pending"
        assert completed["search_task_id"]
        assert search_calls[0]["include_plot"] is False
        run_summary_enhancement(app, run_id)
        enhanced = user_client.get(f"/api/ai/runs/{run_id}").get_json()["run"]
        assert enhanced["result"]["summary"]["generated_by"] == "model"
        assert enhanced["summary_status"] == "model"
        assert len(search_calls) == 1

        history = user_client.get("/api/search/history?source=ai").get_json()["history"]
        assert len(history) == 1
        assert history[0]["id"] == completed["search_task_id"]
        detail = user_client.get(f"/api/search/history/{history[0]['id']}").get_json()["history"]
        assert detail["request"]["index_id"] == planned["plan"]["index_id"]
        assert detail["result"]["result_data"]["results"]

        refined_message = user_client.post(f"/api/ai/conversations/{conversation_id}/messages", json={
            "content": "再找与 1 号最相似的细胞", "model_config_id": model["id"],
        })
        refined_id = refined_message.get_json()["run"]["id"]
        run_planning(app, refined_id)
        refined = user_client.get(f"/api/ai/runs/{refined_id}").get_json()["run"]
        assert refined["status"] == "awaiting_confirmation"
        assert refined["plan"]["dataset_id"] == planned["plan"]["dataset_id"]
        assert refined["plan"]["index_id"] == planned["plan"]["index_id"]
        assert refined["plan"]["query_cell_index"] == 1
        assert user_client.post(f"/api/ai/runs/{refined_id}/reject").status_code == 200

        followup_message = user_client.post(f"/api/ai/conversations/{conversation_id}/messages", json={
            "content": "这些结果的疾病分布如何？", "model_config_id": model["id"],
        })
        followup_id = followup_message.get_json()["run"]["id"]
        run_planning(app, followup_id)
        followup = user_client.get(f"/api/ai/runs/{followup_id}").get_json()["run"]
        assert followup["status"] == "success"
        assert followup["intent"] == "result_follow_up"
        assert followup["search_task_id"] == completed["search_task_id"]
        assert len(search_calls) == 1

        assert _login(outsider_client, "outsider").status_code == 200
        assert outsider_client.get(f"/api/ai/conversations/{conversation_id}").status_code == 404
        assert outsider_client.get(f"/api/search/history/{completed['search_task_id']}").status_code == 404
        usage = admin_client.get("/api/ai/admin/usage").get_json()["usage"]
        assert usage["totals"]["provider_requests"] >= 2
        assert "在 study" not in json.dumps(usage, ensure_ascii=False)
        with app.app_context():
            audit_text = " ".join(row.details_json or "" for row in AuditLog.query.all())
            assert secret not in audit_text
            assert db.session.get(AiRun, run_id).provider_request_count >= 2

        assert admin_client.patch("/api/ai/admin/settings", json={"daily_request_limit": 1}).status_code == 200
        second_conversation = user_client.post("/api/ai/conversations", json={}).get_json()["conversation"]["id"]
        limited = user_client.post(f"/api/ai/conversations/{second_conversation}/messages", json={
            "content": "再次执行检索", "model_config_id": model["id"],
        })
        assert limited.status_code == 403
        assert admin_client.patch(f"/api/access/users/{researcher_id}", data={"ai_enabled": "false"}).status_code == 200
        assert user_client.get("/api/ai/models").get_json()["models"] == []


def test_missing_encryption_key_and_custom_endpoint_protection():
    from app.extensions import db

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        app = _make_app(tmpdir)
        with app.app_context():
            db.create_all()
            db.session.add(_user("admin", "admin"))
            db.session.commit()
        client = app.test_client()
        assert _login(client, "admin").status_code == 200
        settings = client.get("/api/ai/admin/settings").get_json()
        assert settings["credential_store"]["ready"] is False
        missing = client.post("/api/ai/admin/providers", json={
            "provider": "openai", "api_key": "sk-valid-looking", "base_url": "https://api.openai.com/v1",
        })
        assert missing.status_code == 400
        blocked = client.post("/api/ai/admin/providers", json={
            "provider": "custom", "api_key": "sk-valid-looking", "base_url": "http://127.0.0.1:8000/v1",
        })
        assert blocked.status_code == 400


def test_json_mode_falls_back_when_compatible_provider_rejects_parameter(monkeypatch):
    import app.ai.provider as provider_module
    from app.ai.provider import OpenAICompatibleProvider
    from app.ai.schemas import SearchPlan

    calls = []
    monkeypatch.setattr(provider_module, "CLIENT_FACTORY", lambda **kwargs: _FakeClient(calls, reject_format=True))
    client = OpenAICompatibleProvider(provider="qwen", base_url="https://example.com/v1", api_key="test-key-value")
    result = client.complete_structured(
        model="qwen-test",
        messages=[{"role": "user", "content": "plan"}],
        schema_model=SearchPlan,
        max_tokens=500,
    )
    assert result.value.dataset_reference == "study"
    assert result.usage.requests == 2
    assert len(calls) == 2


def test_reasoning_model_connection_retries_with_larger_output_budget(monkeypatch):
    import app.ai.provider as provider_module
    from app.ai.provider import OpenAICompatibleProvider

    calls = []

    class Completions:
        def create(self, **kwargs):
            calls.append(kwargs)
            first = len(calls) == 1
            return SimpleNamespace(
                choices=[SimpleNamespace(
                    message=SimpleNamespace(
                        content="" if first else "OK",
                        reasoning_content="thinking" if first else "",
                    ),
                    finish_reason="length" if first else "stop",
                )],
                usage=SimpleNamespace(prompt_tokens=2, completion_tokens=kwargs["max_tokens"]),
            )

    monkeypatch.setattr(
        provider_module, "CLIENT_FACTORY",
        lambda **kwargs: SimpleNamespace(chat=SimpleNamespace(completions=Completions())),
    )
    provider = OpenAICompatibleProvider(
        provider="deepseek", base_url="https://api.deepseek.com", api_key="test-key"
    )
    usage = provider.test_connection("reasoning-model")
    assert [call["max_tokens"] for call in calls] == [128, 256]
    assert usage.requests == 2


def test_unified_search_history_modes_filters_and_soft_delete():
    from app.extensions import db
    from app.models import Dataset, Task

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        app = _make_app(tmpdir, encryption_key=Fernet.generate_key().decode())
        with app.app_context():
            db.create_all()
            owner = _user("owner")
            other = _user("other")
            db.session.add_all([owner, other])
            db.session.flush()
            dataset = Dataset(
                name="history-study", file_path="history.h5ad", owner_id=owner.id,
                n_cells=10, status="indexed",
            )
            db.session.add(dataset)
            db.session.flush()
            owner_id = owner.id
            dataset_id = dataset.id
            for task_type, mode, source in [
                ("search", "single", "query_lab"),
                ("multi_search", "multi", "query_lab"),
                ("joint_search", "joint", "ai"),
            ]:
                db.session.add(Task(
                    type=task_type, source=source, status="success", progress=100,
                    dataset_id=dataset.id, created_by_id=owner.id,
                    request_json=json.dumps({
                        "mode": mode, "dataset_id": dataset.id,
                        "query_dataset_id": dataset.id, "query_cell_index": 1, "top_k": 5,
                    }),
                    result_json=json.dumps({
                        "result_data": {
                            "results": [{"rank": 1, "cell_index": 2}],
                            "query_cell_index": 1, "top_k": 5, "query_time_ms": 0.5,
                        }
                    }),
                ))
            db.session.add(Task(
                type="search", source="query_lab", status="success", dataset_id=dataset.id,
                created_by_id=other.id, request_json="{}", result_json="{}",
            ))
            db.session.commit()

        client = app.test_client()
        assert _login(client, "owner").status_code == 200
        all_rows = client.get("/api/search/history").get_json()["history"]
        assert {row["mode"] for row in all_rows} == {"single", "multi", "joint"}
        assert all(row["dataset_id"] == dataset_id for row in all_rows)
        assert all(row.get("request") for row in all_rows)
        ai_rows = client.get("/api/search/history?source=ai").get_json()["history"]
        assert len(ai_rows) == 1 and ai_rows[0]["mode"] == "joint"
        single_id = next(row["id"] for row in all_rows if row["mode"] == "single")
        detail = client.get(f"/api/search/history/{single_id}").get_json()["history"]
        assert detail["result"]["result_data"]["results"][0]["cell_index"] == 2
        assert client.delete(f"/api/search/history/{single_id}").status_code == 200
        assert single_id not in {row["id"] for row in client.get("/api/search/history").get_json()["history"]}
        cleared = client.delete("/api/search/history?source=query_lab").get_json()
        assert cleared["hidden_count"] == 1

        with app.app_context():
            assert Task.query.filter_by(created_by_id=owner_id).count() == 3
