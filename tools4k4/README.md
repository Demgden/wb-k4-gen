# kitten4 .bcm4 基础工作模板

一套**自包含、可发布 git 仓库**的 kitten4（编程猫）`.bcm4` 作品开发基础设施：
从「起一个新项目」到「生成 + 校验 + 闭环测试」的全套工具、数据与文档。
换任何机器：`git clone` 本仓库 → `python tools/scaffold.py 我的作品` → 开工。

> **AI agent 读者**（Codex / Cursor / Continue 等）：先读 `AGENTS.md`——那是给你的入口。

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
│   ├── block_reference.md  ← 15 条编辑器语义铁律（改积木前必读，踩坑全集）
│   └── workflow.md         ← 完整工作流：新项目 / 日常迭代 / 发布前检查 / VM 测试怎么写
├── tools/                  ← 通用工具（与具体作品无关）
│   ├── scaffold.py         ← ★一键起新项目（projects/<名字>/ 骨架）
│   ├── gen_mount.js        ← ★通用「信封挂载」库（内容 → 已验证信封）
│   ├── bcm4gen.js          ← 积木 DSL 生成器库
│   ├── template_work.js    ← 从零搭建最小示例（学习 DSL 用）
│   ├── gen_basic.js        ← 生成「空白基础作品」（挂信封、清空脚本）
│   ├── validate_bcm4.py    ← 信封结构校验（schema / 交叉引用）
│   ├── check_connections.js← 连接完整性（铁律 4：每块都要有 connections 条目）
│   ├── verify_procedures.py← 过程(函数)定义/调用的 shadows+mutation 校验
│   ├── bcm4_read.py        ← 反编译任意 .bcm4 为可读伪代码（「读懂」模式）
│   ├── query_block.py      ← ★积木特性速查（字段/输入/影子/真实用例）
│   └── check_all.sh        ← 通用门禁：信封校验 + 连接完整性（+可选 VM 测试）
├── data/
│   ├── block_defs.json     ← 积木影子模板库（编辑器 define_block_xml 全集）
│   └── block_struct.json   ← 329 个积木的结构摘要
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

## 核心工具速查

```bash
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
