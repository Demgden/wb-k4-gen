# kitten4 .bcm4 基础工作模板

一套**自包含*的 kitten4（编程猫）`.bcm4` 作品开发基础设施：
从「起一个新项目」到「生成 + 校验 + 闭环测试」的全套工具、数据与文档
`git clone` 本仓库 → `python tools/scaffold.py 我的作品` → 开工

> AI agent 读者：去读 `AGENTS.md`那是给你的入口。别通读文档，先 `python tools/ask.py orient`，之后按需 `ask.py dsl/law/symptom/task`。详见 `AGENTS.md`
> 更快的方式：`python tools/ask.py orient`（一条命令，30 秒上手，**不用读文档**）。

## 环境要求

Node.js + Python 3，任意 POSIX shell（Windows 用 Git Bash）。

```bash
python tools/scaffold.py 我的作品     # 起项目骨架 projects/我的作品/
cd projects/我的作品 && bash check.sh  # 生成 out/我的作品.bcm4 + 校验
# 把 out/我的作品.bcm4 拖进 kitten4 编辑器即可编辑/运行
```

## 目录地图

```
tools4k4/
├── AGENTS.md               ← AI agent 入口（任务地图 + 命令速查 + 铁律）
├── README.md               ← 本文件
├── docs/
│   ├── block_reference.md  ← 16 条编辑器语义铁律全文（**按需查**，不要通读）
│   └── workflow.md         ← 完整工作流：新项目 / 日常迭代 / 发布前检查 / VM 测试怎么写
├── tools/                  ← 通用工具（与具体作品无关）
│   ├── ask.py              ← ★★agent 查询入口：orient/task/dsl/law/symptom/guard
│   ├── scaffold.py         ← ★一键起新项目（projects/<名字>/ 骨架）
│   ├── gen_mount.js        ← ★通用「信封挂载」库（内容 → 已验证信封）
│   ├── bcm4gen.js          ← 积木 DSL 生成器库
│   ├── template_work.js    ← 从零搭建最小示例（学习 DSL 用）
│   ├── gen_basic.js        ← 生成「空白基础作品」（挂信封、清空脚本）
│   ├── extract_dsl_api.py  ← 从 bcm4gen.js 抽取 DSL API 索引（自动生成）
│   ├── extract_registry.py ← 从编辑器 bundle 抽取积木类型注册表
│   ├── validate_bcm4.py    ← 信封结构校验（schema / 交叉引用 / 类型注册表）
│   ├── check_connections.js← 连接完整性（铁律 4：每块都要有 connections 条目）
│   ├── verify_procedures.py← 过程(函数)定义/调用的 shadows+mutation 校验
│   ├── verify_dsl.py       ← 知识库与实现一致（防止索引对 agent 说谎）
│   ├── kitten4_root.js     ← 工具链定位（项目挪出仓库后仍能找到 tools4k4）
│   ├── bcm4_read.py        ← 反编译任意 .bcm4 为可读伪代码（「读懂」模式）
│   ├── query_block.py      ← ★积木特性速查（字段/输入/影子/真实用例）
│   ├── check_all.sh        ← 通用门禁：信封校验 + 连接完整性（+可选 VM 测试）
│   └── check_repo.sh       ← 仓库自检：知识库一致 + 示例全流程
├── data/
│   ├── block_defs.json     ← 积木影子模板库（编辑器 define_block_xml 全集）
│   ├── block_struct.json   ← 329 个积木的结构摘要
│   ├── editor_block_types.json ← 编辑器积木类型注册表（876 个）
│   ├── dsl_api.json        ← DSL API 索引（自动生成，ask.py dsl 用）
│   └── rules.json          ← 铁律/范式/静默失败（结构化，ask.py law/symptom 用）
├── envelopes/              ← 已验证可打开的信封模板
│   ├── 球体物理.bcm4       ← 主信封（2 角色；挂载时取「引擎」壳）
│   └── 空白作品.bcm4       ← 最小信封（验证边界用）
├── examples/
│   └── poorphy/            ← 完整示例：刚体物理沙盒（含 VM 闭环测试）
│       ├── content.js      ←   内容模块（52KB 积木逻辑，学习 DSL 范本）
│       ├── gen.js          ←   生成器（薄包装）
│       ├── vm_test_poorphy.py ← 块图 VM 测试（VM 解释器部分可复用于任何作品）
│       ├── PoorPhy.bcm4    ←   产出（默认测试目标）
│       └── check_all.sh    ←   示例一键全流程
├── projects/               ← 你的项目（scaffold.py 生成；.gitkeep 占位）
├── out/                    ← 生成产物（.gitignore 忽略）
└── reference_works/        ← 真实作品（查询/对照用，不参与生成）
    ├── florr合卡.bcm4      ← 过程(函数)的紧凑实例
    ├── 球体物理   ← 列表,计算块
    └── 预瞄.bcm4          ← 计算快,侦测类
```

## 三条上手路径

| 场景 | 命令 |
|---|---|
| **起新作品**（推荐） | `python tools/scaffold.py 我的作品` → 改 `projects/我的作品/content.js` → `bash projects/我的作品/check.sh` |
| **跑通示例** | `bash examples/poorphy/check_all.sh`（生成 + 校验 + VM 240 帧闭环测试） |
| **学习 DSL** | 读 `tools/template_work.js`（从零搭最小作品）→ `node tools/template_work.js` → `out/我的作品(模板).bcm4` |

```js
const { root: TOOLS_ROOT, requireTool, dataPath } = require("./kitten4_root.js");
const K = requireTool("bcm4gen.js");
```

### 读懂任意已有作品
python tools/bcm4_read.py reference_works/florr合卡.bcm4

### 校验任意作品（发布门禁）
bash tools/check_all.sh out/我的作品.bcm4 [vm_test.py]

### 仓库自检（知识库一致 + 示例全流程）
bash tools/check_repo.sh [--full]

### 空白基础作品（快速验证编辑器链路）
node tools/gen_basic.js
