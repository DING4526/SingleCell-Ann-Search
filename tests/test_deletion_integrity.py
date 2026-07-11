import json
import os
import pathlib
import sqlite3

import pytest
from sqlalchemy import inspect, text

from app import create_app
from app.extensions import db
from app.models import (
    AiConversation,
    AiCitation,
    AiModelConfig,
    AiProviderCall,
    AiProviderConfig,
    AiRun,
    AiStreamEvent,
    AnnIndex,
    Dataset,
    DatasetPermission,
    IndexEvaluation,
    IndexExperiment,
    JointIndex,
    JointIndexDataset,
    JointQueryLog,
    KnowledgeDocument,
    Task,
    User,
)
from app.services.deletion_service import delete_dataset
from app.services.schema_service import _repair_known_orphans


@pytest.fixture()
def deletion_app(tmp_path):
    class TestConfig:
        TESTING = True
        SECRET_KEY = "deletion-test"
        SQLALCHEMY_DATABASE_URI = "sqlite:///" + str(tmp_path / "deletion.db").replace("\\", "/")
        SQLALCHEMY_TRACK_MODIFICATIONS = False
        RAW_DIR = str(tmp_path / "raw")
        CACHE_DIR = str(tmp_path / "cache")
        INDEX_DIR = str(tmp_path / "indexes")
        KNOWLEDGE_DIR = str(tmp_path / "knowledge")
        FRONTEND_DIST_DIR = str(tmp_path / "missing-frontend-dist")
        AI_STREAM_EVENT_RETENTION_HOURS = 24

    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()
    yield app
    with app.app_context():
        db.session.remove()
        db.engine.dispose()


def _user(username="owner", role="user"):
    row = User(username=username, role=role, is_enabled=True)
    row.set_password("pass1234")
    db.session.add(row)
    db.session.flush()
    return row


def _dataset(app, owner, name="研究数据"):
    path = pathlib.Path(app.config["RAW_DIR"]) / f"{name}.h5ad"
    path.write_bytes(b"h5ad")
    row = Dataset(
        name=name,
        file_path=str(path),
        owner_id=owner.id,
        status="processed",
        n_cells=2,
        vector_dim=2,
    )
    db.session.add(row)
    db.session.flush()
    return row, path


def _login(client, username="owner"):
    response = client.post("/api/auth/login", data={"username": username, "password": "pass1234"})
    assert response.status_code == 200


def test_sqlite_connections_and_history_schema_are_release_safe(deletion_app):
    with deletion_app.app_context():
        assert db.session.execute(text("PRAGMA foreign_keys")).scalar() == 1
        assert db.session.execute(text("PRAGMA foreign_key_check")).all() == []
        experiment_columns = {item["name"] for item in inspect(db.engine).get_columns("index_experiments")}
        evaluation_columns = {
            item["name"]: item for item in inspect(db.engine).get_columns("index_evaluations")
        }
        assert "history_hidden" in experiment_columns
        assert "history_hidden" in evaluation_columns
        assert evaluation_columns["index_id"]["nullable"] is True
        fk = next(
            item for item in inspect(db.engine).get_foreign_keys("index_evaluations")
            if item["constrained_columns"] == ["index_id"]
        )
        assert (fk.get("options") or {}).get("ondelete") == "SET NULL"


def test_missing_frontend_build_returns_release_safe_503(deletion_app):
    response = deletion_app.test_client().get("/login")
    assert response.status_code == 503
    body = response.get_data(as_text=True)
    assert "npm install" not in body
    assert "平台前端暂不可用" in body
    legacy = deletion_app.test_client().get("/background")
    assert legacy.status_code == 302
    assert legacy.headers["Location"].endswith("/overview")


