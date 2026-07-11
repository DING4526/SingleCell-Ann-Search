"""Stage-two RAG, multi-mode planning, streaming, and Chinese-output tests."""
import io
import os
import tempfile
from types import SimpleNamespace

from cryptography.fernet import Fernet


def _make_app(tmpdir):
    from app import create_app
    from app.config import Config

    class TestConfig(Config):
        TESTING = True
        SECRET_KEY = "stage-two-test"
        SQLALCHEMY_DATABASE_URI = "sqlite:///" + os.path.join(tmpdir, "stage2.db").replace("\\", "/")
        RAW_DIR = os.path.join(tmpdir, "raw")
        CACHE_DIR = os.path.join(tmpdir, "cache")
        INDEX_DIR = os.path.join(tmpdir, "indexes")
        KNOWLEDGE_DIR = os.path.join(tmpdir, "knowledge")
        AI_CREDENTIAL_ENCRYPTION_KEY = Fernet.generate_key().decode()

    return create_app(TestConfig)


def _user(name, role="user"):
    from app.models import User
    row = User(username=name, role=role)
    row.set_password("pass1234")
    return row


def _login(client, username):
    response = client.post("/api/auth/login", data={"username": username, "password": "pass1234"})
    assert response.status_code == 200


def test_three_scope_knowledge_ingestion_and_private_visibility(monkeypatch):
    import app.routes.ai as ai_routes
    from app.ai.knowledge import process_document, retrieve_knowledge
    from app.extensions import db
    from app.models import Dataset, KnowledgeDocument, User

    monkeypatch.setattr(ai_routes, "submit_document_processing", lambda *args: None)
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        app = _make_app(tmpdir)
        with app.app_context():
            db.create_all()
            admin = _user("admin", "admin")
            researcher = _user("researcher")
            db.session.add_all([admin, researcher])
            db.session.flush()
            db.session.add(Dataset(
                name="study", file_path="study.h5ad", owner_id=researcher.id,
                status="processed", n_cells=1,
            ))
            db.session.commit()

        user_client = app.test_client()
        admin_client = app.test_client()
        _login(user_client, "researcher")
        _login(admin_client, "admin")
        response = user_client.post(
            "/api/ai/knowledge/documents",
            data={
                "scope": "personal",
                "title": "个人研究笔记",
                "file": (io.BytesIO("肝细胞相似性需要结合疾病和年龄分布解释。".encode()), "note.txt"),
            },
            content_type="multipart/form-data",
        )
        assert response.status_code == 202
        document_id = response.get_json()["document"]["id"]
        with app.app_context():
            process_document(document_id, embed=False)
            owner = User.query.filter_by(username="researcher").first()
            hits = retrieve_knowledge("疾病年龄如何解释", user=owner)
            assert hits and hits[0]["document_id"] == document_id
            assert db.session.get(KnowledgeDocument, document_id).status == "ready"
        assert any(item["id"] == document_id for item in user_client.get("/api/ai/knowledge/documents").get_json()["documents"])
        assert all(item["id"] != document_id for item in admin_client.get("/api/ai/knowledge/documents").get_json()["documents"])


