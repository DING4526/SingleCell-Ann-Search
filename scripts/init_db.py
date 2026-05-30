"""初始化 SQLite 数据库，创建所有表结构。"""
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import create_app
from app.extensions import db

app = create_app()
with app.app_context():
    db.create_all()
    print("数据库初始化成功。")