def test_legacy_ai_orphans_are_repaired_before_fk_validation(deletion_app):
    with deletion_app.app_context():
        database_path = db.engine.url.database
        db.session.remove()
        db.engine.dispose()
    connection = sqlite3.connect(database_path)
    try:
        connection.execute("PRAGMA foreign_keys=OFF")
        connection.execute(
            "INSERT INTO ai_stream_events (run_id, sequence, event_type, created_at) "
            "VALUES (999, 1, 'legacy', CURRENT_TIMESTAMP)"
        )
        connection.execute(
            "INSERT INTO ai_citations "
            "(message_id, chunk_id, citation_key, source_title, excerpt, created_at) "
            "VALUES (999, 999, 'legacy', 'legacy', 'legacy', CURRENT_TIMESTAMP)"
        )
        connection.execute(
            "INSERT INTO ai_provider_calls "
            "(run_id, document_id, model_config_id, operation, status, request_count, "
            "input_tokens, output_tokens, latency_ms, created_at) "
            "VALUES (999, 999, 999, 'legacy', 'success', 1, 0, 0, 0, CURRENT_TIMESTAMP)"
        )
        connection.commit()
    finally:
        connection.close()

    with deletion_app.app_context():
        _repair_known_orphans(db.engine)
        assert AiStreamEvent.query.count() == 0
        assert AiCitation.query.count() == 0
        call = AiProviderCall.query.one()
        assert call.run_id is None
        assert call.document_id is None
        assert call.model_config_id is None
        assert db.session.execute(text("PRAGMA foreign_key_check")).all() == []


def test_dataset_delete_blocks_dependencies_then_commits_before_cleanup(deletion_app):
    with deletion_app.app_context():
        owner = _user()
        dataset, raw_path = _dataset(deletion_app, owner)
        task = Task(
            type="process", status="running", dataset_id=dataset.id,
            created_by_id=owner.id, request_json=json.dumps({"dataset_id": dataset.id}),
        )
        db.session.add(task)
        db.session.commit()
        dataset_id, task_id, owner_id = dataset.id, task.id, owner.id

    client = deletion_app.test_client()
    _login(client)
    response = client.delete(f"/api/datasets/{dataset_id}")
    assert response.status_code == 409
    assert response.get_json()["code"] == "DATASET_DELETE_BLOCKED"
    assert response.get_json()["blockers"][0]["type"] == "task"
    assert raw_path.exists()

    with deletion_app.app_context():
        db.session.get(Task, task_id).status = "success"
        joint = JointIndex(name="依赖联合索引", owner_id=owner_id, status="ready")
        db.session.add(joint)
        db.session.flush()
        db.session.add(JointIndexDataset(joint_index_id=joint.id, dataset_id=dataset_id))
        db.session.commit()
        joint_id = joint.id

    response = client.delete(f"/api/datasets/{dataset_id}")
    assert response.status_code == 409
    assert any(item["type"] == "joint_index" for item in response.get_json()["blockers"])

    with deletion_app.app_context():
        db.session.query(JointIndexDataset).filter_by(joint_index_id=joint_id).delete()
        db.session.query(JointIndex).filter_by(id=joint_id).delete()
        index_path = pathlib.Path(deletion_app.config["INDEX_DIR"]) / "dataset-index.bin"
        index_path.write_bytes(b"index")
        index = AnnIndex(
            dataset_id=dataset_id, index_path=index_path.name, status="ready",
            lifecycle="active", algorithm="hnswlib_hnsw", metric="l2",
        )
        db.session.add(index)
        db.session.flush()
        evaluation = IndexEvaluation(dataset_id=dataset_id, index_id=index.id, status="success")
        experiment = IndexExperiment(dataset_id=dataset_id, created_by_id=owner_id, status="success")
        document_path = pathlib.Path(deletion_app.config["KNOWLEDGE_DIR"]) / "dataset-note.md"
        document_path.write_text("dataset knowledge", encoding="utf-8")
        document = KnowledgeDocument(
            scope="dataset", dataset_id=dataset_id, owner_id=owner_id, title="数据集资料",
            stored_path=str(document_path), checksum="dataset-note", source_type="upload", status="ready",
        )
        db.session.add_all([evaluation, experiment, document])
        db.session.commit()
        dependent_ids = index.id, evaluation.id, experiment.id, document.id
    response = client.delete(f"/api/datasets/{dataset_id}")
    assert response.status_code == 200
    assert response.get_json()["cleanup_status"] == "success"
    assert not raw_path.exists()
    with deletion_app.app_context():
        assert db.session.get(Dataset, dataset_id) is None
        assert db.session.get(AnnIndex, dependent_ids[0]) is None
        assert db.session.get(IndexEvaluation, dependent_ids[1]) is None
        assert db.session.get(IndexExperiment, dependent_ids[2]) is None
        assert db.session.get(KnowledgeDocument, dependent_ids[3]) is None
        cleanup = Task.query.filter_by(type="artifact_cleanup").one()
        assert cleanup.status == "success"
        assert cleanup.history_hidden is True
        assert db.session.execute(text("PRAGMA foreign_key_check")).all() == []
    assert not index_path.exists()
    assert not document_path.exists()


