import os
from flask import current_app, send_from_directory


def frontend_dist_dir() -> str:
    """Return the Vue production build directory."""
    return os.path.abspath(os.path.join(current_app.root_path, "..", "frontend", "dist"))


def render_spa():
    """Serve the built SPA entrypoint, or a small fallback during development."""
    dist_dir = frontend_dist_dir()
    index_path = os.path.join(dist_dir, "index.html")
    if os.path.exists(index_path):
        return send_from_directory(dist_dir, "index.html")

    return (
        "<!doctype html><meta charset='utf-8'>"
        "<title>Single Cell ANN Research Platform</title>"
        "<main style='font-family:system-ui,sans-serif;padding:32px;"
        "max-width:760px;margin:auto;color:#1f2937'>"
        "<h1>Frontend build is not available</h1>"
        "<p>Run <code>npm install</code> and <code>npm run build</code> "
        "inside <code>frontend/</code>, or use the Vite dev server.</p>"
        "</main>",
        200,
        {"Content-Type": "text/html; charset=utf-8"},
    )


def serve_spa_asset(filename: str):
    dist_dir = frontend_dist_dir()
    mimetype = None
    if filename.endswith(".js"):
        mimetype = "application/javascript"
    elif filename.endswith(".css"):
        mimetype = "text/css"
    return send_from_directory(os.path.join(dist_dir, "assets"), filename, mimetype=mimetype)
