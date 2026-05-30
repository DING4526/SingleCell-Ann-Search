# 单细胞 ANN 检索系统中期开发分工手册

## 1. 手册目标

本手册用于规范小组三人在中期提交前的开发协作方式，明确 Git 管理规则、分支合并流程、成员任务边界、阶段性开发节奏和中期验收标准。

当前项目已经具备单细胞 `.h5ad` 数据读取、PCA 向量提取、HNSW 索引构建、Top-K 相似细胞检索、UMAP/PCA 可视化和基础性能评估能力。中期阶段的核心目标不是大规模重构，而是保证系统稳定可运行、功能链路完整、页面展示清晰、Git 提交记录规范，并能支撑 5–8 分钟课堂展示。

------

## 2. 中期开发总目标

中期提交前，项目需要形成一个稳定版本，能够完整演示以下流程：

1. 用户注册、登录、退出。
2. 上传或注册 `.h5ad` 单细胞数据集。
3. 处理数据集，提取 `X_pca` 向量并保存细胞元信息。
4. 构建 HNSW 近似最近邻索引。
5. 根据查询细胞编号执行 Top-K 相似细胞检索。
6. 返回相似细胞编号、细胞名称、细胞类型、疾病信息、年龄组和距离。
7. 展示查询耗时、索引状态和检索结果。
8. 使用 UMAP/PCA 散点图高亮查询细胞和结果细胞。
9. 运行基础评估，对比 ANN 检索和精确检索的 Recall@K、耗时和加速比。
10. GitHub 仓库具有清晰提交记录，README 能指导安装、运行、测试和演示。

中期阶段不追求功能数量，而追求“能稳定跑通、能清楚展示、能讲明白代码逻辑”。

------

## 3. Git 分支管理规则

### 3.1 主分支说明

项目统一采用以下分支结构：

```text
main        稳定提交分支，只放可展示、可提交版本
dev         日常集成分支，所有成员功能先合并到 dev
feature/*   成员个人开发分支，用于具体功能开发
fix/*       问题修复分支，用于修复 bug
docs/*      文档分支，用于 README、说明文档、展示材料
```

### 3.2 分支权限规则

1. `main` 分支只由项目负责人维护。
2. 任何成员不得直接向 `main` 提交代码。
3. 所有功能开发必须先从 `dev` 拉出个人分支。
4. 成员完成任务后，通过 Pull Request 合并到 `dev`。
5. `dev -> main` 只由项目负责人执行。
6. 中期展示前，项目负责人从 `dev` 合并稳定版本到 `main`，并打中期版本标签。

推荐标签：

```text
v0.1-midterm
```

------

## 4. 开发分支命名规范

每个成员开发时，从最新 `dev` 分支拉出自己的功能分支。

### 4.1 功能分支

```bash
git checkout dev
git pull origin dev
git checkout -b feature/成员名-功能名
```

示例：

```text
feature/a-ann-stability
feature/b-ui-demo
feature/c-docs-integration
```

### 4.2 修复分支

```text
fix/search-param-validation
fix/demo-data-error
fix/index-build-error
```

### 4.3 文档分支

```text
docs/midterm-guide
docs/readme-update
docs/demo-script
```

------

## 5. Pull Request 规则

### 5.1 PR 合并方向

所有 PR 统一合并到：

```text
dev
```

禁止直接向 `main` 发 PR。

### 5.2 PR 内容要求

每个 PR 必须写清楚以下内容：

```text
1. 本次 PR 做了什么
2. 修改了哪些主要文件
3. 如何测试
4. 是否影响其他成员模块
5. 是否需要数据库重新初始化
6. 是否需要重新生成 demo 数据
```

PR 描述模板：

~~~markdown
## 本次修改内容

- 

## 主要修改文件

- 

## 测试方式

```bash
python run.py
pytest tests/ -v
~~~

## 影响范围

-  不影响其他模块
-  影响数据处理
-  影响索引构建
-  影响检索页面
-  影响数据库结构
-  影响 README 或演示流程

## 备注

- 

```
### 5.3 PR 合并要求

