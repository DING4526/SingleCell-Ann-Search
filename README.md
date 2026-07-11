# 单细胞 ANN 检索系统

基于 Flask + Vue 3 的单细胞近似最近邻检索平台，用于读取 `.h5ad` 数据集、提取 PCA 向量、比较 HNSW/FAISS 索引，并支持 Top-K 相似细胞检索、跨数据集检索、可视化和评估。

前端已重构为专业研究者平台式 SPA，核心页面包括 Overview、Datasets、Index Lab、Joint Indexes、Query Lab、Access、AI Knowledge 和统一 AI Assistant。

本地开发与课程演示配置不等同于生产配置；对外部署前请逐项完成 [`docs/发布阻断清单.md`](docs/发布阻断清单.md)。

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
│   ├── models.py            # 用户、数据集权限、索引、任务、查询与审计模型
│   ├── routes/              # 页面路由与 API 路由
│   ├── services/            # 数据处理、索引、评估、绘图服务
│   └── spa.py               # Flask 托管 Vite SPA，并提供正式 503 回退页
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
6. 进入 Index Lab，一次构建并统一评估候选索引，选择最终保留的 2–3 个索引
7. 进入 Query Lab，选择数据集和索引
8. 输入查询细胞索引，例如 `0`
9. 设置 Top-K，例如 `10`
10. 运行检索并查看结果表格、耗时和散点图联动
11. 可选：使用跨数据集检索
12. 进入 Access 查看有效权限；Owner 可在数据集详情中配置 Viewer/Editor

## 权限模型

- 系统角色为 `admin / user`；数据集有效角色为 `admin / owner / editor / viewer`。
- `private` 数据集仅 Owner、Admin 和显式成员可见；`shared` 向所有登录用户开放 Viewer。
- Editor 可处理数据、构建和评估索引、完成索引实验以及使用数据构建联合索引。
- 只有 Owner/Admin 可以修改共享范围、管理成员、转移所有权或删除数据集。
- 联合索引构建要求对所有源数据集至少拥有 Editor；查看和查询要求全部源数据集可见。
- Access 页面提供权限总览、管理员用户管理和审计日志；账号停用不会删除资源或历史记录。

## AI 分析第一阶段

平台支持由管理员统一维护 OpenAI、DeepSeek、智谱、Qwen 以及自定义 OpenAI-compatible 服务。普通用户只能选择管理员已测试并启用的模型，无法读取 API Key。

### 1. 配置凭据加密主密钥

先安装依赖并生成 Fernet 密钥：

```powershell
pip install -r requirements.txt
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

复制 `.env.example` 为 `.env`，将输出填写到：

```text
AI_CREDENTIAL_ENCRYPTION_KEY=生成的Fernet密钥
```

此密钥与 Flask `SECRET_KEY` 分离。请备份并避免提交 `.env`；丢失后已保存的模型 API Key 无法解密，只能由管理员重新填写。

### 2. 管理员配置模型

1. 使用管理员账号登录。
2. 进入“权限管理 → AI 模型”。
3. 添加供应商凭据，只在创建或替换时填写 API Key。
4. 添加一个或多个模型 ID，并选择“对话模型”或“Embedding”。
5. 对模型执行连接测试。
6. 测试成功后启用模型，并选择默认模型。
7. 按需设置全局每日请求限额、并发数和单用户 AI 权限。

供应商的“超时（秒）”用于规划、流式解读和 Embedding 调用，新配置默认 180 秒，可在 15–600 秒之间调整。连接失败、429 和 5xx 最多透明重试一次；模型增强失败不会改变已经成功的检索结果。

Qwen 默认提供中国区 Endpoint，并允许填写国际区或 Workspace 专属 Endpoint。自定义 Endpoint 默认必须使用公网 HTTPS；只有明确设置 `AI_ALLOW_PRIVATE_ENDPOINTS=true` 才允许可信内网模型服务。

### 3. 第二阶段 AI 分析与 RAG

进入“AI 助手”，选择可用模型并输入例如：

```text
在 demo_liver 中找到与 123 号细胞最相似的 20 个 Hepatocyte，并解释疾病和年龄组分布。
```

平台会根据请求生成最多四步的 `AnalysisPlan`，在单数据集、Fan-out 和联合索引中选择合法模式。用户可以修改模式、数据集、索引、细胞编号、Top-K 和目标数据集；所有 ANN 步骤整份确认一次，确认前不会创建检索 Task。

ANN 完成后，助手立即返回带实际统计值的中文回答；模型的简短定性解读通过 SSE 流式追加，并在结束时校验中文、数字和引用。Evidence Key、RAG 片段和内部工具步骤默认隐藏，完整结果表和高亮图统一在 Query Lab 展示。

同一会话会继承最近一次有效检索状态，并使用受限的近期消息和结果摘要理解“再查 1 号”一类相对指令。针对上一轮结果的解释性问题会直接基于已保存证据回答，不会重复执行 ANN。

Query Lab 的“检索历史”统一包含人工单数据集、Fan-out、联合索引和 AI 检索。通过 AI 回答中的按钮进入 Query Lab 时，会直接恢复已保存的参数和结果，只异步生成高亮图，不会再次执行 ANN。

### 4. AI 知识库

“AI 知识库”支持 PDF、Markdown 和 TXT，分为平台、数据集和个人三级空间。中文字符关键词检索始终可用；管理员可以使用现有供应商凭据另外配置并测试 Embedding 模型，测试成功后文档会建立语义向量。没有 Embedding 或向量重建失败时自动降级为关键词检索。

内置知识来自 `docs/ai-knowledge/`，包含平台入门、索引选择、AI 证据规则和故障排查。数据集、索引和权限清单在每次提问时实时读取，不固化到文档中。

第二阶段的 RAG 范围不包含公网搜索、OCR 和基因差异表达；全局平台助手与受审批写操作由第三阶段提供。

## 统一 AI 助手

登录后可从任意页面右下角打开 AI 助手，也可以进入 `/ai-assistant` 使用完整工作台。助手会自动附带脱敏页面上下文，在同一会话中完成平台问答、受控页面导航、Query Lab/Index Lab 预填和可确认的科学检索。旧 `/ai-analysis` 链接会兼容跳转到统一助手，历史分析会话继续可用。

数据处理、索引构建/实验/评估、联合索引和知识维护只会生成待确认操作卡。用户确认后，后端重新校验权限和资源状态并复用现有 Task 服务；删除、权限、所有权、账号、模型和密钥操作不向 AI 开放。

默认回答以简体中文为主体。明确导航、科学移交和敏感操作拒绝使用确定性快路径；其余问题结合平台实时资源与三级 RAG，由模型生成并经过中文、数字、引用和工具权限校验。

开发者可运行脱敏真实模型评测：

```powershell
.venv\Scripts\python.exe scripts\evaluate_ai_quality.py --provider qwen --limit 5
```

评测读取管理员已加密保存且测试启用的模型，不创建用户会话或真实写任务；原始输出目录已加入 Git 忽略规则。

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
- 索引合并：Harmony 对齐后的多数据集物理联合索引、全局 cell id 与联合高亮图
- 外部专业文献检索、OCR、marker gene 与差异表达分析
- 批量查询与结果导出
- Plotly 按需加载，降低首屏构建包体积