def test_database_failure_never_unlinks_dataset_file(deletion_app, monkeypatch):
    with deletion_app.app_context():
        owner = _user()
        dataset, raw_path = _dataset(deletion_app, owner)
        db.session.commit()
        dataset_id = dataset.id

        def fail_commit():
            raise RuntimeError("injected commit failure")

        monkeypatch.setattr(db.session, "commit", fail_commit)
        with pytest.raises(RuntimeError, match="injected"):
            delete_dataset(dataset, actor=owner)
        db.session.rollback()
        assert raw_path.exists()
        assert db.session.get(Dataset, dataset_id) is not None


def test_index_and_history_lifecycle_endpoints(deletion_app):
    with deletion_app.app_context():
        owner = _user()
        dataset, _ = _dataset(deletion_app, owner)
        dataset.status = "indexed"
        index_file = pathlib.Path(deletion_app.config["INDEX_DIR"]) / "primary.bin"
        index_file.write_bytes(b"index")
        index = AnnIndex(
            dataset_id=dataset.id, index_path=index_file.name, status="ready",
            lifecycle="active", algorithm="hnswlib_hnsw", metric="l2",
        )
        db.session.add(index)
        db.session.flush()
        evaluation = IndexEvaluation(
            dataset_id=dataset.id, index_id=index.id, status="success", algorithm=index.algorithm,
        )
        experiment = IndexExperiment(dataset_id=dataset.id, created_by_id=owner.id, status="success")
        terminal = Task(type="search", status="success", dataset_id=dataset.id, created_by_id=owner.id)
        running = Task(type="search", status="running", dataset_id=dataset.id, created_by_id=owner.id)
        db.session.add_all([evaluation, experiment, terminal, running])
        db.session.commit()
        ids = dataset.id, index.id, evaluation.id, experiment.id, terminal.id, running.id

    dataset_id, index_id, evaluation_id, experiment_id, terminal_id, running_id = ids
    client = deletion_app.test_client()
    _login(client)
    response = client.delete(f"/api/datasets/{dataset_id}/indexes/{index_id}")
    assert response.status_code == 200
    assert not index_file.exists()
    with deletion_app.app_context():
        assert db.session.get(AnnIndex, index_id) is None
        assert db.session.get(IndexEvaluation, evaluation_id).index_id is None
        assert db.session.get(Dataset, dataset_id).status == "processed"

    assert client.delete(f"/api/index-evaluations/{evaluation_id}").status_code == 200
    assert client.delete(f"/api/index-experiments/{experiment_id}").status_code == 200
    assert client.delete(f"/api/tasks/{terminal_id}").status_code == 200
    conflict = client.delete(f"/api/tasks/{running_id}")
    assert conflict.status_code == 409
    assert conflict.get_json()["code"] == "TASK_RUNNING"
    payload = client.get("/api/tasks").get_json()
    assert terminal_id not in {item["id"] for item in payload["tasks"]}
    assert client.get("/api/index-evaluations").get_json()["evaluations"] == []
    assert client.get("/api/index-experiments").get_json()["experiments"] == []


def test_index_and_joint_delete_permission_matrix(deletion_app):
    with deletion_app.app_context():
        owner = _user("owner")
        editor = _user("editor")
        outsider = _user("outsider")
        admin = _user("admin", role="admin")
        dataset, _ = _dataset(deletion_app, owner)
        db.session.add(DatasetPermission(
            dataset_id=dataset.id, user_id=editor.id, level="editor", granted_by_id=owner.id,
        ))
        index = AnnIndex(
            dataset_id=dataset.id, index_path="", status="ready", lifecycle="active",
            algorithm="hnswlib_hnsw", metric="l2",
        )
        joint = JointIndex(name="权限联合索引", owner_id=owner.id, status="ready")
        db.session.add_all([index, joint])
        db.session.commit()
        dataset_id, index_id, joint_id = dataset.id, index.id, joint.id

    outsider_client = deletion_app.test_client()
    _login(outsider_client, "outsider")
    assert outsider_client.delete(
        f"/api/datasets/{dataset_id}/indexes/{index_id}"
    ).status_code == 403
    assert outsider_client.delete(f"/api/joint-indexes/{joint_id}").status_code == 403

    editor_client = deletion_app.test_client()
    _login(editor_client, "editor")
    assert editor_client.delete(
        f"/api/datasets/{dataset_id}/indexes/{index_id}"
    ).status_code == 200

    admin_client = deletion_app.test_client()
    _login(admin_client, "admin")
    assert admin_client.delete(f"/api/joint-indexes/{joint_id}").status_code == 200


