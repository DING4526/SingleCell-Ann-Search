"""SPA JSON API boundary tests."""
import os
import sys
import tempfile
import time
import json

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
    from app.models import AnnIndex, Dataset, QueryLog, User
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

            algorithms = client.get(f"/api/ann/algorithms?dataset_id={dataset_id}")
            assert algorithms.status_code == 200
            algorithm_rows = {row["key"]: row for row in algorithms.get_json()["algorithms"]}
            assert algorithm_rows["hnswlib_hnsw"]["available"] is True
            assert algorithm_rows["hnswlib_rp_hnsw"]["available"] is True

            rp_build = client.post(
                f"/api/datasets/{dataset_id}/build-index",
                data={
                    "algorithm": "hnswlib_rp_hnsw",
                    "metric": "l2",
                    "M": 8,
                    "ef_construction": 80,
                    "ef_search": 50,
                    "projection_dim": 12,
                    "random_state": 42,
                },
            )
            assert rp_build.status_code == 200
            rp_payload = _wait_for_task(client, rp_build.get_json()["task_id"])
            assert rp_payload["status"] == "success", rp_payload.get("error")
            rp_index_id = rp_payload["result"]["index_id"]
            assert rp_payload["result"]["algorithm"] == "hnswlib_rp_hnsw"
            assert rp_payload["result"]["index_size_bytes"] > 0

            rp_search = client.post(
                "/api/search/task",
                data={"dataset_id": dataset_id, "index_id": rp_index_id, "query_cell_index": 0, "top_k": 5},
            )
            assert rp_search.status_code == 200
            rp_search_payload = _wait_for_task(client, rp_search.get_json()["task_id"])
            assert rp_search_payload["status"] == "success"
            assert len(rp_search_payload["result"]["result_data"]["results"]) == 5

            faiss_flat_available = algorithm_rows.get("faiss_flat", {}).get("available") is True
            if faiss_flat_available:
                faiss_build = client.post(
                    f"/api/datasets/{dataset_id}/build-index",
                    data={
                        "algorithm": "faiss_flat",
                        "metric": "l2",
                        "M": 16,
                        "ef_construction": 200,
                        "ef_search": 100,
                    },
                )
                assert faiss_build.status_code == 200
                faiss_payload = _wait_for_task(client, faiss_build.get_json()["task_id"])
                assert faiss_payload["status"] == "success", faiss_payload.get("error")
                assert faiss_payload["result"]["algorithm"] == "faiss_flat"

            experiment_candidates = [
                {"key": "hnsw_fast", "name": "HNSW fast", "algorithm": "hnswlib_hnsw", "params": {"M": 8, "ef_construction": 80, "ef_search": 32}},
                {"key": "hnsw_balanced", "name": "HNSW balanced", "algorithm": "hnswlib_hnsw", "params": {"M": 16, "ef_construction": 200, "ef_search": 100}},
                {"key": "hnsw_high", "name": "HNSW high recall", "algorithm": "hnswlib_hnsw", "params": {"M": 24, "ef_construction": 260, "ef_search": 180}},
            ]
            experiment = client.post(
                "/api/index-experiments/task",
                data={
                    "dataset_id": dataset_id,
                    "metric": "l2",
                    "sample_size": 5,
                    "top_k": 3,
                    "repetitions": 1,
                    "warmup_count": 1,
                    "candidate_configs": json.dumps(experiment_candidates),
                },
            )
            assert experiment.status_code == 200
            experiment_task_id = experiment.get_json()["task_id"]
            experiment_id = experiment.get_json()["experiment_id"]
            experiment_payload = _wait_for_task(client, experiment_task_id, timeout=60)
            assert experiment_payload["status"] == "success", experiment_payload.get("error")
            experiment_result = experiment_payload["result"]["experiment"]
            assert experiment_result["candidate_count"] == len(experiment_candidates)
            assert experiment_result["status"] == "ready_for_selection"
            assert experiment_result["exact_baseline"]["avg_query_time_ms"] is not None
            assert all(row["status"] == "success" for row in experiment_result["runs"])
            assert all(row["index"]["lifecycle"] == "candidate" for row in experiment_result["runs"])

            experiments = client.get(f"/api/index-experiments?dataset_id={dataset_id}")
            assert experiments.status_code == 200
            assert any(row["id"] == experiment_result["id"] for row in experiments.get_json()["experiments"])

            # A focused deployment may retain only the single best candidate.
            selected_run_ids = [experiment_result["runs"][0]["id"]]
            candidate_index_ids = [row["index"]["id"] for row in experiment_result["runs"]]
            candidate_search = client.post(
                "/api/search",
                data={"dataset_id": dataset_id, "index_id": candidate_index_ids[0], "query_cell_index": 0, "top_k": 5},
            )
            assert candidate_search.status_code == 400
            finalize = client.post(
                f"/api/index-experiments/{experiment_id}/finalize",
                data={"selected_run_ids": selected_run_ids},
            )
            assert finalize.status_code == 200, finalize.get_json()
            finalization = finalize.get_json()["finalization"]
            selected_candidate_index_ids = {candidate_index_ids[0]}
            assert {row["id"] for row in finalization["active_indexes"]} == selected_candidate_index_ids
            assert index_id in finalization["discarded_index_ids"]
            assert rp_index_id in finalization["discarded_index_ids"]
            assert candidate_index_ids[1] in finalization["discarded_index_ids"]
            assert candidate_index_ids[2] in finalization["discarded_index_ids"]

            # Repeating the same finalization is idempotent and does not rebuild indexes.
            repeated_finalize = client.post(
                f"/api/index-experiments/{experiment_id}/finalize",
                data={"selected_run_ids": selected_run_ids},
            )
            assert repeated_finalize.status_code == 200
            assert {row["id"] for row in repeated_finalize.get_json()["finalization"]["active_indexes"]} == selected_candidate_index_ids
            changed_finalize = client.post(
                f"/api/index-experiments/{experiment_id}/finalize",
                data={"selected_run_ids": [experiment_result["runs"][1]["id"]]},
            )
            assert changed_finalize.status_code == 409

            db.session.expire_all()
            retired = [db.session.get(AnnIndex, value) for value in [index_id, rp_index_id, candidate_index_ids[1], candidate_index_ids[2]]]
            assert all(row.lifecycle == "discarded" and row.status == "deleted" for row in retired)
            assert all(not os.path.exists(os.path.join(app.config["INDEX_DIR"], row.index_path)) for row in retired)
            assert all(db.session.get(AnnIndex, value).lifecycle == "active" for value in selected_candidate_index_ids)
            assert QueryLog.query.filter_by(index_id=rp_index_id).count() == 1
            assert QueryLog.query.filter_by(index_id=rp_index_id).first().user_id == user.id

            source_run = experiment_result["runs"][0]
            source_index_id = source_run["index"]["id"]
            index_id = source_index_id

            source_dataset_detail = client.get(f"/api/datasets/{dataset_id}")
            assert source_dataset_detail.status_code == 200
            assert {row["id"] for row in source_dataset_detail.get_json()["dataset"]["indexes"]} == selected_candidate_index_ids
            source_index = next(row for row in source_dataset_detail.get_json()["dataset"]["indexes"] if row["id"] == source_index_id)
            assert source_index["source_experiment_id"] == experiment_result["id"]
            assert source_index["source_run_id"] == source_run["id"]
            assert source_index["source_run"]["recall_at_k"] == source_run["recall_at_k"]

            evaluation = client.post(
                "/api/index-evaluations/task",
                data={
                    "dataset_id": dataset_id,
                    "index_id": index_id,
                    "sample_size": 5,
                    "top_k": 3,
                    "seed": 42,
                },
            )
            assert evaluation.status_code == 200
            evaluation_task_id = evaluation.get_json()["task_id"]
            evaluation_payload = _wait_for_task(client, evaluation_task_id, timeout=60)
            assert evaluation_payload["status"] == "success", evaluation_payload.get("error")
            evaluation_result = evaluation_payload["result"]["evaluation"]
            assert evaluation_result["index_id"] == index_id
            assert evaluation_result["seed"] == 42
            assert evaluation_result["p95_query_time_ms"] is not None
            assert evaluation_result["speedup"] is not None
            assert evaluation_result["quality"] in {"excellent", "acceptable", "low_recall", "not_recommended"}

            evaluations = client.get(f"/api/index-evaluations?dataset_id={dataset_id}")
            assert evaluations.status_code == 200
            assert any(row["id"] == evaluation_result["id"] for row in evaluations.get_json()["evaluations"])
            evaluation_detail = client.get(f"/api/index-evaluations/{evaluation_result['id']}")
            assert evaluation_detail.status_code == 200
            assert evaluation_detail.get_json()["evaluation"]["sample_size"] == 5

            search_task = client.post(
                "/api/search/task",
                data={"dataset_id": dataset_id, "index_id": index_id, "query_cell_index": 0, "top_k": 5},
            )
            assert search_task.status_code == 200
            search_task_payload = _wait_for_task(client, search_task.get_json()["task_id"])
            assert search_task_payload["status"] == "success"
            search_results = search_task_payload["result"]["result_data"]["results"]
            assert len(search_results) == 5
            assert "scatter_plot" not in search_task_payload["result"]

            plot_task = client.post(
                "/api/search/plot/task",
                data={
                    "dataset_id": dataset_id,
                    "query_cell_index": 0,
                    "result_cell_indices": ",".join(str(row["cell_index"]) for row in search_results),
                },
            )
            assert plot_task.status_code == 200
            plot_task_id = plot_task.get_json()["task_id"]
            plot_payload = _wait_for_task(client, plot_task_id)
            assert plot_payload["status"] == "success"
            search_plot = plot_payload["result"]["scatter_plot"]
            assert search_plot["data"]
            assert search_plot["metadata"]["legend"]["default_dimension"] == "cell_type"
            assert all(trace.get("x") != [None] for trace in search_plot["data"])

            task_list = client.get("/api/tasks?status=all&limit=30")
            assert task_list.status_code == 200
            task_rows = task_list.get_json()["tasks"]
            assert any(row["id"] == plot_task_id and row["has_result"] for row in task_rows)
            assert any(row["id"] == experiment_task_id and row["has_result"] for row in task_rows)
            assert any(row["id"] == evaluation_task_id and row["has_result"] for row in task_rows)
            assert all(row["result"] is None for row in task_rows)

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
            dataset_plot = scatter.get_json()["scatter_plot"]
            assert len(dataset_plot["data"]) == 1
            assert set(dataset_plot["metadata"]["legend"]["dimensions"]) == {"cell_type", "disease", "age_group"}
            assert dataset_plot["layout"]["showlegend"] is False

            db.session.remove()
            db.engine.dispose()


