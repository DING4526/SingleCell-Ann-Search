# 单细胞 ANN 检索系统

基于高维向量的单细胞近似最近邻检索平台

基于 Flask 的 Web 系统，用于读取 `.h5ad` 单细胞数据、提取 PCA 向量、使用 HNSWLIB 构建索引，并支持 Top-K 相似细胞检索与交互式可视化。

## 技术栈

- **后端**: Flask, Flask-Login, Flask-SQLAlchemy
- **前端**: Vue 3, Vite, TypeScript, Ant Design Vue
- **数据库**: SQLite + SQLAlchemy
- **数据处理**: Scanpy, AnnData, NumPy, Pandas
- **ANN 索引**: HNSWLIB
- **可视化**: Plotly
- **测试**: pytest

## 主要功能

- 用户注册、登录、退出
- 上传并处理 `.h5ad` 单细胞数据集
- 提取 PCA 向量并缓存为 `.npy`
- 将细胞元信息（cell_type、disease、AgeGroup）保存到 SQLite
- 构建 HNSW 近似最近邻索引
- Top-K 相似细胞检索并展示查询耗时
- 支持按细胞类型过滤检索结果
- 专业研究者平台式 SPA：Overview、Datasets、Index Lab、Query Lab、Evaluation、Access、AI Analysis
- UMAP/PCA 散点图可视化，高亮查询细胞和结果细胞
- 性能评估：ANN vs 精确检索的 Recall@K 和加速比

## 目录结构

```
single-cell-ann-search/
├── app/
│   ├── __init__.py          # Flask 应用工厂
│   ├── config.py            # 配置
│   ├── extensions.py        # db, login_manager
│   ├── models.py            # User, Dataset, Cell, AnnIndex, QueryLog
│   ├── routes/
│   │   ├── main.py          # 首页、文档页
│   │   ├── auth.py          # 登录、注册
│   │   ├── datasets.py      # 上传、处理、详情、建索引
│   │   └── search.py        # 检索、评估
│   ├── services/
│   │   ├── data_service.py  # h5ad 读取、PCA 提取
│   │   ├── ann_service.py   # HNSW 构建、加载、查询
│   │   ├── eval_service.py  # 精确检索、Recall@K
│   │   └── plot_service.py  # Plotly 图表
│   ├── templates/           # Jinja2 HTML 模板
│   └── static/css/          # 样式文件
├── frontend/
│   ├── src/                 # Vue 3 SPA 源码
│   ├── package.json         # 前端依赖与构建脚本
│   └── dist/                # 前端构建产物（本地生成，不提交）
├── data/
│   ├── raw/                 # 上传的 h5ad 文件
│   ├── cache/               # 缓存的 npy 向量
│   └── indexes/             # HNSW 索引文件
├── scripts/
│   ├── init_db.py           # 初始化数据库
│   ├── seed_admin.py        # 创建管理员用户
│   └── create_demo_h5ad.py  # 生成 demo 数据集
├── tests/
│   ├── test_data_service.py
│   └── test_ann_service.py
├── requirements.txt
├── run.py
└── README.md
```

## 安装与运行

### 1. 创建并激活 conda/venv 虚拟环境

```bash
conda create -n sc-ann python=3.10
conda activate sc-ann
```

```
python -m venv .venv
.venv\Scripts\Activate.ps1
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 初始化数据库

```bash
python scripts/init_db.py
```

### 4. （可选）创建管理员用户

```bash
python scripts/seed_admin.py
```

预置管理员账号：`admin` / `admin123`

### 5. 生成 demo 数据

```bash
python scripts/create_demo_h5ad.py
```

### 6. 启动项目

如果只是运行后端 API：

```bash
python run.py
```

如果需要使用新版 SPA，需要先构建前端：

```bash
cd frontend
npm install
npm run build
cd ..
python run.py
```

在浏览器中打开 http://localhost:5000

开发前端时可使用 Vite 代理 Flask API：

```bash
python run.py
cd frontend
npm run dev
```

然后访问 http://localhost:5173

## 演示流程

1. 注册新账号并登录
2. 进入 **Datasets**，上传 `data/raw/demo_liver.h5ad`
3. 在数据集详情页处理数据集，提取向量和细胞元信息
4. 查看数据集统计信息和 UMAP/PCA 可视化
5. 进入 **Index Lab** 构建 HNSW 索引（默认：L2, M=16）
6. 进入 **Query Lab**
7. 选择数据集和索引
8. 输入查询细胞索引（例如 `0`），设置 Top-K（例如 `10`）
9. 点击**检索**查找相似细胞
10. 查看结果表格、查询耗时和散点图
11. 可选：按细胞类型过滤
12. 进入 **Evaluation** 对比 ANN 与精确检索的性能（Recall@K、加速比）

## 运行测试

```bash
pytest tests/ -v
```

前端验证：

```bash
cd frontend
npm run typecheck
npm run build
npm audit --omit=dev
```

## 小组分工建议（3 人团队）

| 角色 | 负责内容 |
|------|---------|
| 组长 | 整体架构设计与维护、Flask 框架搭建、数据库模型、路由集成、代码审查、部署、开发文档撰写、最终汇报 |
| 组员 A | 数据处理服务（data_service）、HNSW 索引服务（ann_service）、评估服务（eval_service）、demo 数据生成、单元测试、参数对比实验 |
| 组员 B | 前端模板开发、Plotly 可视化增强、检索交互 UI、CSS 样式优化、用户验收测试、演示视频录制 |

## 后续扩展方向

- 支持多种 ANN 算法（IVF、PQ）
- 支持向量输入查询（不限于细胞索引）
- 跨数据集联合检索
- 批量查询支持
- 结果导出为 CSV
- 管理员用户管理面板