def test_artifact_cleanup_failure_is_persistent_and_retryable(deletion_app, monkeypatch):
    with deletion_app.app_context():
        owner = _user()
        dataset, _ = _dataset(deletion_app, owner)
        index_file = pathlib.Path(deletion_app.config["INDEX_DIR"]) / "retry.bin"
        index_file.write_bytes(b"index")
        index = AnnIndex(
            dataset_id=dataset.id, index_path=index_file.name, status="ready",
            lifecycle="active", algorithm="hnswlib_hnsw", metric="l2",
        )
        db.session.add(index)
        db.session.commit()
        dataset_id, index_id = dataset.id, index.id

    client = deletion_app.test_client()
    _login(client)
    original_unlink = pathlib.Path.unlink

    def fail_unlink(self, *args, **kwargs):
        if self.resolve() == index_file.resolve():
            raise OSError("injected unlink failure")
        return original_unlink(self, *args, **kwargs)

    with monkeypatch.context() as scoped:
        scoped.setattr(pathlib.Path, "unlink", fail_unlink)
        response = client.delete(f"/api/datasets/{dataset_id}/indexes/{index_id}")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["cleanup_status"] == "error"
    assert index_file.exists()
    cleanup_task_id = payload["cleanup_task_id"]
    with deletion_app.app_context():
        assert db.session.get(AnnIndex, index_id) is None
        cleanup = db.session.get(Task, cleanup_task_id)
        assert cleanup.status == "error"
        assert cleanup.history_hidden is False

    retry = client.post(f"/api/tasks/{cleanup_task_id}/retry-cleanup")
    assert retry.status_code == 200
    assert retry.get_json()["cleanup"]["status"] == "success"
    assert not index_file.exists()


def test_joint_delete_cleans_all_artifacts_and_hides_search_history(deletion_app):
    with deletion_app.app_context():
        owner = _user()
        first, _ = _dataset(deletion_app, owner, "first")
        second, _ = _dataset(deletion_app, owner, "second")
        joint = JointIndex(name="联合空间", owner_id=owner.id, status="ready")
        db.session.add(joint)
        db.session.flush()
        artifacts = {
            "index_path": (pathlib.Path(deletion_app.config["INDEX_DIR"]), "joint.bin"),
            "vector_path": (pathlib.Path(deletion_app.config["CACHE_DIR"]), "joint.npy"),
            "umap_path": (pathlib.Path(deletion_app.config["CACHE_DIR"]), "joint_umap.npy"),
            "mapping_path": (pathlib.Path(deletion_app.config["CACHE_DIR"]), "joint_map.npz"),
        }
        paths = []
        for attribute, (root, filename) in artifacts.items():
            path = root / filename
            path.write_bytes(b"artifact")
            setattr(joint, attribute, filename)
            paths.append(path)
        db.session.add_all([
            JointIndexDataset(joint_index_id=joint.id, dataset_id=first.id),
            JointIndexDataset(joint_index_id=joint.id, dataset_id=second.id),
            JointQueryLog(
                joint_index_id=joint.id, query_dataset_id=first.id, query_cell_index=0,
                top_k=5, user_id=owner.id,
            ),
        ])
        history = Task(
            type="joint_search", source="query_lab", status="success", created_by_id=owner.id,
            request_json=json.dumps({"joint_index_id": joint.id}),
        )
        db.session.add(history)
        db.session.commit()
        joint_id, history_id = joint.id, history.id

    client = deletion_app.test_client()
    _login(client)
    response = client.delete(f"/api/joint-indexes/{joint_id}")
    assert response.status_code == 200
    assert all(not path.exists() for path in paths)
    with deletion_app.app_context():
        assert db.session.get(JointIndex, joint_id) is None
        assert JointQueryLog.query.filter_by(joint_index_id=joint_id).count() == 0
        assert db.session.get(Task, history_id).history_hidden is True


