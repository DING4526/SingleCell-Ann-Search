# 单细胞 ANN 检索系统

基于 Flask + Vue 3 的单细胞近似最近邻检索平台，用于读取 `.h5ad` 数据集、提取 PCA 向量、构建 HNSW 索引，并支持 Top-K 相似细胞检索、跨数据集检索、可视化和评估。

前端已重构为专业研究者平台式 SPA，核心页面包括 Overview、Datasets、Index Lab、Query Lab、Evaluation、Access、AI Analysis。

## 技术栈

- 后端：Flask, Flask-Login, Flask-SQLAlchemy
- 前端：Vue 3, Vite, TypeScript, Pinia, Vue Router, Ant Design Vue
- 数据库：SQLite + SQLAlchemy
- 数据处理：Scanpy, AnnData, NumPy, Pandas
- ANN 索引：HNSWLIB
- 可视化：Plotly
- 测试：pytest, vue-tsc, Vite build

## 目录结构

```text
single-cell-ann-search/
├── app/
│   ├── __init__.py          # Flask 应用工厂
│   ├── config.py            # 配置
│   ├── extensions.py        # db, login_manager
│   ├── models.py            # User, Dataset, Cell, AnnIndex, QueryLog, Task
│   ├── routes/              # 页面路由与 API 路由
│   ├── services/            # 数据处理、索引、评估、绘图服务
│   ├── spa.py               # Flask 托管 Vite SPA
│   ├── templates/           # 旧 Jinja 模板，保留部分兼容页面
│   └── static/              # 旧静态资源
├── frontend/
│   ├── src/                 # Vue 3 SPA 源码
│   ├── package.json         # 前端依赖与脚本
│   └── dist/                # 前端构建产物，本地生成，不提交
├── data/
│   ├── raw/                 # 上传的 h5ad 文件
│   ├── cache/               # 缓存的 npy 向量
│   └── indexes/             # HNSW 索引文件
├── instance/                # SQLite 数据库，本地生成，不提交
├── scripts/
│   ├── init_db.py           # 初始化数据库
│   ├── seed_admin.py        # 创建管理员用户
│   └── create_demo_h5ad.py  # 生成 demo 数据集
├── tests/
├── requirements.txt
├── run.py
└── README.md
```

## 环境要求

- Python 3.10 推荐
- Node.js 18+ 推荐
- Windows PowerShell、Git Bash 或 macOS/Linux Shell 均可

以下命令默认在项目根目录执行：

```powershell
cd D:\03_Courses\3_2_01_Software_Engineering\lab5_final\single-cell-ann-search
```

## 首次初始化

### 1. 创建 Python 虚拟环境

PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

如果使用 conda：

```powershell
conda create -n sc-ann python=3.10
conda activate sc-ann
```

### 2. 安装后端依赖

```powershell
pip install -r requirements.txt
```

### 3. 初始化数据库

```powershell
python scripts/init_db.py
```

### 4. 创建管理员账号

```powershell
python scripts/seed_admin.py
```

默认管理员账号：

```text
用户名：admin
密码：admin123
```

### 5. 生成 demo 数据

```powershell
python scripts/create_demo_h5ad.py
```

生成后可在平台中上传：

```text
data/raw/demo_liver.h5ad
```

### 6. 安装前端依赖

```powershell
cd frontend
npm install
cd ..
```

## 本地浏览器运行

本项目支持两种本地运行方式。

### 方式 A：生产构建模式，推荐用于演示和验收

先构建前端 SPA，再由 Flask 托管静态文件：

```powershell
cd frontend
npm run build
cd ..
python run.py
```

然后在本地浏览器打开：

```text
http://127.0.0.1:5000
```

登录：

```text
admin / admin123
```

这个模式最接近课程演示和部署形态。Flask 会返回 Vue SPA，并继续提供 `/api/*` 接口。

### 方式 B：前端开发模式，推荐用于改 UI

开两个终端。

终端 1：启动 Flask API：

```powershell
.\.venv\Scripts\Activate.ps1
python run.py
```

终端 2：启动 Vite：

```powershell
cd frontend
npm run dev
```

然后在本地浏览器打开：

```text
http://127.0.0.1:5173
```

Vite 会把 `/api` 请求代理到 Flask，因此前端热更新更快，适合继续调页面、交互和组件。

## 常见初始化问题

### PowerShell 不允许激活虚拟环境

如果 `Activate.ps1` 被执行策略拦截，可以在当前 PowerShell 会话中执行：

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

### 访问页面看到旧内容或资源 404

生产构建模式下需要先执行：

```powershell
cd frontend
npm run build
cd ..
python run.py
```

如果刚改过前端但仍看到旧页面，重跑 `npm run build` 后刷新浏览器。

### 端口被占用

默认端口：

```text
Flask: 5000
Vite: 5173
```

如果端口被占用，先关闭旧的 Python 或 Node 进程，再重新启动。

## 演示流程

1. 打开 `http://127.0.0.1:5000` 或 `http://127.0.0.1:5173`
2. 使用 `admin / admin123` 登录
3. 进入 Datasets，上传 `data/raw/demo_liver.h5ad`
4. 在数据集详情页处理数据集，提取向量和细胞元信息
5. 查看数据集统计信息和 UMAP/PCA 可视化
6. 进入 Index Lab，选择数据集并构建 HNSW 索引
7. 进入 Query Lab，选择数据集和索引
8. 输入查询细胞索引，例如 `0`
9. 设置 Top-K，例如 `10`
10. 运行检索并查看结果表格、耗时和散点图联动
11. 可选：使用跨数据集检索
12. 进入 Evaluation，对比 ANN 与精确检索的 Recall@K、耗时和加速比

## 验证命令

后端测试：

```powershell
pytest tests -q
```

前端类型检查：

```powershell
cd frontend
npm run typecheck
```

前端生产构建：

```powershell
cd frontend
npm run build
```

前端生产依赖安全检查：

```powershell
cd frontend
npm audit --omit=dev
```

## 后续扩展方向

- 多 ANN 算法选择：FAISS IVF/PQ/HNSW 参数实验
- 索引合并：多数据集物理联合索引与全局 cell id
- 权限管理：用户、共享、数据集可见性和操作权限
- 大模型集成：自然语言查询、RAG 分析和检索结果解释
- 批量查询与结果导出
- Plotly 按需加载，降低首屏构建包体积