def test_joint_index_build_search_plot_and_access_control():
    import anndata as ad
    from app.extensions import db
    from app.models import Dataset, JointQueryLog, User
    from scripts.create_demo_h5ad import create_demo_h5ad

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        app = _make_app(tmpdir)
        with app.app_context():
            db.create_all()
            admin = User(username="admin", role="admin")
            admin.set_password("pass1234")
            user = User(username="guest", role="user")
            user.set_password("pass1234")
            db.session.add_all([admin, user])
            db.session.commit()

            raw_dir = os.path.join(tmpdir, "raw")
            paths = [
                os.path.join(raw_dir, "joint_a.h5ad"),
                os.path.join(raw_dir, "joint_b.h5ad"),
                os.path.join(raw_dir, "joint_incompatible.h5ad"),
            ]
            for path in paths:
                create_demo_h5ad(path)
            incompatible = ad.read_h5ad(paths[2])
            incompatible.var_names = [f"other_gene_{i:03d}" for i in range(incompatible.n_vars)]
            incompatible.write_h5ad(paths[2])

            datasets = []
            for idx, path in enumerate(paths, 1):
                dataset = Dataset(
                    name=f"joint_demo_{idx}",
                    description="joint index test",
                    file_path=path,
                    status="uploaded",
                    owner_id=admin.id,
                    visibility="private",
                )
                db.session.add(dataset)
                datasets.append(dataset)
            db.session.commit()
            dataset_ids = [dataset.id for dataset in datasets]

            client = app.test_client()
            login = client.post("/api/auth/login", data={"username": "admin", "password": "pass1234"})
            assert login.status_code == 200

            for dataset_id in dataset_ids:
                process = client.post(f"/api/datasets/{dataset_id}/process")
                assert process.status_code == 200
                process_task = _wait_for_task(client, process.get_json()["task_id"])
                assert process_task["status"] == "success"
            db.session.expire_all()

            build_joint = client.post(
                "/api/joint-indexes/build/task",
                data={
                    "name": "test harmony joint",
                    "dataset_ids": [str(dataset_id) for dataset_id in dataset_ids],
                    "metric": "l2",
                    "M": 8,
                    "ef_construction": 80,
                    "ef_search": 50,
                    "n_pcs": 10,
                    "n_top_genes": 50,
                    "min_common_genes": 20,
                },
            )
            assert build_joint.status_code == 200
            build_payload = _wait_for_task(client, build_joint.get_json()["task_id"], timeout=90)
            assert build_payload["status"] == "success", build_payload.get("error")
            joint_index = build_payload["result"]["joint_index"]
            joint_index_id = joint_index["id"]
            included = [row for row in joint_index["datasets"] if row["status"] == "included"]
            skipped = [row for row in joint_index["datasets"] if row["status"] == "skipped"]
            assert len(included) == 2
            assert len(skipped) == 1
            assert joint_index["n_cells"] == 800

            search_joint = client.post(
                "/api/search/joint/task",
                data={
                    "joint_index_id": joint_index_id,
                    "query_dataset_id": dataset_ids[0],
                    "query_cell_index": 0,
                    "top_k": 5,
                },
            )
            assert search_joint.status_code == 200
            search_payload = _wait_for_task(client, search_joint.get_json()["task_id"])
            assert search_payload["status"] == "success", search_payload.get("error")
            result_data = search_payload["result"]["result_data"]
            assert result_data["query_global_label"] == 0
            assert len(result_data["results"]) == 5
            assert all(row["global_label"] != result_data["query_global_label"] for row in result_data["results"])
            assert JointQueryLog.query.filter_by(joint_index_id=joint_index_id).first().user_id == admin.id

            plot_joint = client.post(
                "/api/search/joint/plot/task",
                data={
                    "joint_index_id": joint_index_id,
                    "query_global_label": result_data["query_global_label"],
                    "result_global_labels": ",".join(str(row["global_label"]) for row in result_data["results"]),
                    "max_background_points": 1000,
                },
            )
            assert plot_joint.status_code == 200
            plot_task_id = plot_joint.get_json()["task_id"]
            plot_payload = _wait_for_task(client, plot_task_id)
            assert plot_payload["status"] == "success", plot_payload.get("error")
            joint_plot = plot_payload["result"]["scatter_plot"]
            assert joint_plot["data"]
            assert joint_plot["metadata"]["legend"]["default_dimension"] == "dataset"
            assert all(trace.get("x") != [None] for trace in joint_plot["data"])

            task_list = client.get("/api/tasks?status=all&limit=50")
            rows = task_list.get_json()["tasks"]
            assert any(row["id"] == plot_task_id and row["has_result"] for row in rows)
            assert all(row["result"] is None for row in rows)

            client.post("/api/auth/logout")
            guest_login = client.post("/api/auth/login", data={"username": "guest", "password": "pass1234"})
            assert guest_login.status_code == 200
            forbidden = client.get(f"/api/joint-indexes/{joint_index_id}")
            assert forbidden.status_code == 403

            db.session.remove()
            db.engine.dispose()
