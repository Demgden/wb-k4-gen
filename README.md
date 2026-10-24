# kitten4 .bcm4 基础工作模板

一套**自包含、可发布 git 仓库**的 kitten4（编程猫）`.bcm4` 作品开发基础设施：
从「起一个新项目」到「生成 + 校验 + 闭环测试」的全套工具、数据与文档。
换任何机器：`git clone` 本仓库 → `python tools/scaffold.py 我的作品` → 开工。

> **AI agent 读者**（Codex / Cursor / Continue 等）：先读 `AGENTS.md`——那是给你的入口。
> 更快的方式：`python tools/ask.py orient`（一条命令，30 秒上手，**不用读文档**）。

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
    ├── florr合卡.bcm4      ← 过程(函数)用法的紧凑实例
    └── INDEX.md            ← 大作品索引（在 Desktop，按需拷贝）
```

## 三条上手路径

| 场景 | 命令 |
|---|---|
| **起新作品**（推荐） | `python tools/scaffold.py 我的作品` → 改 `projects/我的作品/content.js` → `bash projects/我的作品/check.sh` |
| **跑通示例** | `bash examples/poorphy/check_all.sh`（生成 + 校验 + VM 240 帧闭环测试） |
| **学习 DSL** | 读 `tools/template_work.js`（从零搭最小作品）→ `node tools/template_work.js` → `out/我的作品(模板).bcm4` |

> **AI agent**：别通读文档，先 `python tools/ask.py orient`（一条命令 30 秒上手），
> 之后按需 `ask.py dsl/law/symptom/task`。详见 `AGENTS.md`。

## 项目挪出仓库怎么办

项目用 `kitten4_root.js` 定位工具链（scaffold 自动复制进项目），不要写死相对路径：

```js
const { root: TOOLS_ROOT, requireTool, dataPath } = require("./kitten4_root.js");
const K = requireTool("bcm4gen.js");
```

解析顺序：`TOOLS4K4_HOME` 环境变量 → 逐级向上找 `tools4k4/` → 常见兄弟目录 →
失败时抛出带排查建议的错误。项目完全独立时 `export TOOLS4K4_HOME=/path/to/tools4k4`。


## 核心工具速查

```bash
# ★ agent 查询入口：先 orient，再按需查（不要通读文档）
python tools/ask.py orient                 # 30 秒上手：是什么 + 该干什么 + 5 条命令
python tools/ask.py dsl cloneIdx           # 查生成 DSL：签名 + 对应积木类型 + 警告
python tools/ask.py dsl --list clone       # 按章节列出 DSL 函数
python tools/ask.py law 7                  # 查铁律（标 [库已自动] 的不必操心）
python tools/ask.py law                    # 列出全部铁律及归属
python tools/ask.py symptom 空白           # 按症状反查根因与防线
python tools/ask.py paradigm 克隆          # 查通用范式
python tools/ask.py task new               # 任务食谱：new/edit/read/debug/vm
python tools/ask.py guard                  # 交付前自检清单

# 积木特性速查（写积木前先查，别猜）
python tools/query_block.py round                # 模糊搜
python tools/query_block.py --type math_round    # 字段/输入/影子默认值
python tools/query_block.py --defs  check_key    # 定义 XML 原文
python tools/query_block.py --use  check_key     # 真实作品用例 + 字段取值分布
python tools/query_block.py --list controls_     # 前缀列举

# 读懂任意已有作品
python tools/bcm4_read.py reference_works/florr合卡.bcm4

# 校验任意作品（发布门禁）
bash tools/check_all.sh out/我的作品.bcm4 [vm_test.py]

# 仓库自检（知识库一致 + 示例全流程）
bash tools/check_repo.sh [--full]

# 空白基础作品（快速验证编辑器链路）
node tools/gen_basic.js
```

## 内容模块契约（content.js）

每个项目的 `content.js` 只做一件事：`module.exports.build = function (K) {...}`，
在 build 里用 `K.defActor / defScene / defVar / defList / script` 描述作品；
`gen.js` 负责 `loadDefs` + 挂到 `envelopes/球体物理.bcm4` + 写出。
DSL 全部助手见 `tools/bcm4gen.js` 头部注释。

## 铁律速览（完整 15 条见 docs/block_reference.md）

1. 顶层不留 `compile_result`；2. `emitChain` 返回链首；3. 每个命名输入都要有
   `shadows` 条目；4. 每个块（含叶子影子）都要有 connections 条目，否则编辑器
   能打开但脚本区空白；5. `controls_if` 是 if/else-if，阈值分支要高阈值优先；
6. 布尔积木（`mouse_down`/`check_key`）输出 Boolean，`true≠1`，IF 条件直用布尔变量；
7. `math_round` = JS `Math.round`，Python 镜像禁写内置 `round()`；
8. VM 参考模型必须与积木浮点结合顺序位级一致（禁 `x**2`，显式写 `x*x`）；
9. `lists_replace` 越界 = 静默空操作，列表必须先 `listAdd` 扩容到位；
10. 状态列表按容量上限预扩展（含易漏的 `边数`/`刚R`）；
11. 可点击角色必须 `visible:true`；
12. 背景用真 scene 不用角色；
13. 参数化按键范式：一键循环切参数（存可见变量）+ 一键执行；
14. 一步执行(warp)包住 forever 的循环体，不是 forever 本身；
15. 多克隆体/多刚体用「每实例自匹配自己那一格」，禁外部顺序计数器扫描。

## 环境要求

Node.js + Python 3，任意 POSIX shell（Windows 用 Git Bash）。
无需 npm 依赖、无需联网、无任何机器相关绝对路径——clone 即可用。

## 发布为 git 仓库

本仓库**已完成** `git init`（main 分支，首次提交见 `git log`）。推到远程：

```bash
git remote add origin <你的仓库地址>
git push -u origin main
```

发布前检查单：
1. `git status` 确认 `out/`（生成产物）未被提交——已在 `.gitignore`
2. `projects/` 下没有不想公开的私有作品（有就移出或加 `.gitignore`）
3. 建议补一个 `LICENSE`（如 MIT）
4. 换设备验证：`git clone <地址> /tmp/t && cd /tmp/t && bash examples/poorphy/check_all.sh`

`.gitattributes` 已规定：文本统一 LF，`.bcm4`/图片按二进制（防止换行改动字节）。