1. PR 至少由项目负责人检查后再合并。
2. 如果 PR 修改了公共文件，必须说明原因。
3. 如果 PR 修改了数据库模型，需要提前通知全组。
4. 如果 PR 修改了 `requirements.txt`，需要说明新增依赖用途。
5. 如果 PR 会导致原有 demo 流程变化，需要同步更新 README 或演示文档。

---

## 6. Commit 提交规范

每次提交应保持小而清晰，不建议一次性提交大量无关内容。

推荐格式：

```text
类型: 简短说明
```

常用类型：

```text
feat: 新功能
fix: bug 修复
docs: 文档修改
style: 样式或格式调整
test: 测试相关
refactor: 代码重构
chore: 配置、依赖、清理等杂项
```

示例：

```text
feat: improve hnsw index parameter validation
fix: prevent top_k from exceeding cell count
docs: add midterm demo guide
style: optimize search result table layout
test: add ann search boundary tests
```

不推荐提交信息：

```text
修改
update
111
final
临时
```

------

## 7. 文件责任边界

为了减少冲突，中期开发阶段按文件范围划分主要负责人。其他成员如果需要修改非自己负责的文件，应提前在群里说明。

### 7.1 数据与算法相关文件

主要负责人：成员A

```text
app/services/data_service.py
app/services/ann_service.py
app/services/eval_service.py
scripts/create_demo_h5ad.py
tests/test_data_service.py
tests/test_ann_service.py
```

职责：

```text
保证数据处理、向量提取、索引构建、检索和评估逻辑稳定可靠。
```

### 7.2 页面与可视化相关文件

主要负责人：成员B

```text
app/templates/*.html
app/static/css/main.css
app/services/plot_service.py
```

职责：

```text
保证页面展示清晰、美观，检索结果、数据集状态和可视化图表适合中期展示。
```

### 7.3 集成、路由、文档和发布相关文件

主要负责人：项目负责人（丁益三）

```text
app/routes/*.py
app/__init__.py
app/models.py
README.md
docs/*
.gitignore
requirements.txt
```

职责：

```text
维护整体系统结构，负责 PR 审查、dev 分支集成、main 分支发布、中期演示流程和文档整理。
```

### 7.4 公共文件修改规则

以下文件属于公共敏感文件，修改前必须提前说明：

```text
app/models.py
app/routes/search.py
app/routes/datasets.py
requirements.txt
README.md
```

原因：

```text
这些文件容易影响数据库结构、页面流程、依赖安装和最终演示。
```

------

## 8. 三人分工

## 8.1 项目负责人：集成、Git 管理与中期交付

### 主要职责

项目负责人负责整体项目集成和中期交付质量，不负责所有代码细节，但负责保证系统最终能稳定运行。

### 大块任务

#### 任务一：Git 流程和分支管理

负责内容：

```text
维护 dev 和 main 分支
审核成员 PR
解决合并冲突
控制 dev -> main
中期前打版本标签
检查 GitHub 提交记录是否清晰
```

主要涉及：

```text
GitHub 仓库
dev 分支
main 分支
PR 页面
```

交付标准：

```text
main 分支始终是稳定版本
dev 分支是集成测试版本
每个成员都有清晰提交记录
中期提交前 main 能直接运行
```

#### 任务二：系统集成和流程验收

负责内容：

```text
检查登录、上传、处理、建索引、检索、评估、可视化全流程
修复路由层面的流程问题
统一 flash 提示信息
确保页面跳转逻辑顺畅
```

主要涉及文件：

```text
app/routes/main.py
app/routes/datasets.py
app/routes/search.py
app/__init__.py
```

交付标准：

```text
从启动项目到完成一次检索，流程不中断
所有主要按钮跳转正常
异常情况有友好提示
```

#### 任务三：README 和中期展示材料

负责内容：

```text
整理安装运行说明
整理中期演示流程
整理项目功能说明
整理小组分工说明
准备 5–8 分钟展示大纲
```

主要涉及文件：

```text
README.md
docs/中期分工手册.md
docs/中期展示提纲.md
docs/系统流程说明.md
```

交付标准：

```text
新成员按照 README 能跑起来项目
展示时按文档可以完整讲解系统流程
项目目标、功能模块、技术栈、运行步骤清楚
```

------

## 8.2 成员 A：数据处理、索引检索与评估模块

