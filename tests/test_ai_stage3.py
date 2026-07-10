"""Stage-three global assistant, context safety, navigation, and approval tests."""
import os
import tempfile
from types import SimpleNamespace

from cryptography.fernet import Fernet


def _make_app(tmpdir):
    from app import create_app
    from app.config import Config

    class TestConfig(Config):
        TESTING = True
        SECRET_KEY = "stage-three-test"
        SQLALCHEMY_DATABASE_URI = "sqlite:///" + os.path.join(tmpdir, "stage3.db").replace("\\", "/")
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


def _seed_assistant(app, decision):
    from app.extensions import db
    from app.models import AiConversation, AiMessage, AiModelConfig, AiProviderConfig, AiRun

    with app.app_context():
        db.create_all()
        user = _user("researcher")
        provider = AiProviderConfig(
            provider="qwen", name="Qwen", base_url="https://example.com/v1",
            api_key_ciphertext="encrypted", api_key_hint="***test", enabled=True,
        )
        db.session.add_all([user, provider])
        db.session.flush()
        model = AiModelConfig(
            provider_config_id=provider.id, model_id="qwen-test", display_name="Qwen Test",
            enabled=True, is_default=True, last_test_status="success", capability="chat",
        )
        conversation = AiConversation(user_id=user.id, title="助手", kind="assistant")
        db.session.add_all([model, conversation])
        db.session.flush()
        message = AiMessage(conversation_id=conversation.id, role="user", content="这个页面是做什么的？")
        db.session.add(message)
        db.session.flush()
        run = AiRun(
            conversation_id=conversation.id, user_id=user.id, model_config_id=model.id,
            input_message_id=message.id, status="queued", surface="assistant",
            page_context_json='{"path":"/datasets","resources":{},"password":"secret"}',
        )
        db.session.add(run)
        db.session.commit()
        return user.id, conversation.id, run.id


class _FakeAssistantProvider:
    def __init__(self, decision):
        self.decision = decision

    def complete_structured(self, **_kwargs):
        from app.ai.provider import ProviderUsage
        return SimpleNamespace(
            value=self.decision, raw_text=self.decision.model_dump_json(),
            usage=ProviderUsage(requests=1, input_tokens=10, output_tokens=20, latency_ms=5),
        )


def test_page_context_is_sanitized_and_navigation_is_allowlisted():
    from app.ai.assistant import resolve_navigation, sanitize_page_context
    from app.extensions import db
    from app.models import Dataset

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        app = _make_app(tmpdir)
        with app.app_context():
            db.create_all()
            owner = _user("owner")
            outsider = _user("outsider")
            db.session.add_all([owner, outsider])
            db.session.flush()
            dataset = Dataset(name="private", file_path="x.h5ad", owner_id=owner.id, visibility="private")
            db.session.add(dataset)
            db.session.commit()
            cleaned = sanitize_page_context({
                "path": "/datasets", "password": "never", "api_key": "never",
                "resources": {"dataset_id": dataset.id}, "filters": {"status": "ready", "secret": "x"},
            }, outsider)
            assert "password" not in cleaned and "api_key" not in cleaned
            assert "dataset_id" not in cleaned.get("resources", {})
            assert resolve_navigation("dataset_detail", {"dataset_id": dataset.id}, outsider) is None
            assert resolve_navigation("overview", {}, outsider)["path"] == "/overview"


def test_global_assistant_answer_uses_separate_conversation_kind(monkeypatch):
    from app.ai.assistant import run_assistant
    from app.ai.schemas import AssistantTurnDecision
    from app.extensions import db
    from app.models import AiConversation, AiRun
    import app.ai.knowledge as knowledge
    import app.ai.service as service

    decision = AssistantTurnDecision(
        intent="answer_only",
        direct_answer="这是数据资源页面，可查看你有权访问的数据集。",
        supporting_points=["你可以继续打开数据集详情并查看索引状态。"],
    )
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        app = _make_app(tmpdir)
        _, conversation_id, run_id = _seed_assistant(app, decision)
        monkeypatch.setattr(knowledge, "retrieve_knowledge", lambda *args, **kwargs: [])
        monkeypatch.setattr(service, "configured_provider", lambda *_args, **_kwargs: _FakeAssistantProvider(decision))
        run_assistant(app, run_id)
        with app.app_context():
            run = db.session.get(AiRun, run_id)
            conversation = db.session.get(AiConversation, conversation_id)
            assert conversation.kind == "assistant"
            assert run.status == "success" and run.surface == "assistant"
            assert run.prompt_revision == "stage3-r1"
            assert "password" not in (run.page_context_json or "")
            assert "数据资源页面" in run.output_message.content


def test_write_action_requires_confirmation_and_is_idempotent(monkeypatch):
    from app.ai.assistant import run_assistant
    from app.ai.schemas import AssistantTurnDecision
    from app.extensions import db
    from app.models import AiRun, AiToolCall, Dataset, Task, User
    import app.ai.knowledge as knowledge
    import app.ai.service as service
    import app.services.platform_action_service as actions

    decision = AssistantTurnDecision(
        intent="propose_action",
        direct_answer="可以为当前数据集提交处理任务。",
        action="submit_dataset_processing",
        action_args={},
    )
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        app = _make_app(tmpdir)
        user_id, _, run_id = _seed_assistant(app, decision)
        with app.app_context():
            dataset = Dataset(name="uploaded", file_path="u.h5ad", owner_id=user_id, status="uploaded")
            db.session.add(dataset)
            db.session.commit()
            run = db.session.get(AiRun, run_id)
            run.page_context_json = '{"path":"/datasets/%s","resources":{"dataset_id":%s}}' % (dataset.id, dataset.id)
            db.session.commit()
        monkeypatch.setattr(knowledge, "retrieve_knowledge", lambda *args, **kwargs: [])
        monkeypatch.setattr(service, "configured_provider", lambda *_args, **_kwargs: _FakeAssistantProvider(decision))
        run_assistant(app, run_id)
        with app.app_context():
            run = db.session.get(AiRun, run_id)
            tool = AiToolCall.query.filter_by(run_id=run.id).one()
            assert run.status == "awaiting_confirmation" and tool.status == "proposed"
            assert Task.query.count() == 0
            tool_id = tool.id

        monkeypatch.setattr(actions, "execute_action", lambda *args, **kwargs: {"status": "submitted"})
        client = app.test_client()
        assert client.post("/api/auth/login", data={"username": "researcher", "password": "pass1234"}).status_code == 200
        approved = client.post(f"/api/ai/tool-calls/{tool_id}/approve")
        assert approved.status_code == 202
        duplicate = client.post(f"/api/ai/tool-calls/{tool_id}/approve")
        assert duplicate.status_code == 409


def test_unregistered_or_destructive_actions_are_rejected():
    from app.services.platform_action_service import ActionValidationError, normalize_action
    from app.extensions import db

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        app = _make_app(tmpdir)
        with app.app_context():
            db.create_all()
            user = _user("researcher")
            db.session.add(user)
            db.session.commit()
            try:
                normalize_action("delete_dataset", {"dataset_id": 1}, user)
                assert False, "destructive action must not be registered"
            except ActionValidationError:
                pass