def test_analysis_plan_auto_prefers_joint_but_explicit_fanout_stays_fanout():
    from app.ai.schemas import AnalysisPlan, AnalysisStep
    from app.ai.service import _resolve_analysis_plan
    from app.extensions import db
    from app.models import AnnIndex, Cell, Dataset, JointIndex, JointIndexDataset

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        app = _make_app(tmpdir)
        with app.app_context():
            db.create_all()
            owner = _user("owner")
            db.session.add(owner)
            db.session.flush()
            source = Dataset(name="source", file_path="s.h5ad", owner_id=owner.id, status="indexed", n_cells=2, vector_dim=8)
            target = Dataset(name="target", file_path="t.h5ad", owner_id=owner.id, status="indexed", n_cells=2, vector_dim=8)
            db.session.add_all([source, target])
            db.session.flush()
            db.session.add_all([
                Cell(dataset_id=source.id, cell_index=0, cell_type="T"),
                AnnIndex(dataset_id=source.id, index_path="s.bin", status="ready", lifecycle="active", metric="l2"),
                AnnIndex(dataset_id=target.id, index_path="t.bin", status="ready", lifecycle="active", metric="l2"),
            ])
            joint = JointIndex(name="shared", status="ready", metric="l2", owner_id=owner.id)
            db.session.add(joint)
            db.session.flush()
            db.session.add_all([
                JointIndexDataset(joint_index_id=joint.id, dataset_id=source.id, status="included"),
                JointIndexDataset(joint_index_id=joint.id, dataset_id=target.id, status="included"),
            ])
            db.session.commit()

            def resolve(selection_mode):
                return _resolve_analysis_plan(AnalysisPlan(steps=[AnalysisStep(
                    tool="run_fanout_search", selection_mode=selection_mode,
                    dataset_reference=source.id, target_dataset_references=[target.id],
                    query_cell_index=0, top_k=10,
                )]), owner)

            automatic, valid = resolve("auto")
            assert valid and automatic["steps"][0]["tool"] == "run_joint_search"
            assert automatic["steps"][0]["joint_index_id"] == joint.id
            explicit, valid = resolve("explicit")
            assert valid and explicit["steps"][0]["tool"] == "run_fanout_search"


