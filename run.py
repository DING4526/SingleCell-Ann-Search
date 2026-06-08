import time
import mimetypes
from flask import request
from app import create_app

mimetypes.add_type("text/css", ".css")
mimetypes.add_type("application/javascript", ".js")

app = create_app()

# 每次启动生成一个静态资源版本号
app.config["STATIC_VERSION"] = str(int(time.time()))
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0


@app.context_processor
def inject_static_version():
    return {
        "static_version": app.config["STATIC_VERSION"]
    }


@app.after_request
def improve_dev_static_response(response):
    if request.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        response.headers.pop("ETag", None)
        response.headers.pop("Last-Modified", None)

        if request.path.endswith(".css"):
            response.headers["Content-Type"] = "text/css; charset=utf-8"
            response.headers.pop("Content-Disposition", None)

        elif request.path.endswith(".js"):
            response.headers["Content-Type"] = "application/javascript; charset=utf-8"
            response.headers.pop("Content-Disposition", None)

    return response


if __name__ == "__main__":
    app.run(debug=True)