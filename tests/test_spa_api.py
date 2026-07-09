"""SPA JSON API boundary tests."""
import os
import sys
import tempfile
import time

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


def _wait_for_task(client, task_id, timeout=30):
    deadline = time.time() + timeout
    last_payload = None
    while time.time() < deadline:
        response = client.get(f"/api/tasks/{task_id}")
        assert response.status_code == 200
        last_payload = response.get_json()
        if last_payload["status"] in ("success", "error"):
            return last_payload
        time.sleep(0.25)
    raise AssertionError(f"task {task_id} did not finish: {last_payload}")


def test_spa_processing_index_search_and_scatter_baseline():
    from app.extensions import db
    from app.models import Dataset, User
    from scripts.create_demo_h5ad import create_demo_h5ad

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        app = _make_app(tmpdir)
        with app.app_context():
            db.create_all()
            user = User(username="researcher", role="admin")
            user.set_password("pass1234")
            db.session.add(user)
            db.session.commit()

            demo_path = os.path.join(tmpdir, "raw", "demo.h5ad")
            create_demo_h5ad(demo_path)
            dataset = Dataset(
                name="demo",
                description="functional baseline",
                file_path=demo_path,
                status="uploaded",
                owner_id=user.id,
                visibility="private",
            )
            db.session.add(dataset)
            db.session.commit()
            dataset_id = dataset.id

            client = app.test_client()
            login = client.post("/api/auth/login", data={"username": "researcher", "password": "pass1234"})
            assert login.status_code == 200

            process = client.post(f"/api/datasets/{dataset_id}/process")
            assert process.status_code == 200
            process_task = _wait_for_task(client, process.get_json()["task_id"])
            assert process_task["status"] == "success"
            db.session.expire_all()

            build = client.post(
                f"/api/datasets/{dataset_id}/build-index",
                data={"metric": "l2", "M": 16, "ef_construction": 200, "ef_search": 100},
            )
            assert build.status_code == 200
            build_task = _wait_for_task(client, build.get_json()["task_id"])
            assert build_task["status"] == "success"
            index_id = build_task["result"]["index_id"]

            search_task = client.post(
                "/api/search/task",
                data={"dataset_id": dataset_id, "index_id": index_id, "query_cell_index": 0, "top_k": 5},
            )
            assert search_task.status_code == 200
            search_task_payload = _wait_for_task(client, search_task.get_json()["task_id"])
            assert search_task_payload["status"] == "success"
            assert len(search_task_payload["result"]["result_data"]["results"]) == 5
            assert search_task_payload["result"]["scatter_plot"]["data"]

            sync_search = client.post(
                "/api/search",
                data={"dataset_id": dataset_id, "index_id": index_id, "query_cell_index": 0, "top_k": 5},
            )
            assert sync_search.status_code == 200
            search_payload = sync_search.get_json()
            assert len(search_payload["result_data"]["results"]) == 5
            assert search_payload["scatter_plot"]["data"]

            multi_task = client.post(
                "/api/search/multi/task",
                data={
                    "dataset_id": dataset_id,
                    "index_id": index_id,
                    "query_cell_index": 0,
                    "top_k": 5,
                    "target_scope": "selected",
                    "target_dataset_ids": str(dataset_id),
                },
            )
            assert multi_task.status_code == 200
            multi_payload = _wait_for_task(client, multi_task.get_json()["task_id"])
            assert multi_payload["status"] == "success"
            assert len(multi_payload["result"]["result_data"]["results"]) == 5

            scatter = client.get(f"/api/datasets/{dataset_id}/scatter")
            assert scatter.status_code == 200
            assert scatter.get_json()["scatter_plot"]["data"]

            db.session.remove()
            db.engine.dispose()