### 主要职责

成员 A 负责系统的核心算法链路，包括 `.h5ad` 数据读取、PCA 向量缓存、HNSW 索引构建、Top-K 检索和基础性能评估。

### 大块任务

#### 任务一：数据处理链路稳定化

负责内容：

```text
检查 h5ad 读取逻辑
保证 X_pca 字段检查清晰
保证向量缓存为 npy
保证细胞元信息正确入库
处理失败时写入错误状态
```

主要涉及文件：

```text
app/services/data_service.py
tests/test_data_service.py
scripts/create_demo_h5ad.py
```

交付标准：

```text
demo 数据能够成功处理
真实 liver.h5ad 如果字段完整也能处理
缺少 X_pca 时能给出明确错误提示
处理后 Dataset 中细胞数、基因数、向量维度正确
Cell 表中有 cell_type、disease、age_group 信息
```

#### 任务二：HNSW 索引与检索稳定化

负责内容：

```text
保证 HNSW 索引能正常构建、保存、加载
保证 top_k 不超过细胞数量
保证 fetch_k 不超过索引元素数量
保证 index_id 必须属于当前 dataset_id
保证查询细胞编号越界时有明确错误
```

主要涉及文件：

```text
app/services/ann_service.py
tests/test_ann_service.py
```

交付标准：

```text
构建索引成功后生成 .bin 文件
检索返回 Top-K 相似细胞
默认排除查询细胞自身
按 cell_type 过滤时不报错
非法参数不会导致系统崩溃
```

#### 任务三：评估模块可展示化

负责内容：

```text
保证 ANN vs 精确检索评估可以运行
输出 Recall@K
输出 ANN 平均耗时
输出精确检索平均耗时
输出加速比
限制 sample_size，避免评估过慢
```

主要涉及文件：

```text
app/services/eval_service.py
tests/test_ann_service.py
```

交付标准：

```text
检索页面点击评估按钮后能返回评估结果
Recall@K、ANN 耗时、精确检索耗时、加速比均能正常显示
评估过程不会因为 sample_size 过大导致系统卡死
```

------

## 8.3 成员 B：前端页面、可视化与演示体验

### 主要职责

成员 B 负责系统页面展示、可视化效果和中期演示体验。重点是让老师能直观看到系统已经完成了数据管理、索引构建、检索展示和性能评估。

### 大块任务

#### 任务一：数据集页面和详情页优化

负责内容：

```text
优化数据集列表页
优化数据集详情页
突出显示数据集状态、细胞数、基因数、向量维度
突出显示索引参数和索引状态
让处理数据集、构建索引、删除数据集按钮清晰
```

主要涉及文件：

```text
app/templates/datasets.html
app/templates/dataset_detail.html
app/static/css/main.css
```

交付标准：

```text
用户进入数据集页面后能清楚知道数据集当前状态
详情页能清楚展示是否已处理、是否已建索引
索引构建表单清楚可用
页面适合课堂展示
```

#### 任务二：检索页面和结果展示优化

负责内容：

```text
优化检索表单
优化结果表格
突出显示 query_cell_index、top_k、查询耗时、过滤条件
展示 rank、cell_index、cell_name、distance、cell_type、disease、age_group
当没有索引或没有结果时给出友好提示
```

主要涉及文件：

```text
app/templates/search.html
app/static/css/main.css
```

交付标准：

```text
检索结果一眼能看懂
Top-K 表格字段完整
查询耗时明显展示
无结果、错误输入等情况页面不混乱
```

#### 任务三：Plotly 可视化展示增强

负责内容：

```text
优化数据集整体散点图
优化检索结果高亮图
确保查询细胞和结果细胞颜色、图例、标题清晰
确保 hover 信息尽量包含 cell_index 或 cell_type
```

主要涉及文件：

```text
app/services/plot_service.py
app/templates/dataset_detail.html
app/templates/search.html
```

交付标准：

```text
数据集详情页能显示 UMAP/PCA 散点图
检索后能高亮查询细胞和结果细胞
图表标题、坐标轴、图例适合展示
```

------

## 9. 阶段安排

## 阶段一：环境同步与基线确认

目标：

```text
所有成员在本地跑通当前项目，确认项目基线版本。
```

