# AGENTS.md — AI agent 工作入口

> 本文件是给 AI coding agent（Codex / Cursor / Continue / WorkBuddy 等）的入口。
> 你被雇来做 kitten4 `.bcm4` 作品开发。读完本文件即可开工，细节按文中指引深入。
> 人类读者请从 `README.md` 开始。

## 0. 这个仓库是什么

kitten4（编程猫）`.bcm4` 作品开发基础设施：**积木 DSL 生成器 + 已验证信封 + 校验器 + 块图 VM 闭环测试**。
核心工作方式：写 `content.js`（JS DSL 描述积木）→ 生成 `.bcm4` → 校验 → 拖进 kitten4 编辑器。
**不要手写 `.bcm4` JSON**，不要改信封模板的既有结构。

## 1. 命令速查（先背这几个）

```bash
# 起新项目（唯一正确的起点）
python tools/scaffold.py <项目名>
cd projects/<项目名> && bash check.sh      # 生成 out/<项目名>.bcm4 + 信封校验 + 连接校验

# 跑完整示例（验证工具链本身是好的）
bash examples/poorphy/check_all.sh          # 含 VM 240 帧位级闭环测试

# 写任何积木之前，先查它的真实结构（禁止凭记忆/猜）
python tools/query_block.py --type <block_type>    # 字段/输入/影子默认值
python tools/query_block.py --use  <block_type>    # 真实作品里的用法 + 字段取值分布
python tools/query_block.py <关键词>                # 模糊搜类型名

# 读懂任意已有作品（反编译为可读伪代码）
python tools/bcm4_read.py <某作品.bcm4>

# 校验任意作品（发布门禁）
bash tools/check_all.sh <作品.bcm4> [vm_test.py]
```

环境：Node.js + Python 3 + POSIX shell（Windows 用 Git Bash）。无 npm 依赖、不联网。
**Git Bash 注意**：脚本内取绝对路径必须 `pwd -W`（`pwd` 返回 `/g/...` MSYS 路径，传给原生 Windows python/node 会变 `G:\g\...`）。

## 2. 任务食谱

### A. 从零做新作品
1. `python tools/scaffold.py <名字>` → `projects/<名字>/`（content.js / gen.js / check.sh / README.md）
2. 只改 `content.js`。DSL 用法照抄 `examples/poorphy/poorphy_content.js`（范本）或 `tools/template_work.js`（最小）
3. `bash check.sh` 全过 → 产物在 `out/<名字>.bcm4`，拖进 kitten4 编辑器验收
4. 玩法有物理/状态机/计时逻辑 → 抄 `examples/poorphy/vm_test_poorphy.py` 改参考模型，做闭环测试

### B. 改已有项目
改 `projects/<名字>/content.js` → `bash check.sh` → 校验全过再交付。
改完必须重跑校验——本格式的失败大多是**静默的**（见第 4 节）。

### C. 查积木语义（写每一块新积木前必做）
```bash
python tools/query_block.py --type math_round     # 结构：fields / inputs / shadows
python tools/query_block.py --use  check_key      # 真实用例：key 字段合法取值
```
权威数据：`data/block_defs.json`（144 积木影子模板）+ `data/block_struct.json`（329 积木结构摘要）+ `reference_works/` 真实作品。

### D. 读懂别人的 .bcm4
`python tools/bcm4_read.py <文件>` 反编译成伪代码；大作品先看 `reference_works/INDEX.md` 的索引。

## 3. 铁律（违反 = 静默损坏，编辑器不报错但作品坏）

完整 15 条在 `docs/block_reference.md`（**动手前必读**）。agent 最常踩的：

1. **每个块（含叶子影子块）都必须有 connections 条目**（无子块给 `{}`）。缺 → 编辑器能打开、能运行，但脚本区空白、一动就报错。
2. **每个命名输入都要有 shadows 条目**：被真实积木占据 → phantom id 模板；字面量 → 地图内 `is_shadow` 块；语句输入 → `""`。
3. **`controls_if` 是 if/else-if（首个命中即返回）**，不是独立多 if。堆叠阈值分支必须**高阈值优先**排。
4. **布尔积木（`mouse_down` / `check_key`）输出 Boolean，`true ≠ 1`**：IF 条件直用布尔变量，取反用 `logic_negate`，禁止 `K.eq(V("按下"), N(1))`。
5. **`math_round` = JS `Math.round`（floor(x+0.5)）**；Python 镜像必须 `float(math.floor(v + 0.5))`，禁内置 `round()`（银行家舍入，.5 边界分叉）。
6. **`lists_replace` 越界 = 静默空操作**：列表必须先 `listAdd` 扩容到位再逐格写；动态增减个体时状态列表按容量上限预扩展。
7. **可点击角色必须 `visible:true`**；1×1 透明 PNG 占位 = 「造型损坏」，用真实 SVG/PNG dataURI。
8. **背景用真 scene**（`theatre.scenes`），不用「角色 + set_layer_with_pen(below)」。
9. **warp（一步执行）包住 forever 的循环体**，不是 forever 本身；warp 内禁 `repeat_forever`。
10. **VM 参考模型必须与积木浮点结合顺序位级一致**：禁 `x ** 2`（写 `x*x`），乘法/加法结合顺序逐一对应。

## 4. 静默失败清单（校验器全过 ≠ 对的，重点盯这些）

| 症状 | 根因 | 防线 |
|---|---|---|
| 编辑器能打开但脚本区空白 | 块缺 connections 条目 | `check_connections.js` |
| 一改积木就坏 | 命名输入缺 shadows | 重跑 `check_all.sh` + 人工过铁律 2 |
| 阈值分支永远走低层 | `controls_if` 低阈值排在前面 | 铁律 3，VM 测试覆盖分支 |
| 按键/鼠标交互无反应 | 布尔与数字比较（`true≠1`） | 铁律 4 |
| 新个体参数恒 0 / 读列表崩 | `lists_replace` 越界静默丢失 | 铁律 6，VM 测试的「越界抛错」语义 |
| VM 与编辑器行为分叉 | 参考模型浮点结合顺序不一致 | 铁律 10，精确 `==` 逐帧扫描定位首帧分歧 |

## 5. 目录地图

```
tools4k4/
├── tools/          通用工具：scaffold.py(起项目) gen_mount.js(信封挂载) bcm4gen.js(DSL)
│                   validate_bcm4.py check_connections.js verify_procedures.py(校验三件套)
│                   bcm4_read.py(反编译) query_block.py(积木速查) check_all.sh(门禁)
├── data/           block_defs.json(积木影子模板库) block_struct.json(结构摘要)
├── envelopes/      已验证信封：球体物理.bcm4(主) 空白作品.bcm4(最小)
├── examples/poorphy/  完整示例：content.js + gen.js + vm_test_poorphy.py + PoorPhy.bcm4
├── projects/       你的项目（scaffold 生成）
├── out/            产物（.gitignore 忽略，可随时重新生成）
├── docs/           block_reference.md(15 铁律全文) workflow.md(完整工作流)
└── reference_works/  真实作品（florr合卡.bcm4）+ INDEX.md(大作品索引)
```

## 6. 交付前自检清单

- [ ] `bash check.sh`（或 `tools/check_all.sh`）全过：信封 0 errors / 连接完整
- [ ] 有 VM 测试的：`bash examples/poorphy/check_all.sh` 式闭环 PASS
- [ ] 产物已拖进 kitten4 编辑器人工验收（点绿旗/点角色跑一遍）
- [ ] 没手改任何 `.bcm4`；没改 `envelopes/` 里信封的结构
- [ ] 新写的积木都先过 `query_block.py` 确认结构