def test_embedding_adapter_and_chinese_guard(monkeypatch):
    import app.ai.provider as provider_module
    from app.ai.provider import OpenAICompatibleProvider
    from app.ai.service import _chinese_dominant

    calls = []

    class Embeddings:
        def create(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(
                data=[SimpleNamespace(index=0, embedding=[0.1, 0.2, 0.3])],
                usage=SimpleNamespace(prompt_tokens=4, total_tokens=4),
            )

    class Client:
        def __init__(self, **kwargs):
            self.embeddings = Embeddings()

    monkeypatch.setattr(provider_module, "CLIENT_FACTORY", Client)
    provider = OpenAICompatibleProvider(provider="openai", base_url="https://api.openai.com/v1", api_key="secret")
    result = provider.test_embedding("embedding-model")
    assert result.dimensions == 3 and result.usage.requests == 1
    assert calls[0]["input"] == ["单细胞相似性检索测试"]
    assert _chinese_dominant("结果主要由中文解释。算法名称可以保留 Harmony。")
    assert not _chinese_dominant("Only English sentences. No Chinese answer.")


def test_sse_replays_terminal_run_and_owner_isolation():
    from app.ai.streaming import emit_stream_event
    from app.extensions import db
    from app.models import AiConversation, AiMessage, AiModelConfig, AiProviderConfig, AiRun

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        app = _make_app(tmpdir)
        with app.app_context():
            db.create_all()
            owner = _user("owner")
            outsider = _user("outsider")
            db.session.add_all([owner, outsider])
            db.session.flush()
            provider = AiProviderConfig(
                provider="openai", name="mock", base_url="https://api.openai.com/v1",
                api_key_ciphertext="cipher", api_key_hint="***", enabled=True,
            )
            db.session.add(provider)
            db.session.flush()
            model = AiModelConfig(provider_config_id=provider.id, model_id="mock", display_name="mock")
            db.session.add(model)
            db.session.flush()
            conversation = AiConversation(user_id=owner.id)
            db.session.add(conversation)
            db.session.flush()
            message = AiMessage(conversation_id=conversation.id, role="user", content="测试")
            db.session.add(message)
            db.session.flush()
            run = AiRun(
                conversation_id=conversation.id, user_id=owner.id, model_config_id=model.id,
                input_message_id=message.id, status="success", summary_status="fallback",
            )
            db.session.add(run)
            db.session.flush()
            emit_stream_event(run.id, "answer.replace", {"content": "中文回答"})
            emit_stream_event(run.id, "run.completed", {"status": "success"})
            db.session.commit()
            run_id = run.id

        owner_client = app.test_client()
        outsider_client = app.test_client()
        _login(owner_client, "owner")
        _login(outsider_client, "outsider")
        response = owner_client.get(f"/api/ai/runs/{run_id}/events")
        assert response.status_code == 200
        assert b"event: answer.replace" in response.data
        assert b"event: run.completed" in response.data
        assert outsider_client.get(f"/api/ai/runs/{run_id}/events").status_code == 404


def test_confirmed_fanout_plan_reuses_service_and_creates_ai_history(monkeypatch):
    import app.ai.service as ai_service
    import app.services.multi_search_service as multi_service
    from app.ai.schemas import AnalysisPlan, AnalysisStep
    from app.ai.service import apply_analysis_plan, run_execution
    from app.extensions import db
    from app.models import (
        AiConversation, AiMessage, AiModelConfig, AiProviderConfig, AiRun,
        AnnIndex, Cell, Dataset, Task,
    )

    calls = []

    def fake_fanout(**kwargs):
        calls.append(kwargs)
        return {
            "results": [
                {"rank": 1, "dataset_id": kwargs["target_dataset_ids"][0], "dataset_name": "target",
                 "cell_index": 1, "distance": 0.2, "cell_type": "T", "disease": "normal", "age_group": "adult"},
            ],
            "query_time_ms": 2.0,
            "query_cell_index": kwargs["query_cell_index"],
            "top_k": kwargs["top_k"],
            "skipped": [],
        }

    monkeypatch.setattr(multi_service, "search_across_datasets", fake_fanout)
    monkeypatch.setattr(ai_service, "submit_summary", lambda *args: None)
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        app = _make_app(tmpdir)
        with app.app_context():
            db.create_all()
            user = _user("researcher")
            db.session.add(user)
            db.session.flush()
            source = Dataset(name="source", file_path="s.h5ad", owner_id=user.id, status="indexed", n_cells=2, vector_dim=8)
            target = Dataset(name="target", file_path="t.h5ad", owner_id=user.id, status="indexed", n_cells=2, vector_dim=8)
            db.session.add_all([source, target])
            db.session.flush()
            db.session.add_all([
                Cell(dataset_id=source.id, cell_index=0, cell_type="T", disease="normal", age_group="adult"),
                AnnIndex(dataset_id=source.id, index_path="s.bin", status="ready", lifecycle="active", metric="l2"),
                AnnIndex(dataset_id=target.id, index_path="t.bin", status="ready", lifecycle="active", metric="l2"),
            ])
            provider = AiProviderConfig(
                provider="openai", name="mock", base_url="https://api.openai.com/v1",
                api_key_ciphertext="cipher", api_key_hint="***", enabled=True,
            )
            db.session.add(provider)
            db.session.flush()
            model = AiModelConfig(
                provider_config_id=provider.id, model_id="mock", display_name="mock",
                enabled=True, last_test_status="success", capability="chat",
            )
            db.session.add(model)
            conversation = AiConversation(user_id=user.id)
            db.session.add(conversation)
            db.session.flush()
            message = AiMessage(conversation_id=conversation.id, role="user", content="跨数据集检索")
            db.session.add(message)
            db.session.flush()
            run = AiRun(
                conversation_id=conversation.id, user_id=user.id, model_config_id=model.id,
                input_message_id=message.id, status="planning", intent="analysis_request",
            )
            db.session.add(run)
            db.session.flush()
            plan = AnalysisPlan(steps=[
                AnalysisStep(tool="get_dataset_profile", dataset_reference=source.id, query_cell_index=0),
                AnalysisStep(
                    tool="run_fanout_search", selection_mode="explicit", dataset_reference=source.id,
                    target_dataset_references=[target.id], query_cell_index=0, top_k=5,
                ),
                AnalysisStep(tool="build_evidence_report"),
            ])
            resolved, valid = apply_analysis_plan(run, plan, user)
            assert valid and resolved["steps"][1]["tool"] == "run_fanout_search"
            for tool in run.tool_calls:
                tool.status = "approved"
            run.status = "executing"
            db.session.commit()
            run_id = run.id
            target_id = target.id

        run_execution(app, run_id)
        with app.app_context():
            run = db.session.get(AiRun, run_id)
            assert run.status == "success"
            task = db.session.get(Task, run.search_task_id)
            assert task.type == "multi_search" and task.source == "ai"
            assert calls[0]["target_dataset_ids"] == [target_id]
            result = __import__("json").loads(run.result_json)
            assert result["evidence"]["dataset_distribution"] == {"target": 1}
            assert result["provenance"]["task_ids"] == [task.id]
