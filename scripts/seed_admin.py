"""创建管理员用户。"""
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import create_app
from app.extensions import db
from app.models import User

app = create_app()
with app.app_context():
    if User.query.filter_by(username="admin").first():
        print("管理员用户已存在。")
    else:
        admin = User(username="admin", role="admin")
        admin.set_password("admin123")
        db.session.add(admin)
        db.session.commit()
        print("管理员用户已创建: admin / admin123")
