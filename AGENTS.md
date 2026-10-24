# AGENTS.md — AI agent 工作入口

> 本文件给 AI coding agent（Codex / Cursor / Continue / WorkBuddy 等）用。
> **不要通读 docs/ 下的文档**——有查询工具，30 秒拿到你要的那一条。
> 人类读者请从 `README.md` 开始。

## 0. 先跑这一条

```bash
python tools/ask.py orient
```

它会告诉你：这是什么仓库、现在该干什么、5 条最常用命令、3 条最容易犯的错。
**跑完直接开工，不要再翻文档。**

## 1. 这是什么

kitten4（编程猫）`.bcm4` 作品开发基础设施：**积木 DSL 生成器 + 已验证信封 + 四道校验 + VM 闭环测试**。
工作方式：写 `content.js`（JS DSL 描述积木）→ 生成 `.bcm4` → 校验 → 拖进 kitten4 编辑器。

两条硬规矩：**不要手写 `.bcm4` JSON**；**不要改 `envelopes/` 里信封的结构**。

## 2. 任务 → 命令（照着跑，不要自己找）

| 你要做的事 | 跑这条 |
|---|---|
| 从零做新作品 | `python tools/scaffold.py <名字>` → 改 `content.js` → `bash projects/<名字>/check.sh` |
| 改已有项目 | 改 `projects/<名字>/content.js` → `bash projects/<名字>/check.sh` |
| **写某块积木前**（必做） | `python tools/ask.py dsl <函数名>` —— 别猜参数名 |
| 查某积木的结构/真实用例 | `python tools/ask.py blocks --type <类型>` / `--use <类型>` |
| 编辑器里表现不对 | `python tools/ask.py symptom <症状>` —— 按症状反查根因 |
| 读懂别人的 .bcm4 | `python tools/ask.py task read` |
| 写 VM 闭环测试 | `python tools/ask.py task vm` |
| 交付前自检 | `python tools/ask.py guard` |

详细食谱：`python tools/ask.py task`（new / edit / read / debug / vm）

## 3. 铁律怎么用

16 条铁律在 `python tools/ask.py law` 里，每条都标了归属：

- **[库已自动]** —— `tools/bcm4gen.js` 已经帮你处理了，**你不用操心**，只要用对 DSL 助手。
- **[需自己写对]** —— 必须你写代码时注意，共 5 条。
- **[有校验器]** —— 写错会被校验器拦下。

> 这个标注不是口头承诺：`tools/verify_dsl.py` 会逐条核对声明与源码是否一致，对不上就报错。
> 所以「[库已自动]」是**被验证过**的，可以放心跳过。

最常踩的 3 条（其余用 `ask.py law` 查）：

1. **`controls_if` 是 if/else-if**，阈值分支必须**高阈值优先**排 → `ask.py dsl ifChain`
2. **布尔积木输出 Boolean，`true ≠ 1`** → 条件直用布尔变量，取反用 `K.not` → `ask.py dsl not`
3. **`math_round` = `floor(x+0.5)`** → Python 侧禁内置 `round()` → `ask.py law 14`

## 4. 静默失败清单（校验器全过 ≠ 对的）

| 症状 | 根因 | 防线 |
|---|---|---|
| 编辑器能打开但脚本区空白 | 块缺 connections 条目 | `check_connections.js` |
| 积木零散不连接、没输入值（≥1000 块静默吞异常） | 未注册积木类型（`math_mod`→`math_modulo`） | `validate_bcm4.py` 7c 节 |
| 有参数的文件打不开、无参数的能开 | 函数参数块类型写反 | `verify_procedures.py` |
| 一改积木就坏 | 命名输入缺 shadows | `check_connections.js` |
| 阈值分支永远走低层 | `controls_if` 低阈值在前 | VM 测试 |
| 按键/鼠标交互无反应 | 布尔与数字比较（`true≠1`） | VM 测试 |
| 新个体参数恒 0 / 读列表崩 | `lists_replace` 越界静默丢失 | VM 测试的「越界抛错」语义 |
| VM 与编辑器行为分叉 | 参考模型浮点结合顺序不一致 | 精确 `==` 逐帧扫描 |

按症状查：`python tools/ask.py symptom <关键词>`

## 5. 四道校验

```bash
python tools/validate_bcm4.py <f.bcm4>      # 信封 + 结构 + 类型注册表
node   tools/check_connections.js <f.bcm4>   # 连接完整性
python tools/verify_procedures.py <f.bcm4>   # 函数块契约（唯一能提前判死「文件打不开」）
python tools/verify_dsl.py                   # 知识库与实现一致（仓库级）
```

全跑：`bash tools/check_all.sh <f.bcm4> [vm_test.py]`
仓库自检（含 PoorPhy 示例全流程）：`bash tools/check_repo.sh [--full]`

## 5.1 项目挪目录了怎么办

**别写死 `../../tools/...` 相对路径** —— 项目一挪出仓库就全线报
`Cannot find module '../../tools/bcm4gen.js'`，接手的人要花很久才定位到根因。

用 `kitten4_root.js`（scaffold 会自动复制进项目）自动定位工具链：

```js
const { root: TOOLS_ROOT, requireTool, dataPath } = require("./kitten4_root.js");
const K = requireTool("bcm4gen.js");
const defs = dataPath("block_defs.json");
```

解析顺序：`TOOLS4K4_HOME` 环境变量 → 从项目逐级向上找 `tools4k4/` → 常见兄弟目录 →
都失败时抛出**带排查建议**的错误（而不是一句天书）。

项目完全独立时：`export TOOLS4K4_HOME=/path/to/tools4k4`。


## 6. 目录地图

```
tools4k4/
├── tools/          scaffold.py(起项目) gen_mount.js(信封挂载) bcm4gen.js(DSL)
│                   ask.py(★ 查询入口) query_block.py(积木速查) extract_dsl_api.py
│                   extract_registry.py validate_bcm4.py check_connections.js
│                   verify_procedures.py verify_dsl.py bcm4_read.py(反编译)
│                   kitten4_root.js(工具链定位·项目挪目录仍有效)
│                   check_all.sh(作品门禁) check_repo.sh(仓库门禁)
├── data/           block_defs.json(影子模板) block_struct.json(结构摘要)
│                   editor_block_types.json(编辑器注册表) dsl_api.json(DSL 索引)
│                   rules.json(铁律/范式/静默失败)
├── envelopes/      已验证信封：球体物理.bcm4(主) 空白作品.bcm4(最小)
├── examples/poorphy/  完整示例：content.js + gen.js + vm_test_poorphy.py
├── projects/       你的项目（scaffold 生成）
├── out/            产物（gitignore）
├── docs/           block_reference.md(铁律全文·按需查) workflow.md(完整工作流)
└── reference_works/  真实作品 + INDEX.md
```

## 7. 交付前

- [ ] `bash projects/<名字>/check.sh` 全过
- [ ] 有 VM 测试的：闭环 PASS（`ask.py task vm`）
- [ ] 改过函数的：`verify_procedures.py` 过
- [ ] 产物已拖进 kitten4 编辑器人工验收（点绿旗 / 点角色跑一遍）
- [ ] 没手改 `.bcm4`；没改 `envelopes/` 结构
- [ ] 新写的积木都先过 `ask.py dsl` 确认签名