主要任务：

```text
1. 从 main 克隆项目。
2. 创建本地环境。
3. 安装 requirements.txt。
4. 初始化数据库。
5. 生成或准备 demo 数据。
6. 启动 Flask 项目。
7. 完成一次完整检索流程。
```

完成标准：

```text
三名成员都能在本地访问 http://localhost:5000
至少一名成员完成从数据处理到检索的完整流程录屏或截图
```

建议命令：

```bash
conda create -n sc-ann python=3.10
conda activate sc-ann
pip install -r requirements.txt
python scripts/init_db.py
python scripts/create_demo_h5ad.py
python run.py
```

------

## 阶段二：并行开发

目标：

```text
三名成员按照模块并行开发，尽量减少互相修改同一文件。
```

分工：

```text
成员 A：数据处理、索引、检索、评估稳定化
成员 B：页面、样式、可视化展示优化
项目负责人：路由集成、文档、Git 管理、中期流程验收
```

要求：

```text
1. 每个人从 dev 拉自己的 feature 分支。
2. 每个大块任务完成后发 PR 到 dev。
3. 不直接改 main。
4. 不直接 push 到 dev，除非项目负责人处理紧急集成问题。
5. 公共文件修改前先说明。
```

------

## 阶段三：集成测试

目标：

```text
把成员功能合并到 dev，统一跑通完整系统。
```

测试流程：

```text
1. 启动项目。
2. 注册或登录用户。
3. 进入数据集页面。
4. 上传或使用 demo h5ad。
5. 处理数据集。
6. 查看数据集详情和可视化。
7. 构建 HNSW 索引。
8. 进入检索页面。
9. 输入查询细胞编号。
10. 设置 Top-K。
11. 执行检索。
12. 查看结果表格和高亮图。
13. 运行评估。
14. 检查 Recall@K、耗时和加速比。
```

完成标准：

```text
dev 分支可以完整跑通演示流程
页面无明显报错
核心功能按钮均可用
README 中的运行步骤准确
```

------

## 阶段四：中期冻结与发布

目标：

```text
冻结中期版本，合并到 main，准备展示。
```

流程：

```text
1. 项目负责人确认 dev 分支稳定。
2. 项目负责人从 dev 合并到 main。
3. 在 main 上重新拉取并完整测试。
4. 打 tag：v0.1-midterm。
5. 准备展示讲稿和演示视频。
```

命令示例：

```bash
git checkout main
git pull origin main
git merge dev
git push origin main
git tag v0.1-midterm
git push origin v0.1-midterm
```

完成标准：

```text
main 分支可直接运行
GitHub 提交记录清楚
中期展示流程稳定
README 和展示文档完整
```

------

## 10. 冲突避免规则

### 10.1 尽量避免多人同时修改同一文件

高风险文件：

```text
app/routes/search.py
app/routes/datasets.py
app/templates/search.html
app/templates/dataset_detail.html
README.md
```

处理方式：

```text
如果确实需要多人修改同一个文件，应先在群里说明修改范围。
```

### 10.2 Service 和 Template 分阶段对接

开发顺序建议：

```text
成员 A 先稳定 service 返回字段
成员 B 再根据返回字段调整页面展示
项目负责人最后检查路由传参和整体流程
```

原则：

```text
service 返回字段尽量保持兼容
新增字段可以，但不要随意删除已有字段
模板只依赖稳定字段
```

### 10.3 数据库模型谨慎修改

中期阶段原则上不大改数据库模型。

如果必须修改 `app/models.py`：

```text
1. 提前说明修改原因。
2. 说明是否需要删除 instance/app.db。
3. 说明是否需要重新运行 init_db.py。
4. 合并前由项目负责人确认。
```

### 10.4 依赖谨慎增加

中期阶段不随意增加大型依赖。

如果必须修改 `requirements.txt`：

```text
1. 说明新增依赖用途。
2. 确认所有成员能安装成功。
3. README 同步说明。
```

------

## 11. 中期验收标准

中期版本合并到 main 前，必须满足以下标准。

### 11.1 功能标准

