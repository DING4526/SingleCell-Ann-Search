import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import create_app
from app.extensions import db
from app.models import Dataset, User

app = create_app()

with app.app_context():
    file_path = os.path.abspath("data/raw/liver.h5ad")

    if not os.path.exists(file_path):
        raise FileNotFoundError(f"找不到文件: {file_path}")

    existing = Dataset.query.filter_by(file_path=file_path).first()
    admin = User.query.filter_by(username="admin").first()
    owner_id = admin.id if admin else None

    if existing:
        changed = False
        if existing.owner_id is None and owner_id is not None:
            existing.owner_id = owner_id
            changed = True
        if existing.visibility != "shared":
            existing.visibility = "shared"
            changed = True
        if changed:
            db.session.commit()
        print(f"数据集已存在: id={existing.id}, name={existing.name}, status={existing.status}")
        print(f"权限信息: owner_id={existing.owner_id or '未归属'}, visibility={existing.visibility}")
    else:
        dataset = Dataset(
            name="liver",
            description="真实 liver.h5ad 单细胞数据集",
            file_path=file_path,
            status="uploaded",
            owner_id=owner_id,
            visibility="shared",
        )
        db.session.add(dataset)
        db.session.commit()
        print(f"已注册数据集: id={dataset.id}, file_path={dataset.file_path}")
        print(f"权限信息: owner_id={dataset.owner_id or '未归属'}, visibility={dataset.visibility}")
