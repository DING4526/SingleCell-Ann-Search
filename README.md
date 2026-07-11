# 单细胞 ANN 检索研究平台

一个面向单细胞转录组数据的可视化近似最近邻检索工作台。平台读取 AnnData `.h5ad` 文件，使用 PCA 向量构建 HNSW/FAISS 索引，并提供单数据集检索、跨数据集 Fan-out、Harmony 联合索引、UMAP 高亮、算法评估、权限管理和可选 AI/RAG 助手。

> 当前版本适合课程演示、本地研究和受控内网环境。公网部署前请完成[发布阻断清单](docs/发布阻断清单.md)。

## 主要能力

- 上传和处理 `.h5ad`，浏览细胞、基因、PCA 与元数据统计。
- 在 UMAP/PCA 图中按细胞类型、疾病和年龄组着色并查看细胞详情。
- 比较 HNSW、随机投影 HNSW、FAISS IVF-Flat、IVF-PQ 等候选索引。
- 使用 Recall@K、平均/P95 时延、构建耗时和索引体积选择正式索引。
- 执行单数据集 Top-K、多个独立索引 Fan-out 和 Harmony 联合空间检索。
- 通过 Viewer、Editor、Owner 和 Admin 管理数据访问与审计。
- 安全删除资源、移除历史、跟踪后台任务和重试文件清理。
- 可选配置 OpenAI-compatible 模型、三级知识库和需要用户确认的 AI 操作。

## 快速开始

### 1. 环境要求

- Python 3.10+
- Node.js 20.19+、22.12+ 或 24.x
- Git 2.x
- 推荐 Chromium 内核桌面浏览器，界面基线为 1366×768

以下命令默认在项目根目录执行。

### 2. Clone 项目

```powershell
git clone https://github.com/DING4526/SingleCell-Ann-Search.git
cd SingleCell-Ann-Search
```

### 3. 安装后端

Windows PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

macOS/Linux：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

如果 PowerShell 阻止激活脚本：

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

### 4. 创建本地配置

Windows：

```powershell
Copy-Item .env.example .env
```

macOS/Linux：

```bash
cp .env.example .env
```

至少把 `.env` 中的 `SECRET_KEY` 替换为随机值：

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

AI 功能可以暂不配置，不影响数据、索引和检索主流程。不要提交 `.env` 或真实密钥。

### 5. 初始化数据库和演示数据

```powershell
python scripts/init_db.py
python scripts/seed_admin.py
python scripts/create_demo_h5ad.py
```

这会创建：

- 本地 SQLite 数据库；
- 演示管理员：`admin / admin123`；
- 演示数据：`data/raw/demo_liver.h5ad`。

首次登录后请立即从右上角账号菜单修改默认密码。

### 6. 安装并构建前端

```powershell
cd frontend
npm ci
npm run build
cd ..
```

### 7. 启动平台

```powershell
python run.py
```

打开 <http://127.0.0.1:5000>，使用 `admin / admin123` 登录。

`run.py` 使用 Flask 开发服务器，只用于本地运行和演示。

## 完成第一次检索

1. 打开“数据资源”，上传 `data/raw/demo_liver.h5ad`。
2. 进入数据集详情，点击“处理数据集”，等待任务完成。
3. 查看数据统计和 UMAP；可切换图例、双击独显分类、点击散点查看细胞。
4. 打开“索引实验室”，选择该数据集并运行默认候选实验。
5. 实验完成后选择 1–3 个 Recall 达标的候选，确认保留为现用索引。
6. 打开“检索实验室”，选择“单数据集”、数据集和索引。
7. 输入细胞编号 `0`、Top-K `10`，运行检索。
8. 查看排名表和“嵌入空间高亮”。

后台任务可从页面顶部“任务”入口查看。离开当前业务页面不会主动取消任务。

## 输入数据要求

平台接收 AnnData `.h5ad` 文件。

必须包含：

```python
adata.obsm["X_pca"]  # 二维数值数组，ANN 检索向量
```

推荐包含：

```python
adata.obsm["X_umap"]       # 可选；缺失时使用 PCA 前两维绘图
adata.obs["cell_type"]     # 可选
adata.obs["disease"]       # 可选
adata.obs["AgeGroup"]      # 可选，注意大小写
```

可在上传前检查：

```python
import scanpy as sc

adata = sc.read_h5ad("your_dataset.h5ad")
print(adata.shape)
print(adata.obsm.keys())
print(adata.obs.columns.tolist())
assert "X_pca" in adata.obsm
```

平台上传上限为 3 GiB，但 Scanpy 会在处理阶段读取数据到内存；文件上限不代表普通电脑一定能稳定处理同等规模。

## 三种检索模式

| 模式 | 适用场景 | 说明 |
| --- | --- | --- |
| 单数据集 | 在一个数据集内寻找相似细胞 | 支持细胞类型过滤和 UMAP/PCA 高亮 |
| Fan-out | 同一向量查询多个独立索引 | 要求索引距离度量和向量维度兼容；结果按距离归并 |
| 联合索引 | 多数据集经过公共基因与 Harmony 对齐后检索 | 在统一空间中查询并展示联合 UMAP |