def test_ai_deletion_guards_and_historical_reference_protection(deletion_app):
    with deletion_app.app_context():
        owner = _user()
        provider = AiProviderConfig(
            provider="openai", name="测试供应商", base_url="https://example.com/v1",
            api_key_ciphertext="encrypted", api_key_hint="****", created_by_id=owner.id,
        )
        db.session.add(provider)
        db.session.flush()
        model = AiModelConfig(
            provider_config_id=provider.id, model_id="test-model", display_name="测试模型",
            capability="chat",
        )
        conversation = AiConversation(user_id=owner.id, title="运行中的会话")
        db.session.add_all([model, conversation])
        db.session.flush()
        run = AiRun(
            conversation_id=conversation.id, user_id=owner.id, model_config_id=model.id,
            status="executing",
        )
        db.session.add(run)
        builtin_path = pathlib.Path(deletion_app.root_path).parent / "docs" / "ai-knowledge" / "platform-quickstart.md"
        builtin = KnowledgeDocument(
            scope="platform", title="内置资料", stored_path=str(builtin_path), checksum="builtin",
            source_type="builtin", source_key="test-builtin", status="ready",
        )
        upload_path = pathlib.Path(deletion_app.config["KNOWLEDGE_DIR"]) / "upload.md"
        upload_path.write_text("content", encoding="utf-8")
        upload = KnowledgeDocument(
            scope="personal", owner_id=owner.id, title="上传资料", stored_path=str(upload_path),
            checksum="upload", source_type="upload", status="pending",
        )
        db.session.add_all([builtin, upload])
        db.session.commit()
        ids = conversation.id, run.id, provider.id, model.id, builtin.id, upload.id, owner.id

    conversation_id, run_id, provider_id, model_id, builtin_id, upload_id, owner_id = ids
    client = deletion_app.test_client()
    _login(client)
    response = client.delete(f"/api/ai/conversations/{conversation_id}")
    assert response.status_code == 409
    assert response.get_json()["code"] == "AI_CONVERSATION_RUNNING"
    response = client.delete(f"/api/ai/knowledge/documents/{builtin_id}")
    assert response.status_code == 409
    assert response.get_json()["code"] == "BUILTIN_IMMUTABLE"
    assert builtin_path.exists()
    response = client.delete(f"/api/ai/knowledge/documents/{upload_id}")
    assert response.status_code == 409
    assert response.get_json()["code"] == "AI_KNOWLEDGE_PROCESSING"

    with deletion_app.app_context():
        run = db.session.get(AiRun, run_id)
        run.status = "success"
        upload = db.session.get(KnowledgeDocument, upload_id)
        upload.status = "ready"
        db.session.add(AiProviderCall(
            user_id=owner_id, run_id=run.id, document_id=upload.id,
            model_config_id=model_id, operation="chat", status="success",
        ))
        db.session.commit()

    assert client.delete(f"/api/ai/conversations/{conversation_id}").status_code == 200
    assert client.delete(f"/api/ai/knowledge/documents/{upload_id}").status_code == 200
    assert not upload_path.exists()
    model_conflict = client.delete(f"/api/ai/admin/models/{model_id}")
    assert model_conflict.status_code == 403  # non-admin cannot manage provider configuration

    with deletion_app.app_context():
        owner = db.session.get(User, owner_id)
        owner.role = "admin"
        db.session.commit()
    model_conflict = client.delete(f"/api/ai/admin/models/{model_id}")
    assert model_conflict.status_code == 409
    assert model_conflict.get_json()["code"] == "AI_MODEL_IN_USE"
    provider_conflict = client.delete(f"/api/ai/admin/providers/{provider_id}")
    assert provider_conflict.status_code == 409
    with deletion_app.app_context():
        call = AiProviderCall.query.one()
        assert call.run_id is None
        assert call.document_id is None
        assert call.model_config_id == model_id
        assert db.session.execute(text("PRAGMA foreign_key_check")).all() == []
