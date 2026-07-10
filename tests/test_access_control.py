"""Dataset collaboration and account-management authorization tests."""
import os
import tempfile


def _make_app(tmpdir):
    from app import create_app
    from app.config import Config

    class TestConfig(Config):
        TESTING = True
        SECRET_KEY = "access-test-secret"
        SQLALCHEMY_DATABASE_URI = "sqlite:///" + os.path.join(tmpdir, "access.db").replace("\\", "/")
        RAW_DIR = os.path.join(tmpdir, "raw")
        CACHE_DIR = os.path.join(tmpdir, "cache")
        INDEX_DIR = os.path.join(tmpdir, "indexes")

    return create_app(TestConfig)


def _user(username, role="user", enabled=True):
    from app.models import User

    user = User(username=username, role=role, is_enabled=enabled)
    user.set_password("pass1234")
    return user


def _login(client, username, password="pass1234"):
    return client.post("/api/auth/login", data={"username": username, "password": password})


def test_dataset_role_matrix_and_task_visibility():
    from app.extensions import db
    from app.models import Dataset, DatasetPermission, Task
    from app.services.access_service import (
        accessible_datasets_query,
        accessible_tasks_query,
        can_edit_dataset,
        can_manage_dataset,
        can_view_dataset,
        effective_dataset_role,
    )

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        app = _make_app(tmpdir)
        with app.app_context():
            db.create_all()
            admin = _user("admin", "admin")
            owner = _user("owner")
            editor = _user("editor")
            viewer = _user("viewer")
            outsider = _user("outsider")
            db.session.add_all([admin, owner, editor, viewer, outsider])
            db.session.flush()
            private = Dataset(name="private", file_path="private.h5ad", owner_id=owner.id, visibility="private")
            shared = Dataset(name="shared", file_path="shared.h5ad", owner_id=owner.id, visibility="shared")
            unowned = Dataset(name="unowned", file_path="legacy.h5ad", owner_id=None, visibility="private")
            db.session.add_all([private, shared, unowned])
            db.session.flush()
            db.session.add_all([
                DatasetPermission(dataset_id=private.id, user_id=editor.id, level="editor", granted_by_id=owner.id),
                DatasetPermission(dataset_id=private.id, user_id=viewer.id, level="viewer", granted_by_id=owner.id),
            ])
            db.session.add_all([
                Task(type="process", dataset_id=private.id, created_by_id=owner.id),
                Task(type="search", dataset_id=private.id, created_by_id=viewer.id),
                Task(type="build_joint_index", dataset_id=None, created_by_id=viewer.id),
                Task(type="build_joint_index", dataset_id=None, created_by_id=owner.id),
            ])
            db.session.commit()

            assert effective_dataset_role(private, admin) == "admin"
            assert effective_dataset_role(private, owner) == "owner"
            assert effective_dataset_role(private, editor) == "editor"
            assert effective_dataset_role(private, viewer) == "viewer"
            assert effective_dataset_role(private, outsider) is None
            assert effective_dataset_role(shared, outsider) == "viewer"
            assert effective_dataset_role(unowned, outsider) is None
            assert effective_dataset_role(unowned, admin) == "admin"
            assert can_view_dataset(private, viewer)
            assert not can_edit_dataset(private, viewer)
            assert can_edit_dataset(private, editor)
            assert not can_manage_dataset(private, editor)
            assert can_manage_dataset(private, owner)

            outsider_names = {row.name for row in accessible_datasets_query(user=outsider).all()}
            assert outsider_names == {"shared"}
            editor_names = {row.name for row in accessible_datasets_query(user=editor).all()}
            assert editor_names == {"private", "shared"}

            viewer_tasks = accessible_tasks_query(user=viewer).all()
            assert {(row.type, row.created_by_id) for row in viewer_tasks} == {
                ("search", viewer.id),
                ("build_joint_index", viewer.id),
            }
            editor_tasks = accessible_tasks_query(user=editor).all()
            assert {(row.type, row.created_by_id) for row in editor_tasks} == {
                ("process", owner.id),
                ("search", viewer.id),
            }
            db.session.remove()
            db.engine.dispose()


