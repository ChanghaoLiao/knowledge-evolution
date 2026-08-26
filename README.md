# Knowledge Evolution

把对话、Agent 实际工作和历史资料，转化为**可审核、可追溯、可恢复**的个人知识库变更。

[![License: MIT](https://img.shields.io/badge/License-MIT-2f6f5e.svg)](LICENSE)
![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB.svg)
![Storage: Markdown](https://img.shields.io/badge/Storage-Markdown-6C5CE7.svg)
![Obsidian: Optional](https://img.shields.io/badge/Obsidian-Optional-7C3AED.svg)
![Git: Private Optional](https://img.shields.io/badge/Git-Private%20Optional-24292F.svg)

> Proposal-first personal knowledge governance for Codex.

Knowledge Evolution 不是一个“自动把聊天保存成笔记”的工具。它让 Codex 先检查对话、工具行为、工作区变化、已有知识库和用户授权的历史资料，再提出类似 Git Diff 的知识变更；只有用户明确批准后，目标知识库才会被创建或更新。

![Knowledge Evolution 生成的 Obsidian 知识图谱](docs/images/knowledge-graph-light.png)

## 目录

- [为什么需要它](#为什么需要它)
- [核心能力](#核心能力)
- [工作原理](#工作原理)
- [安装](#安装)
- [快速开始](#快速开始)
- [Bootstrap：第一次使用](#bootstrap第一次使用)
- [多电脑：私有 Git 知识系统](#多电脑私有-git-知识系统)
- [Import / Adopt：接管已有资料](#import--adopt接管已有资料)
- [日常使用](#日常使用)
- [截图演示](#截图演示)
- [目录结构](#目录结构)
- [脚本与支持格式](#脚本与支持格式)
- [隐私与安全边界](#隐私与安全边界)
- [配置](#配置)
- [验证与测试](#验证与测试)
- [已知限制](#已知限制)
- [常见问题](#常见问题)
- [许可证](#许可证)

## 为什么需要它

普通 AI 笔记流程通常是：

```text
一次对话 → 一篇总结 → 更多孤立笔记
```

Knowledge Evolution 关注的是“这次工作让知识体系发生了什么变化”：

```text
对话 + Agent 工具记录 + 工作区事实 + 已有知识 + 历史资料
                           ↓
                    知识候选与证据
                           ↓
                  重复 / 冲突 / 版本协调
                           ↓
                    可审核的变更提案
                           ↓
                       用户批准
                           ↓
               知识库更新 + 来源登记 + 变更台账
```

它解决的不是单纯的“生成”，而是知识变化的治理：知道内容来自哪里、为什么要改、改了什么，以及如何回滚。

## 核心能力

- **Proposal-first**：任何知识库写入之前，先生成带编号的变更提案。
- **对话与工作区联合观察**：不仅看聊天，还核对 Agent 实际修改的文件、测试和产物。
- **三种 Bootstrap 路线**：新建 Create、原地接管 Adopt、多来源迁移 Import。
- **Obsidian 可选**：普通 Markdown 文件夹即可完整使用，之后可直接作为 Vault 打开。
- **多来源只读导入**：对多个授权文件夹建立清单、哈希、来源定位和迁移提案。
- **可暂停、可恢复**：大量资料按确定性分类批次处理，任务状态独立保存。
- **证据链**：候选知识保留 `source_id`、`file_id`、`chunk_id`、相对路径和定位信息。
- **重复与冲突协调**：区分完全重复、近似重复、历史版本和未解决冲突。
- **持久化初始化状态**：Bootstrap 完成后不会因为下一次调用而丢失或重置。
- **可选私有 Git 便携层**：把知识、共享配置和仓库级 Skill 快照放进私有仓库，让另一台电脑克隆后继续工作。
- **设备配置隔离**：共享逻辑来源 ID，本机绝对路径只写入被 Git 忽略的设备配置。
- **安全默认值**：来源只读、敏感文件排除、内容凭据遮盖、严格路径边界和应用前哈希检查。

## 工作原理

```mermaid
flowchart LR
    C["对话与工具记录"] --> A["Codex + Knowledge Evolution"]
    W["授权工作区"] --> A
    S["Import 来源文件夹<br/>只读"] --> I["清单、提取、分类批次"]
    K["已有知识库<br/>Adopt 比对来源"] --> I
    I --> A
    A --> R["重复、冲突与版本协调"]
    R --> P["知识变更提案"]
    P --> U{"用户明确批准？"}
    U -->|否| X["修改、延期或拒绝"]
    U -->|是| T["目标 Markdown 知识库"]
    T --> V["验证、来源登记、变更台账"]
    V -. 可选的获批发布 .-> G["私有 Git 远程<br/>跨电脑传输与回滚"]
```

Skill、工作区和知识库始终是三个不同对象：

- **公开 Skill 本体**保存通用规则、模板和辅助脚本。
- **工作区与来源文件夹**提供事实和历史资料，默认只读观察。
- **目标知识库**只接收用户批准的变更。

启用 Git 便携层时，私有仓库可以额外保存一份不含个人信息的 Skill 快照，供仓库级发现使用。用户画像、偏好、设备路径和知识内容始终位于快照之外。

升级 Skill 不等于重新初始化用户知识库，也不会用新版空白模板覆盖用户内容。

## 安装

### 方法一：让 Codex 使用内置 Skill Installer

在 Codex 中输入：

```text
用 $skill-installer 从 https://github.com/ChanghaoLiao/knowledge-evolution 安装仓库根目录的 knowledge-evolution Skill。
```

安装完成后新开一个 Codex 任务；如果 Skill 没有立即出现在列表中，再重启 Codex。

### 方法二：运行 Skill Installer 脚本

```bash
python3 "${CODEX_HOME:-$HOME/.codex}/skills/.system/skill-installer/scripts/install-skill-from-github.py" \
  --repo ChanghaoLiao/knowledge-evolution \
  --path . \
  --name knowledge-evolution
```

安装器会把仓库根目录复制到：

```text
${CODEX_HOME:-~/.codex}/skills/knowledge-evolution/
```

如果目标目录已经存在，安装器会停止而不是覆盖。升级前请先检查并保留自己的本地修改。

### 方法三：手动安装

```bash
git clone https://github.com/ChanghaoLiao/knowledge-evolution.git
mkdir -p "${CODEX_HOME:-$HOME/.codex}/skills/knowledge-evolution"
rsync -a --exclude '.git' knowledge-evolution/ \
  "${CODEX_HOME:-$HOME/.codex}/skills/knowledge-evolution/"
```

运行要求：

- Codex，负责发现并调用 Skill；
- Python 3.10 或更高版本，负责可选的审计、快照和 Import / Adopt 流水线；
- Git，可选；使用多电脑私有仓库功能时必需；
- GitHub CLI，可选；创建或验证 GitHub 私有仓库时使用；
- Obsidian，可选，普通 Markdown 目录同样受支持。

## 快速开始

### 1. 先做只读检查

```text
用 $knowledge-evolution 检查我是否需要初始化知识库。
先只读分析并生成提案，不要修改任何文件。
```

### 2. 新建一个不依赖 Obsidian 的知识库

```text
用 $knowledge-evolution 初始化我的个人知识库。
目标目录是 `/你的/知识库路径`。先给我 Bootstrap 提案，不要直接创建文件。
```

### 3. 接管已有 Obsidian Vault

```text
用 $knowledge-evolution 接管这个现有 Vault：`/你的/Vault`。
保留现有目录、标签、frontmatter 和链接规则；先建立索引与提案，不要移动笔记。
```

### 4. 导入多个资料文件夹

```text
用 $knowledge-evolution 把 `/资料/旧笔记` 和 `/资料/项目文档`
纳入目标知识库 `/资料/我的知识库`。
来源保持只读，分批处理，先给我第一轮迁移提案。
```

### 5. 建立多电脑私有知识环境

```text
用 $knowledge-evolution 把我的知识库配置成私有 GitHub 知识系统。
另一台电脑克隆后要能继续使用仓库内的 Skill、个人配置和知识库。
先给我 Bootstrap 与 Git 操作提案，不要创建远程或推送。
```

## Bootstrap：第一次使用

第一次使用时，Skill 不假设用户已经有 Obsidian，也不假设当前工作区就是知识库。它会先判断环境，再选择路线。

| 路线 | 适用情况 | 默认行为 |
| --- | --- | --- |
| Create | 没有知识库或只有空目录 | 提议创建便携 Markdown 结构 |
| Adopt | 已有 Markdown / Obsidian 知识库 | 原地映射，采用已有结构 |
| Import | 资料分散在多个外部文件夹或导出包 | 来源只读，向单独目标库提出迁移 |

### Bootstrap 第一阶段：发现与提案

Agent 会确认：

- 知识库根目录；
- 是否已有 Vault 或 Markdown 目录；
- 哪些旧资料、导出包或项目文件夹允许读取；
- 哪些路径和内容必须排除；
- 用户偏好的语言、链接、命名和目录规则；
- 后续审核策略。

此阶段不会创建目录、移动笔记或修改 `.obsidian/`。

在 Create、Adopt 或 Import 路线确定之后，用户还可以选择一个独立的存储层：

| 存储层 | 适用情况 | 默认行为 |
| --- | --- | --- |
| Local-only | 只在当前电脑使用 | 不初始化 Git，不增加仓库级 Skill |
| Existing Git | 已有合适的私有仓库 | 先检查状态、remote 与 ignore，再提出放置方案 |
| New Private GitHub | 需要跨电脑访问 | 先建本地便携结构；远程创建和首次 push 分开审批 |

### Bootstrap 第二阶段：用户批准后应用

用户可以批准全部变更、只批准部分编号、要求修改或完全拒绝，例如：

```text
批准 K-01、K-03 和 K-04，其余先延期。
```

只有获批变更会被应用。一个新的知识库可能采用以下起始结构：

```text
00 Inbox/
10 Concepts/
20 Projects/
30 Decisions/
40 Experiences/
50 Resources/
System/
```

这只是新知识库的默认起点，不会强加给已有成熟 Vault。

### 初始化完成后会保留什么

默认系统记录包括：

```text
System/
├── knowledge-evolution.yaml
├── Knowledge Map.md
├── Source Registry.md
├── Change Ledger.md
└── Proposals/
    └── 已批准的 Bootstrap 提案.md
```

- `knowledge-evolution.yaml`：初始化状态、目录映射、授权范围和审核策略；
- `Knowledge Map.md`：当前知识结构和导航入口；
- `Source Registry.md`：来源、边界和最后观察状态；
- `Change Ledger.md`：获批变更、证据和回滚位置；
- `Proposals/`：已经批准并应用的提案版本。

初始化状态是持久的。之后会进入 Evolve 或 Audit，不会重复复制模板或删除初始化信息。

## 多电脑：私有 Git 知识系统

这是一层可选能力，不会改变 Local-only 用户的行为。它把公开 Skill 和个人环境分成两个对象：

```text
公开 Knowledge Evolution Skill
        ↓ 生成、验证和升级通用规则
用户自己的私有 Git 仓库
        ↓ 保存知识、共享配置、历史和仓库级 Skill 快照
多台电脑上的本机路径映射
```

### 标准仓库结构

新建环境的参考结构是：

```text
personal-knowledge/
├── AGENTS.md
├── .agents/
│   └── skills/
│       └── knowledge-evolution/   # 不含个人信息的通用快照
├── Knowledge/
│   ├── 00 Inbox/
│   ├── 10 Concepts/
│   ├── 20 Projects/
│   ├── 30 Decisions/
│   ├── 40 Experiences/
│   ├── 50 Resources/
│   └── System/
│       ├── Profile/               # 用户画像与知识偏好
│       ├── Knowledge Map.md
│       ├── Source Registry.md
│       ├── Change Ledger.md
│       └── knowledge-evolution.yaml
├── .knowledge-evolution/
│   └── portability.yaml           # 共享同步与隐私策略
├── .local/
│   ├── device.yaml                # 本机配置，不提交
│   └── device.yaml.example        # 可提交的字段示例
├── .gitignore
└── README.md
```

已有成熟 Vault 或 Git 仓库不会被强制改成这个目录。Skill 会保留其结构，只提议加入必要的便携配置和可选 Skill 快照。

### 创建本地便携结构

只有在用户批准目标路径、是否复制旧 Vault、Bootstrap 状态和 Git 初始化之后，才运行：

```bash
python3 scripts/create_portable_repository.py \
  --repo-root "/目标/Personal Knowledge" \
  --name "Personal Knowledge" \
  --bootstrap-status initialized \
  --bootstrap-route create \
  --proposal-id BOOTSTRAP-001 \
  --initialized-at YYYY-MM-DD \
  --pretty
```

接管已有知识库时，必须显式提供 `--copy-knowledge`；脚本只复制，不会移动或修改原目录：

```bash
python3 scripts/create_portable_repository.py \
  --repo-root "/目标/Personal Knowledge" \
  --knowledge-source "/原来的/Vault" \
  --copy-knowledge \
  --bootstrap-status adopted \
  --bootstrap-route adopt \
  --proposal-id BOOTSTRAP-002 \
  --initialized-at YYYY-MM-DD \
  --pretty
```

该脚本只创建本地结构。它不会创建 GitHub 仓库、修改全局 Codex 配置、提交、推送或删除来源。复制旧资料时会跳过并报告嵌套 `.git`、符号链接、凭据/密钥命名文件和 Obsidian 设备状态；这些内容仍保留在原目录。

### 连接新的私有 GitHub 仓库

远程创建属于单独的外部操作，需要明确批准。参考流程：

```bash
gh repo create OWNER/REPOSITORY --private --source "/目标/Personal Knowledge" --remote origin
python3 scripts/sync_knowledge_repository.py verify-private \
  --repo "/目标/Personal Knowledge" \
  --pretty
```

只有验证结果为 `PRIVATE` 后，才允许第一次知识 push。GitHub CLI 未登录、无法获得可见性、仓库是 public，都会阻断推送；系统不会退回公开仓库。

### 日常同步

开始一次知识任务前检查状态：

```bash
python3 scripts/sync_knowledge_repository.py status --repo "/目标/Personal Knowledge" --pretty
python3 scripts/sync_knowledge_repository.py pull --repo "/目标/Personal Knowledge" --pretty
```

`pull` 只在 worktree 和 index 都干净、有明确 upstream 时执行 `--ff-only`。存在未提交修改、分叉、冲突、detached HEAD 或认证失败时会停止，不会自动 stash、reset、rebase 或选一个版本覆盖另一个。

知识提案获批并应用、验证后，提交仍然只包含用户批准的路径：

```bash
python3 scripts/sync_knowledge_repository.py publish \
  --repo "/目标/Personal Knowledge" \
  --path Knowledge \
  --message "knowledge: apply PROPOSAL-001" \
  --push \
  --pretty
```

脚本拒绝已有的无关 staged 内容，从不 force-push。普通知识 Apply 的批准不会自动授权 commit 或 push，除非用户已经在持久策略中明确启用获批后发布。

### 另一台电脑如何开始

```text
登录私有 Git 提供方
        ↓
clone 私有仓库
        ↓
用 Codex 打开克隆目录
        ↓
仓库级 Skill 读取共享知识与配置
        ↓
从 example 创建本机 device.yaml
        ↓
先运行只读 Audit，再开始 Apply
```

Git clone 出于安全原因不会自动执行安装脚本。在支持仓库级 Skill 的 Codex 环境中，打开仓库即可使用 `.agents/skills/knowledge-evolution/`。如果还希望在无关项目中全局调用这份快照，再显式运行一次：

```bash
python3 .agents/skills/knowledge-evolution/scripts/install_portable_skill.py \
  --repository-root . \
  --pretty
```

安装器默认使用符号链接，使全局入口跟随克隆仓库中的快照；Windows 的 `auto` 模式使用复制。目标已存在时会停止，不会覆盖另一个 Skill。复制模式不会自动跟随后续升级。

### 不同电脑上的项目路径

共享配置只记录逻辑来源 ID，例如 `ai-coding-projects`。每台电脑在不提交的 `.local/device.yaml` 中映射自己的绝对路径：

```yaml
device_id: "macbook-example"
source_paths:
  ai-coding-projects: "/Users/example/Projects/ai-coding"
```

Windows 或另一台 Mac 可以把相同 ID 映射到完全不同的位置。某台电脑没有该路径时，来源只会标记为 `unavailable-on-this-device`，不会被当成已删除。

完整协议见 [`references/git-portability.md`](references/git-portability.md)。

## Import / Adopt：接管已有资料

Import / Adopt 不是一次性“批量总结”。它是一条可恢复、带证据链的治理流水线：

```text
登记授权来源与排除范围
          ↓
只读文件清单与内容哈希
          ↓
跨格式文字提取与敏感值遮盖
          ↓
确定性分类批次与 checkpoint
          ↓
概念 / 项目 / 决策 / 经历 / 资源候选
          ↓
重复 / 冲突 / 版本候选
          ↓
完整协调决定
          ↓
有界 Proposal Wave
          ↓
用户逐项批准
          ↓
目标写入、应用记录与验证
```

### Import

- 外部资料文件夹与目标知识库不能重叠；
- 来源文件始终登记为 `writable: false`；
- 原文件不会被移动、改名、覆盖或删除；
- 整理结果只写入单独目标库中的获批路径。

### Adopt

- 已有知识库同时是比对来源和最终目标；
- 发现、分类和提案阶段仍然只读；
- 只有与获批 Change ID 对应的目标修改才允许记录；
- 验证会把已记录的 Adopt 目标变更和不明外部变化分开。

### 已有目标库再导入外部资料

如果目标库本身已经有内容，目标会登记一次 `adopt` 来源；外部文件夹分别登记为 `import` 来源。这样 incoming knowledge 会和目标里的现有概念、项目和决定一起去重、比较版本和检查冲突。

每个任务使用独立 job 目录，保存 Manifest、批次、候选、协调决定、提案、应用记录和验证报告。job 目录必须位于来源和目标之外。

完整操作协议见 [`references/import-adopt.md`](references/import-adopt.md)。

## 日常使用

Bootstrap 完成后，通常使用 Evolve、Audit 和 Apply。

### 从对话和工作区生成提案

```text
用 $knowledge-evolution 整理这次讨论，同时核对当前项目真实修改了什么。
只生成知识更新提案。
```

### 只做知识体检

```text
用 $knowledge-evolution 审计我的知识库。
只报告重复、冲突、孤立笔记和可能过期的内容，不要修改文件。
```

### 应用部分变更

```text
用 $knowledge-evolution 应用当前提案中的 K-01 和 K-03，其余保持不变。
```

### 重新检查 Agent 的实际工作成果

```text
用 $knowledge-evolution 对照这次对话、工具记录和工作区 diff，
找出值得沉淀的项目决定和状态变化，先给我提案。
```

## 截图演示

以下截图来自一次本地测试流程。图中的用户名、绝对路径、知识主题和 Change ID 都只是演示数据，不是 Skill 的固定配置。

### 从空 Vault 开始

![Obsidian 空 Vault 与初始关系图谱](docs/images/obsidian-empty-vault.png)

### 用户批准 Bootstrap 变更

![Codex 中的 Bootstrap 审批过程](docs/images/bootstrap-approval.png)

### 初始化后的第一版知识图谱

![Bootstrap 后的 Obsidian 知识图谱](docs/images/knowledge-graph-bootstrap.png)

### 知识库持续演化后的图谱

![持续更新后的 Obsidian 知识图谱](docs/images/knowledge-graph-evolved.png)

## 目录结构

```text
knowledge-evolution/
├── SKILL.md
├── README.md
├── LICENSE
├── AGENTS.md
├── agents/
│   └── openai.yaml
├── assets/
│   ├── portable-repository/
│   │   ├── AGENTS.md
│   │   ├── README.md
│   │   └── gitignore
│   └── templates/
│       ├── knowledge-evolution.yaml
│       ├── git-portability.yaml
│       ├── device-config.yaml.example
│       ├── adopt-job.json
│       ├── import-job.json
│       ├── import-proposal.md
│       ├── import-report.md
│       └── ...
├── references/
│   ├── onboarding.md
│   ├── import-adopt.md
│   ├── knowledge-schema.md
│   ├── observation.md
│   ├── git-portability.md
│   └── governance.md
├── scripts/
│   ├── audit_knowledge_base.py
│   ├── workspace_changes.py
│   ├── create_portable_repository.py
│   ├── install_portable_skill.py
│   ├── sync_knowledge_repository.py
│   ├── register_sources.py
│   ├── build_source_manifest.py
│   ├── extract_documents.py
│   ├── prepare_import_batches.py
│   ├── manage_import_state.py
│   ├── find_duplicate_candidates.py
│   └── verify_import.py
├── tests/
│   ├── test_import_pipeline.py
│   └── test_git_portability.py
└── docs/images/
```

## 脚本与支持格式

脚本只负责确定性工作；语义分类和冲突判断由 Agent 完成，知识库写入由用户批准。

| 脚本 | 作用 | 是否修改来源 |
| --- | --- | --- |
| `audit_knowledge_base.py` | 有界知识库体检 | 否 |
| `workspace_changes.py` | Git 状态或前后快照 | 否；只有显式输出快照时写状态文件 |
| `create_portable_repository.py` | 生成本地便携仓库结构与 Skill 快照 | 不修改来源；只写批准的新目录 |
| `install_portable_skill.py` | 可选地链接或复制仓库级 Skill 到全局目录 | 不修改知识；拒绝覆盖已有 Skill |
| `sync_knowledge_repository.py` | 状态、`ff-only` 拉取、私有验证、按路径发布 | 仅显式 pull/publish 修改 Git 状态 |
| `register_sources.py` | 校验来源、目标和 job 边界 | 否 |
| `build_source_manifest.py` | 路径、格式、大小和哈希清单 | 否 |
| `extract_documents.py` | 提取带来源定位的内容片段 | 否 |
| `prepare_import_batches.py` | 建立确定性分类批次 | 否 |
| `manage_import_state.py` | checkpoint、批次状态、候选和应用记录 | 不编辑知识内容 |
| `find_duplicate_candidates.py` | 重复、冲突和版本短名单 | 否 |
| `verify_import.py` | 来源稳定性、证据链和目标哈希验证 | 否；可显式写验证报告 |

直接支持的内容包括：

- Markdown、纯文本和常见代码文件；
- JSON、JSONL、CSV、TSV、YAML、TOML；
- HTML；
- DOCX；
- Jupyter Notebook；
- PDF 文本层（需要 `pypdf`、`PyPDF2` 或系统中的 `pdftotext`）。

无法提取的格式会出现在报告中，不会被假装已经导入。

## 隐私与安全边界

- 只检查用户明确提供或批准的目录。
- 不用主目录、整个桌面、云盘或无关仓库代替缺失的范围。
- `.env`、私钥、凭据文件和常见 token 文件在哈希与提取前排除。
- 普通文档中常见的 API Key、Bearer Token、授权值、带密码 URL 和私钥块会在写入临时提取内容前遮盖。
- 内容遮盖是 defense in depth，不应把已知含敏感信息的目录纳入来源。
- 默认忽略 symlink、`.git`、`node_modules`、构建目录、虚拟环境和缓存。
- Import 来源与目标不得重叠；job 目录必须位于来源和目标之外。
- 应用前重新校验来源哈希；来源变化会让旧提案失效。
- 没有会话前 baseline 或工具记录时，不把 dirty tree 变化归因于当前 Agent。
- 覆盖、删除、批量移动、合并和知识体系重构始终需要单独审核。
- 原始提取片段属于临时证据，不应提交到 Git 或长期同步目录。
- 私有 Git 模式默认忽略 `.local/device.yaml`、Obsidian workspace 状态和 Import 临时提取内容。
- GitHub 第一次知识 push 前必须验证可见性是 `PRIVATE`，不能验证则停止。
- 不把 Obsidian Sync、iCloud/Dropbox 目录同步和 Git 自动化同时用于同一个 Vault，除非用户明确设计了冲突策略。

## 配置

新知识库可以从 [`assets/templates/knowledge-evolution.yaml`](assets/templates/knowledge-evolution.yaml) 适配，而不是强制复制：

```yaml
version: 2
format: "markdown"
link_style: "markdown"

bootstrap:
  status: "uninitialized"
  initialized_at: null
  route: null
  proposal_id: null
  schema_version: 2

portability:
  enabled: false
  mode: "local"
  repository_root: null
  knowledge_root: "."
  skill_snapshot: null
  device_config: null
  remote:
    provider: null
    expected_visibility: "private"
  sync:
    pull_before_run: false
    pull_strategy: "fast-forward-only"
    publish_after_approved_apply: false
    auto_resolve_conflicts: false
    force_push: false

approval:
  mode: "proposal-first"
  auto_apply_low_risk: false
  require_separate_high_risk_approval: true

imports:
  state_root: null
  preserve_sources: true
  batch_max_files: 25
  batch_max_characters: 120000
  keep_extracted_text_after_completion: false
  require_source_hash_check_before_apply: true
```

如果已有知识库拥有自己的目录、frontmatter、wikilink、标签和归档规则，优先采用用户的现有配置。

## 验证与测试

运行结构校验：

```bash
python3 "${CODEX_HOME:-$HOME/.codex}/skills/.system/skill-creator/scripts/quick_validate.py" .
```

运行端到端测试：

```bash
python3 -m unittest discover -s tests -v
```

当前测试覆盖：

- 多来源 Import 和 Adopt 路径边界；
- 敏感文件排除和嵌入凭据遮盖；
- 确定性批次、暂停和恢复；
- 错误 provenance 拒绝；
- 未完成批次阻断；
- 重复与冲突协调完整性；
- Application Change ID 幂等；
- 来源在清单后变化时阻断；
- Adopt 获批目标更新与外部漂移的区分；
- 便携仓库生成与原 Vault 哈希保持；
- 复制来源必须显式授权；
- 仓库级 Skill 安装幂等且拒绝覆盖；
- 干净 worktree 的 `ff-only` 拉取、dirty pull 阻断和批准路径提交；
- 非 GitHub 测试 remote 的显式隐私确认与普通 push。

所有自动化测试均使用临时仓库和临时知识库，不接触真实 Vault。Import / Adopt 还完成过一次独立前向测试：两个外部来源加一个已有目标库、9 个清单文件、5 个分类批次，成功推进到 `proposed`，来源和目标文件零写入。

## 已知限制

- 这是 Codex Skill，不是 Obsidian 插件，也不提供独立 GUI。
- 语义分类、去重确认和冲突判断由 Agent 完成；脚本只提供确定性短名单和校验。
- 扫描版 PDF、图片和手写内容没有内置 OCR。
- Notion、OneNote 等系统应先导出为用户可检查的本地文件；当前没有直接 API 连接器。
- 内容敏感值遮盖使用启发式规则，不等于完整 DLP 系统。
- 大规模资料需要时间和上下文预算，设计目标是可暂停、可恢复，而不是未经审核的一键导入。
- Skill 不会自动安装、配置或修改 Obsidian，也不会修改 `.obsidian/`。
- Git 同步是显式任务触发的安全同步，不是实时同步或后台守护进程。
- GitHub 私有可见性验证依赖已登录的 GitHub CLI；其他 Git 提供方需要单独验证隐私并显式确认。
- Git 不适合频繁变化的大型二进制附件；此类内容应单独评估 Git LFS 或外部存储。

## 常见问题

### 必须安装 Obsidian 吗？

不需要。Knowledge Evolution 的存储契约是普通 Markdown。Obsidian 是一个可选客户端。

### Bootstrap 会修改哪些内容？

发现阶段不修改。用户批准后，只能修改提案中列出的知识库路径；Git 便携模式还可以修改明确批准的全新仓库路径。远程创建、全局 Skill 安装、commit 和 push 分别需要授权，不会修改项目源码或 `.obsidian/` 设置。

### 初始化完成后，初始化信息会消失吗？

不会。初始化状态、路线、授权范围、目录映射、提案和变更历史会持久保存。临时扫描结果和被拒绝的草稿可以清理。

### Import 会改动原始资料吗？

不会。Import 来源永久按只读处理。Adopt 的目标库也只会在用户批准具体 Change ID 后被修改。

### 升级 Skill 会覆盖我的知识库吗？

不会。公开 Skill 或私有仓库里的 Skill 快照与 `Knowledge/`、`Profile/`、`.local/` 相互独立。更新快照必须单独审核，未来配置迁移也应先生成迁移提案。

### 必须使用 GitHub 吗？

不需要。本地模式完全不依赖 Git。便携层底层使用普通 Git，GitHub 是当前提供私有可见性自动验证的参考实现；GitLab 或自建 Git 可以在单独验证隐私后使用。

### clone 后 Skill 会自动安装吗？

不会自动执行安装代码。用 Codex 打开仓库时可以使用仓库内 `.agents/skills/` 快照；需要跨项目全局发现时，再主动运行一次安装器。

### 两台电脑能同时修改同一知识库吗？

可以依次修改并同步。若产生 Git 分叉或内容冲突，系统会停止并要求审核，不会自动选择较新的版本。开始工作前先执行安全 pull 能显著减少冲突。

### 为什么不允许直接自动整理全部内容？

因为重复、冲突、版本和知识结构都包含人的判断。自动化负责降低整理成本，但不应该替用户决定什么是真的、什么应该被删除。

### 如何反馈问题？

请在 [GitHub Issues](https://github.com/ChanghaoLiao/knowledge-evolution/issues) 提供：使用模式、脱敏后的目录结构、命令输出、当前 stage，以及预期行为。不要上传真实知识库、提取片段、token 或凭据。

## 许可证

本项目使用 [MIT License](LICENSE)。

欢迎提交 Issue 或 Pull Request。参与贡献时，请保持来源只读、proposal-first 和显式审批这三条核心边界，并为脚本变化补充临时夹具测试。