```text
用户可以注册、登录、退出。
可以上传或使用 demo h5ad 数据。
可以处理数据集并提取 PCA 向量。
可以保存细胞元信息。
可以构建 HNSW 索引。
可以输入查询细胞编号做 Top-K 检索。
可以返回相似细胞信息。
可以按 cell_type 过滤检索结果。
可以展示查询耗时。
可以显示 UMAP/PCA 可视化图。
可以运行基础性能评估。
```

### 11.2 稳定性标准

```text
非法 query_cell_index 有错误提示。
top_k 过大不会导致系统崩溃。
未构建索引时页面有提示。
缺少 X_pca 时处理失败但系统不崩溃。
demo 数据可以稳定跑通。
```

### 11.3 文档标准

```text
README 包含项目介绍。
README 包含技术栈。
README 包含安装步骤。
README 包含数据库初始化步骤。
README 包含 demo 数据生成步骤。
README 包含运行方式。
README 包含中期演示流程。
README 包含测试命令。
docs 中包含中期分工手册。
```

### 11.4 Git 标准

```text
所有成员都有提交记录。
功能通过 PR 合并到 dev。
main 分支只保留稳定版本。
中期版本有 tag。
提交信息基本规范。
```

------

## 12. 中期展示建议分工

### 项目负责人

负责讲：

```text
项目背景
系统目标
整体架构
Git 管理方式
项目完成情况
后续计划
```

### 成员 A

负责讲：

```text
h5ad 数据读取
X_pca 向量提取
HNSW 索引构建
Top-K 检索逻辑
ANN 与精确检索评估
```

### 成员 B

负责讲：

```text
Web 页面使用流程
数据集管理页面
检索结果表格
UMAP/PCA 可视化
页面交互和展示效果
```

### 演示顺序

```text
1. 首页介绍系统。
2. 登录系统。
3. 进入数据集页面。
4. 上传或选择 demo 数据。
5. 处理数据集。
6. 查看数据集详情和可视化。
7. 构建 HNSW 索引。
8. 进入检索页面。
9. 输入查询细胞编号和 Top-K。
10. 展示相似细胞结果。
11. 展示检索高亮图。
12. 运行基础评估。
13. 总结当前完成内容和结项计划。
```

------

## 13. 每日协作规则

中期前建议每天做一次简短同步，内容不超过 5 分钟。

每人说明：

```text
昨天完成了什么
今天准备做什么
是否遇到阻塞
是否需要修改公共文件
是否需要其他成员配合
```

如果出现 bug，先在群里说明：

```text
出现问题的页面或命令
复现步骤
报错截图或报错文本
当前分支名
最近修改过的文件
```

不要只说“跑不起来”。

------

## 14. 中期前不建议做的事情

为了保证中期稳定，以下功能不建议在中期前强行加入：

```text
多数据集联合检索
复杂管理员后台
Celery 后台任务
大规模数据库重构
多种 ANN 算法重构
RAG 自然语言查询
复杂权限系统
前后端彻底分离
```

这些功能可以作为结项扩展方向，但中期阶段应优先保证已有功能稳定可展示。

------

## 15. 中期版本最终交付物

中期提交前，仓库应至少包含：

```text
完整 Flask 项目代码
requirements.txt
README.md
docs/中期分工手册.md
docs/中期展示提纲.md
scripts/init_db.py
scripts/create_demo_h5ad.py
tests/
.gitignore
```

项目负责人最终检查：

```text
main 分支能运行
README 步骤准确
demo 数据能生成
数据集能处理
索引能构建
检索能返回结果
评估能显示指标
页面能正常展示
GitHub 提交记录清楚
```

------

## 16. 总结

本阶段开发重点是稳定完成中期要求：

```text
单细胞数据读取
数据向量化表示
ANN 索引构建
相似细胞检索
Top-K 结果返回
Web 页面展示
Git 过程管理
课堂演示
```

三人分工原则：

```text
成员 A 负责核心算法链路
成员 B 负责页面和可视化展示
项目负责人负责集成、Git、文档和发布
```

代码合并原则：

```text
个人分支开发
PR 合并到 dev
项目负责人负责 dev 到 main
main 始终保持稳定
```

中期目标不是做最多功能，而是提交一个结构清晰、流程完整、能稳定演示的单细胞 ANN 检索系统。