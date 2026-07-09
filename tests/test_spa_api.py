"""SPA JSON API boundary tests."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def _make_app(tmpdir):
    from app import create_app
    from app.config import Config

    class TestConfig(Config):
        TESTING = True
        SECRET_KEY = "test-secret"
        SQLALCHEMY_DATABASE_URI = "sqlite:///" + os.path.join(tmpdir, "app.db").replace("\\", "/")
        RAW_DIR = os.path.join(tmpdir, "raw")
        CACHE_DIR = os.path.join(tmpdir, "cache")
        INDEX_DIR = os.path.join(tmpdir, "indexes")

    return create_app(TestConfig)


def test_api_requires_json_auth_for_protected_routes():
    from app.extensions import db

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        app = _make_app(tmpdir)
        with app.app_context():
            db.create_all()
            response = app.test_client().get("/api/datasets")
            assert response.status_code == 401
            assert response.is_json
            assert response.get_json()["ok"] is False
            db.session.remove()
            db.engine.dispose()


def test_auth_me_and_dataset_resource_api():
    from app.extensions import db
    from app.models import Dataset, User

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        app = _make_app(tmpdir)
        with app.app_context():
            db.create_all()
            user = User(username="researcher", role="user")
            user.set_password("pass1234")
            db.session.add(user)
            db.session.commit()

            dataset = Dataset(
                name="demo",
                description="test dataset",
                file_path=os.path.join(tmpdir, "raw", "demo.h5ad"),
                status="uploaded",
                owner_id=user.id,
                visibility="private",
            )
            db.session.add(dataset)
            db.session.commit()

            client = app.test_client()
            login = client.post("/api/auth/login", data={"username": "researcher", "password": "pass1234"})
            assert login.status_code == 200
            assert login.get_json()["user"]["username"] == "researcher"

            me = client.get("/api/auth/me").get_json()
            assert me["authenticated"] is True
            assert me["user"]["role"] == "user"

            listing = client.get("/api/datasets").get_json()
            assert listing["ok"] is True
            assert listing["datasets"][0]["name"] == "demo"

            detail = client.get(f"/api/datasets/{dataset.id}").get_json()
            assert detail["ok"] is True
            assert detail["dataset"]["can_manage"] is True

            db.session.remove()
            db.engine.dispose()