Fan-out 中“维度相同”不等于不同数据集的生物学距离严格可比；正式跨数据集分析优先使用联合索引，并结合研究设计验证结果。

## 前端开发模式

需要修改页面时，打开两个终端。

终端 1：

```powershell
.\.venv\Scripts\Activate.ps1
python run.py
```

终端 2：

```powershell
cd frontend
npm run dev
```

访问 <http://127.0.0.1:5173>。Vite 会把 `/api` 和 `/assets` 代理到 Flask 的 5000 端口。

前端修改不会自动更新 5000 端口使用的生产产物；演示前需重新执行 `npm run build`。

## 可选：配置 AI 与知识库

### 1. 配置凭据加密密钥

```powershell
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

把输出写入 `.env`：

```dotenv
AI_CREDENTIAL_ENCRYPTION_KEY=生成的Fernet密钥
```

该密钥与 Flask `SECRET_KEY` 不同。丢失后已保存的 Provider API Key 无法解密。

### 2. 在平台中启用模型

1. 使用管理员登录。
2. 打开“权限管理 → AI 模型”。
3. 新增 OpenAI-compatible Provider 和 API Key。
4. 新增对话模型或 Embedding 模型。
5. 测试连接，成功后启用模型。
6. 按需开启用户 AI 权限和每日限额。

自定义 Endpoint 默认要求公网 HTTPS。只有明确使用可信内网模型服务时，才考虑设置 `AI_ALLOW_PRIVATE_ENDPOINTS=true`。

知识库支持 PDF、Markdown 和 TXT，分为平台、数据集和个人空间。没有 Embedding 模型时会自动使用中文关键词检索；扫描版 PDF 暂不支持 OCR。

AI 可以生成检索或部分维护操作的草案，但必须由用户确认后执行。删除、权限、所有权、账号、模型和密钥操作不会交给 AI。

## 权限与删除规则

| 数据集角色 | 主要能力 |
| --- | --- |
| Viewer | 查看、统计和检索 |
| Editor | Viewer + 处理、建索引、实验、评估、数据集知识维护 |
| Owner | Editor + 分享、转移所有权、永久删除数据集 |
| Admin | 平台全局管理、账号、审计和 AI 配置 |

删除策略：

- 数据集、普通索引和联合索引：满足权限且无运行任务/依赖时永久删除。
- 任务、检索、实验和评估记录：从历史移除。
- 用户账号：停用，不物理删除。
- 审计日志：保留，不提供删除。
- 文件清理失败：任务中心显示错误，可重试清理。

收到删除冲突提示时，应先处理页面列出的依赖项，不要手工删除 `data/` 文件或直接修改 SQLite。

## 项目结构

```text
single-cell-ann-search/
├─ app/
│  ├─ ai/                 AI、RAG、SSE 和安全
│  ├─ routes/             Flask API 与 SPA 入口
│  ├─ services/           数据、索引、检索、评估、绘图和删除
│  ├─ models.py           SQLAlchemy 数据模型
│  └─ tasks.py            后台任务编排
├─ frontend/              Vue 3 + TypeScript SPA
├─ data/                  上传、缓存、索引和知识文件
├─ instance/              本地 SQLite 数据库
├─ scripts/               初始化、demo 和评测脚本
├─ tests/                 后端测试
├─ docs/                  开发文档与发布说明
├─ requirements.txt
└─ run.py
```

## 验证

后端：

```powershell
python -m pytest -q
```

前端：

```powershell
cd frontend
npm test -- --run
npm run typecheck
npm run build
```

## 常见问题

### 页面显示 503

前端产物尚未生成。停止正在运行的服务后执行：

```powershell
cd frontend
npm run build
cd ..
python run.py
```

### 数据处理提示缺少 `X_pca`

先在 AnnData 中执行 PCA，并把结果保存到 `adata.obsm["X_pca"]` 后重新导出 `.h5ad`。

### 表格已有检索结果，但高亮图仍未出现

结果查询和绘图是两个任务。等待图表任务完成；失败时点击“重新加载”。切换检索模式会清理旧图。

### Fan-out 跳过数据集

检查当前用户是否有查看权限、目标是否存在同距离度量的 ready 索引，以及 PCA 向量维度是否一致。

### Windows 构建提示无法创建 `dist/assets`

先停止旧的 Python/Node 服务，确认 `frontend/dist` 可写，再运行 `npm run build`。

### 端口被占用

默认端口为 Flask 5000、Vite 5173。正常停止旧服务后重新启动。

## 更多文档

- [完整开发文档与用户手册](docs/单细胞ANN检索研究平台开发文档.md)
- [公网部署前发布阻断清单](docs/发布阻断清单.md)
- [AI 平台内置知识](docs/ai-knowledge/)
- [中期开发分工手册](docs/单细胞%20ANN%20检索系统中期开发分工手册.md)

## 生产部署提醒

本项目当前使用 SQLite、本地文件系统、进程内线程池和 Flask 开发服务器。公网或高并发部署前，至少需要生产 WSGI、HTTPS/反向代理、强密钥和独立管理员、持久任务队列、数据库与文件一致备份、上传防护、监控告警及安全评审。详见[发布阻断清单](docs/发布阻断清单.md)。