def test_dataset_sharing_transfer_and_owner_audit_api(monkeypatch):
    import app.routes.api as api_routes
    from app.extensions import db
    from app.models import AuditLog, Dataset, DatasetPermission

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        app = _make_app(tmpdir)
        with app.app_context():
            db.create_all()
            owner = _user("owner")
            member = _user("member")
            viewer = _user("viewer")
            db.session.add_all([owner, member, viewer])
            db.session.flush()
            dataset = Dataset(name="study", file_path="study.h5ad", owner_id=owner.id, visibility="private")
            db.session.add(dataset)
            db.session.commit()
            dataset_id = dataset.id
            member_id = member.id
            viewer_id = viewer.id

            client = app.test_client()
            monkeypatch.setattr(api_routes.executor, "submit", lambda *args, **kwargs: None)
            assert _login(client, "owner").status_code == 200
            grant = client.put(
                f"/api/datasets/{dataset_id}/access/users/{member_id}",
                data={"level": "editor"},
            )
            assert grant.status_code == 200
            assert grant.get_json()["permission"]["level"] == "editor"
            client.post("/api/auth/logout")
            assert _login(client, "member").status_code == 200
            assert client.post(f"/api/datasets/{dataset_id}/process").status_code == 200
            client.post("/api/auth/logout")
            assert _login(client, "owner").status_code == 200
            assert client.patch(f"/api/datasets/{dataset_id}/access", data={"visibility": "shared"}).status_code == 200
            client.post("/api/auth/logout")
            assert _login(client, "viewer").status_code == 200
            assert client.post(f"/api/datasets/{dataset_id}/process").status_code == 403
            client.post("/api/auth/logout")
            assert _login(client, "owner").status_code == 200
            transfer = client.post(
                f"/api/datasets/{dataset_id}/transfer-ownership",
                data={"new_owner_id": member_id},
            )
            assert transfer.status_code == 200

            db.session.expire_all()
            dataset = db.session.get(Dataset, dataset_id)
            assert dataset.owner_id == member_id
            old_owner_grant = DatasetPermission.query.filter_by(dataset_id=dataset_id, user_id=owner.id).first()
            assert old_owner_grant and old_owner_grant.level == "editor"
            assert DatasetPermission.query.filter_by(dataset_id=dataset_id, user_id=member_id).first() is None
            assert AuditLog.query.filter_by(event="dataset.owner_transferred", dataset_id=dataset_id).count() == 1

            client.post("/api/auth/logout")
            assert _login(client, "owner").status_code == 200
            assert client.patch(f"/api/datasets/{dataset_id}/access", data={"visibility": "private"}).status_code == 403

            client.post("/api/auth/logout")
            assert _login(client, "viewer").status_code == 200
            assert client.get(f"/api/datasets/{dataset_id}").status_code == 200
            assert client.get(f"/api/datasets/{dataset_id}/access").status_code == 403

            client.post("/api/auth/logout")
            assert _login(client, "member").status_code == 200
            audit = client.get(f"/api/access/audit?dataset_id={dataset_id}")
            assert audit.status_code == 200
            assert any(row["event"] == "dataset.owner_transferred" for row in audit.get_json()["events"])
            assert client.put(
                f"/api/datasets/{dataset_id}/access/users/{viewer_id}",
                data={"level": "viewer"},
            ).status_code == 200
            db.session.remove()
            db.engine.dispose()


def test_user_management_disabled_login_and_last_admin_protection():
    from app.extensions import db
    from app.models import AuditLog, User

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        app = _make_app(tmpdir)
        with app.app_context():
            db.create_all()
            admin = _user("admin", "admin")
            normal = _user("normal")
            victim = _user("victim")
            disabled = _user("disabled", enabled=False)
            db.session.add_all([admin, normal, victim, disabled])
            db.session.commit()
            admin_id = admin.id
            normal_id = normal.id
            victim_id = victim.id
            disabled_id = disabled.id

        client = app.test_client()
        victim_client = app.test_client()
        assert _login(victim_client, "victim").status_code == 200
        assert _login(client, "disabled").status_code == 403
        with app.app_context():
            assert AuditLog.query.filter_by(event="auth.login_blocked", target_user_id=disabled_id).count() == 1
        assert _login(client, "admin").status_code == 200
        assert client.patch(f"/api/access/users/{victim_id}", data={"is_enabled": "false"}).status_code == 200
        assert victim_client.get("/api/auth/me").get_json()["authenticated"] is False

        cannot_demote = client.patch(f"/api/access/users/{admin_id}", data={"role": "user"})
        assert cannot_demote.status_code == 409
        cannot_disable_self = client.patch(f"/api/access/users/{admin_id}", data={"is_enabled": "false"})
        assert cannot_disable_self.status_code == 409

        promote = client.patch(f"/api/access/users/{normal_id}", data={"role": "admin"})
        assert promote.status_code == 200
        demote = client.patch(f"/api/access/users/{admin_id}", data={"role": "user"})
        assert demote.status_code == 200
        with app.app_context():
            assert db.session.get(User, admin_id).role == "user"
            assert AuditLog.query.filter_by(event="user.updated", target_user_id=admin_id).count() == 1
            db.session.remove()
            db.engine.dispose()


def test_compatibility_migration_assigns_unowned_datasets_to_first_enabled_admin():
    from sqlalchemy import inspect, text
    from app.extensions import db
    from app.models import Dataset
    from app.services.schema_service import ensure_sqlite_schema

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        app = _make_app(tmpdir)
        with app.app_context():
            db.create_all()
            disabled_admin = _user("disabled-admin", "admin", enabled=False)
            first_admin = _user("first-admin", "admin")
            second_admin = _user("second-admin", "admin")
            db.session.add_all([disabled_admin, first_admin, second_admin])
            db.session.flush()
            legacy = Dataset(name="legacy", file_path="legacy.h5ad", owner_id=None, visibility="private")
            db.session.add(legacy)
            db.session.commit()
            db.session.execute(text("DROP TABLE dataset_permissions"))
            db.session.execute(text("DROP TABLE audit_logs"))
            db.session.commit()

            ensure_sqlite_schema()
            db.session.expire_all()
            assert db.session.get(Dataset, legacy.id).owner_id == first_admin.id
            inspector = inspect(db.engine)
            assert inspector.has_table("dataset_permissions")
            assert inspector.has_table("audit_logs")
            db.session.remove()
            db.engine.dispose()


def test_spa_module_assets_use_browser_compatible_mime_type(monkeypatch):
    import pathlib
    from app.extensions import db
    from app import spa

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        app = _make_app(tmpdir)
        dist_dir = pathlib.Path(tmpdir) / "dist"
        assets_dir = dist_dir / "assets"
        assets_dir.mkdir(parents=True)
        (assets_dir / "app.js").write_text("export default 1;", encoding="utf-8")
        (assets_dir / "app.css").write_text("body{}", encoding="utf-8")
        monkeypatch.setattr(spa, "frontend_dist_dir", lambda: str(dist_dir))
        with app.app_context():
            db.create_all()
            client = app.test_client()
            assert client.get("/assets/app.js").content_type.startswith("application/javascript")
            assert client.get("/assets/app.css").content_type.startswith("text/css")
            db.session.remove()
            db.engine.dispose()
