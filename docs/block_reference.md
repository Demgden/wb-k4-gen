# kitten4 积木参考 / Block Reference

> **按需查，不要通读。** agent 用 `python tools/ask.py law`（按编号/关键词查铁律）、
> `ask.py symptom <症状>`（按现象反查）、`ask.py dsl <函数名>`（查 DSL 签名）——
> 命中的那一条才是你要读的。本文件是这些查询的**全文底稿**。
> 另有结构化版本在 `data/rules.json`（机器可读，标注每条归谁负责）。

供 AI「生成」与「看懂」`.bcm4` 时使用。配套文件：
- `data/block_defs.json` — 144 种积木的默认 shadow 模板（编辑器自带 define_block_xml 源），`bcm4gen.js` 用它补全每个值输入的 shadow。
- `data/block_struct.json` — 329 种积木的完整结构（输入名/字段名），生成器做连接校验的依据。
- `data/editor_block_types.json` — 876 种积木类型注册表（哪些 type 名编辑器真的认）。
- `data/dsl_api.json` — 生成 DSL 的 API 索引（签名 + 对应积木类型）。
- `tools/bcm4gen.js` — 生成库（见下「生成 DSL」）。
- `tools/bcm4_read.py` — 反编译器（`.bcm4` → 中文伪代码）。
- `tools/validate_bcm4.py` / `tools/check_connections.js` — 写完必跑的两道校验。

---

## 一、十六条编辑器语义铁律
1. **移除顶层 `compile_result`**：否则编辑器只读它、忽略 `block_data_json` → 脚本区空白。`bcm4gen` 已自动剔除。
2. **`emitChain` 必须返回链首块**（供 DO/next 语句输入连接）；返链尾→双父块→Blockly 加载拽走、DO 空出、表现为「嵌套积木向右下偏移」。`bcm4gen` 已正确返回链首。
3. **`change_variable` 字段是 `valname`(变量UUID)+`method`("increase"/"decrease")，值输入名 `n`**；不是 `variables_set` 的 `VAR`。用 `K.chgV(name, val)`。
4. **`scene.group_order` 数组开头 = 最上层**（"top"→unshift）。想沉底要 reverse/插入末尾。`bcm4gen` 用 `Object.keys(groups).reverse()`。
5. **每个命名输入都要有 `shadows` 条目**：值输入被真实积木占据→phantom id 模板；字面量→地图内 is_shadow 块；语句输入→`""`。缺了编辑器能加载但一改就坏。`bcm4gen` 自动补。
6. **角色默认在画笔图层上方**会盖住笔迹；每个角色脚本首行插 `set_layer_with_pen`(position:"below")。`bcm4gen` 的 `script()` 默认带；`sceneScript()` 不带（背景是真 scene，永远最底层，不能下移）。
7. **`controls_if` 是 if/else-if（首个命中即返回），不是独立多 if**：堆叠阈值分支（如连击倍率 `>3/>7/>11/>15`）必须**高阈值优先**排，否则低阈值永远先命中、高层级永远到不了。`bcm4gen` 的 `K.ifChain([{cond,body},...,{cond:null,body}])` 即此语义。
8. **每个块——包括叶子影子块——都必须有 `connections` 条目**（无子块则 `{}`）。真实作品 blocks 数 == connections 数（球体物理 1645/1645、185/185、空白 0/0）。旧版 `bcm4gen` 只给「有子块的父块」建条目 → 268 个 math_number 叶子影子块只有 blocks 没有 connections → **编辑器按 connections 建块树时子块未注册 → 整个积木区加载失败**。症状极具迷惑性：编辑器不报错、能打开、背景/变量正常，但积木栏消失、脚本区空白、一动就出错。`bcm4gen` 的 `addBlock` 字面分支已补 `conns[id]={}`。
9. **影子块字段模式（对齐真实作品，`is_shadow:true` 块）**：`deletable:true`（球体物理全库 0 个 `deletable:false`）；reporter 影子（`lists_get`/`text`/`default_value`/音频）`is_output:true`，`math_number` 两种都有（`null` 合法）；`location:[0,0]`；`parent_id` 指父块；**shadows XML 的 id 必须与块自身 id 相同**（同 id 双挂是编辑器原生模式）。`lists_get` 只能是影子（XML 带 `inline="true"`），不能当普通真实子块；`variables_get` 永远是真实块。
10. **自定义函数调用的 ARG 输入：字面量必须转 `default_value` 影子块**（`fields:{TEXT:"25"}`、`field_extra_attr:{TEXT:{has_been_edited:true}}`、XML `<field has_been_edited="true" name="TEXT">25</field>`）。真实作品铁证：球体物理 call ARG 子块里 `math_number` 出现 **0 例**。`bcm4gen` 已自动转换。
11. **函数「定义」上的参数块与函数体里「引用」参数是两种不同类型，写错 → 整个文件打不开**：
    - 定义块的 `PARAMS0/PARAMS1/...` 输入上挂的必须是 **`procedures_2_stable_parameter`**，`fields:{param_name:"x", param_default_value:""}`，`is_output:true`、`parent_id`=定义块。
    - 函数体内引用参数是 **`procedures_2_parameter`**，`fields:{param_name:"x"}`（无 `param_default_value`）。
    - 规范来源：`ts2kitten-main/blockly.js` 头注释 + 真实作品 球体物理（能打开）实测（DEF-PARAM 25 个全是 stable_parameter，BODY-USE 165 个全是 parameter）。
    - 症状极具迷惑性：**凡是带参数的函数定义所在文件一律打不开**（编辑器不报错、能打开背景/变量，但积木栏消失、脚本区空白）。对照实验：12 个函数定义里 5 个无参数能开、7 个有参数全打不开 → 100% 吻合。
    - **排查铁律**：若「无参数的文件能开、有参数的文件打不开」，第一反应查这条，不要再去查连接图/字段/XML（那些都会全绿，白费时间）。
12. **布尔积木语义：`mouse_down`/`check_key` 返回 Boolean，编辑器里 `true ≠ 1`、`false ≠ 0`**（2026-10-23 PoorPhy 实测）：`logic_compare EQ` 把布尔与数字视为不相等 → 凡用 `K.eq(V("按下"), N(1))` / `K.eq(V("上鼠标"), N(0))` 做边沿检测的写法**永远不成立**（症状：鼠标抓取/空格暂停/S单步/R重置全部失灵，但不报错）。正确写法：IF 条件**直用布尔变量**（`cond: V("按下")`），取反用 `logic_negate`（`K.not(V("上鼠标"))`）。布尔值存进普通变量合法（变量是 any 类型）；真实作品先例：`controls_if IF0 <- variables_get`、`logic_negate BOOL <- variables_get`、`logic_operation B <- check_key` 均存在。
13. **VM 闭环测试：Python 参考模型必须与积木公式「位级」一致，不是 1e-9 一致**（2026-10-23 血泪， PoorPhy 帧190 大分叉的根因）：浮点乘法/加法**不满足结合律**，参考模型若与积木的结合顺序不同就产生 ULP 漂移，会在「支撑点近平局」（SAT 轴恰为角平分线时两顶点投影只差 ~3e-14）处比较翻转 → 放大成可见分叉，而 1e-9 的 cmp 容差全程放过了它。三条对齐规则：
    - **乘法结合顺序逐一对应**：积木 `1/((0.5*m)*(r*r))` ≠ Python  `1/(((0.5*m)*r)*r)`；积木 `(invMa+invMb)+(项A+项B)` ≠ Python 左结合 `((invMa+invMb)+项A)+项B`。
    - **绝不写 `x ** 2`**：Python `**` 走 C `pow()`，与 `x*x` 有 0.2% 概率差 1 ULP；积木是乘法，参考模型必须写显式 `x*x`。
    - **调试方法**：用「精确 `==` 逐帧扫描」定位首处分歧帧 → 对该帧追踪 VM 侧 `variables_set`/`lists_replace` 写入序列与参考模型侧同名函数 → 逐项 `repr()` 对比中间量，找第一个不同的数。
14. **`math_round`（四舍五入）语义与取整边界**（2026-10-23 PoorPhy 实测）：块结构 `type:"math_round"` + `fields:{OP:"ROUND"}`（另两个选项 ROUNDUP=Math.ceil / ROUNDDOWN=Math.floor），NUM 是 `input_shadow`（block_defs.json 模板默认值 3.1，被真实 reporter 占据时自动生成 phantom 影子，无需手工补 shadows）。 kitten4 编译为 **JS `Math.round`**（floor(x+0.5)），Python 镜像必须写 `float(math.floor(v + 0.5))`——写内置 `round()`（银行家舍入）会在 .5 边界与 VM 假分叉。**取整策略（用户 2026-10-23 最终裁定）**：编辑器坐标显示自动保留 1 位，渲染层无需取整；**允许对「大量级标量」取整**（世界顶点 ±600、位置积分输出 ±600、抓取目标 → 相对误差 ≤0.08%，大幅削减 18 位小数运算量）；**速度/角度/角速度/单位向量/中间量不取整**（量级小，round 5.4→5 即 7% 误差，整度跳变可见棱角）。派生量（顶点）每帧重算，取整不累积；积分位置取整的已知副作用：|v|<0.5 提前静止、穿透修正 <0.5px 被容忍。也不要用 `[round of [n*10]]/10` 这类假保留小数 hack。
15. **动态刚体（运行时可增删）三件套**（2026-10-23 PoorPhy「新增刚体」功能实测）：① **所有状态列表按容量上限 `NB_MAX` 预扩展**——含容易被漏掉的 `边数`/`刚R`（它们常随初始数据 listAdd 生成，不占预扩展循环）→ G 键写第 7 槽时 `lists_replace` 越界**静默空操作**（铁律 11）→ 新刚体边数/半径恒 0 → `世界顶点(7)` 读 `边数[7]` 直接 ListIndexError 崩。VM 测试靠「读越界抛错」抓到了它。② **「当前个数」用变量（如 `体数`），不用常量**——重力/宽相位/积分/渲染/找最近全部 `rep(V("体数"), ...)`；宽相位内层 `rep(K.sub(V("体数"), V("iSTEP")), ...)`。③ **参数化按键（无文本输入积木时的范式）**：一个键循环切参数（边数 3→…→8→3，`ifChain` 回绕），值存可见变量「保存直到下次修改」；另一个键执行动作。边数上限必须 ≤ 每体顶点槽位数 `MAXV`（`slot=(i-1)*MAXV+k`，超出会写进邻体顶点槽）。新刚体质量派生式的乘法结合顺序与初始化逐字一致（位级铁律 13）。
16. **积木类型名必须在编辑器注册表内**（2026-10-24 bikeman 实测）：kitten4 的类型名与 Scratch 不完全一致——取余积木是 `math_modulo`（输入名 `DIVIDEND`/`DIVISOR`），**不是** Scratch 的 `math_mod`。未注册类型在编辑器 `json_to_workspace` 建块时抛异常；而角色 ≥1000 块走异步加载路径，异常仅被 `console.log` 吞掉 → **不报错、工作区空白、connections 树不应用到块上**（复制全部积木到别的角色会看到一堆没连接、没输入值的块）。权威名单在 `data/editor_block_types.json`（876 个，从编辑器 bundle 抽取）；`validate_bcm4.py` 第 7c 节会报 `not registered`。新增/改名积木前先 `python tools/extract_registry.py` 确认真名。

## 二、通用正确范式
- **克隆体各有状态（多克隆玩法）**：绝不用外部顺序计数器扫描克隆体——一旦有克隆体销毁，计数器与稳定索引 (`get_current_clone_index`) 错位 → 匹配不到、打不死。正确做法 = **每克隆体自匹配**：每只克隆体只读/写**自己**那一格（按 `cloneIdx()` 存进 per-clone list 槽）。命中条件全满足→自己 `dispose()` 自毁。用 `K.defRoleVar(name, actorId)` 给每只克隆体独立的变量。
- **背景必须是真实 scene，不是角色**：`theatre.scenes[SCENE_ID]`（有 styles/造型，永远最底层，含角色与画笔之下，无画笔功能）；不要用「角色 + set_layer_with_pen(below)」——否则所有角色都下移一层后图层顺序整体倒置。切换背景用 `set_costume_by_index`（index 1 基）。
- **每帧循环只跑一次，无需 `wait(0.03)` 节流**；多秒级等待（boss 闪光 0.1/0.2/0.3 等）保留。
- **同帧重复多次用 `warp` 扩展积木**：`type:"warp"` + DO 体内嵌循环，无需独立扩展注册；内部跑完再等 1 帧，故初始化全放同一个 warp 内（克隆体 init 即此）。
- **索引约定：全部 1 基**（costume(1)=第1个造型，setScene(1)=第1张背景，listGet index 1=第1项）。`bcm4gen` 的 `lit()`/helpers 已按 1 基处理。
- **列表先扩容再写入（`lists_replace` 越界是静默空操作）**：kitten4/Scratch 的「替换列表第 i 项」对越界索引**不报错、不写入**——直接对空列表 LS 赋值 → 列表恒为空 → 后续读取全 0（表现为「物理不跑/状态全零」）。正确做法：初始化里先 `K.listAdd(L, N(0))` 把列表 append 到目标长度，再 LS 逐格写。派生列表（顶点/碰撞对）同 Paradigm；`vm_test` 的参考模型 `ls()` 也是同样语义，两边必须同时预扩展。
- **造型资源必须真实**：1×1 透明 PNG 占位会被显示为「造型损坏」；背景用编辑器官方空白场景 SVG（`https://static.codemao.cn/kitten/B1iottffw` + 对应 dataURI），角色用真实尺寸 SVG/PNG。**要能被点击（`start_on_click`/`sprite_on_tap`）的角色必须 `visible:true`**——不可见角色点不到，帽子永远不触发（「不能运行」根因之一）。

## 三、warp 与 repeat_forever 帧模型（勿混用致死循环）
- `repeat_forever`：每帧驱动一次迭代（VM 每帧推进一层）。
- `warp`：一帧内跑完嵌套循环、再等一帧。运行时机制：`is_inside_warp() = is_warped || current_frame.is_warped || current_frame.n_warp_parents>0` → `step_iteration_yield` 在 warp 内**不 yield**（这才是「一步执行」效果的来源）。配额：`max_warp_iterations_per_interpreter_step=3e4`、`warp_interpreter_millisecond_time_limit=4ms`（超时只是让出控制权，不中断）、`max_procedure_calls_per_interpreter_step=5e4`。
- **warp 只能包「有界」循环**；若 warp 内包 `repeat_forever`，VM/编辑器会卡死（无法在「一帧」内展开）。
- **warp 内禁用积木仅 11 个**（extensions:["disable_inside_warp_loop"]）：`clone / play_audio / play_audio_and_wait / play_audio_and_wait_2 / play_words_audio / play_words_audio_wait / continue_pause_video / display_recognition_result / get_face_age / get_recognition_result / get_voice_volume / self_go_forward / set_camera_opcity / set_speaking_language / sync_tell / turn_on_the_camera`。**画笔块（clear_drawing/self_pen_*/self_move_to/set_pen_*）、repeat_n_times、procedures_2_callnoreturn 全部可用** → 渲染路径可安全放进 warp。
- **warp 块自身仍参与语句链**（`chain()` 给它挂 next 连接）→ 遍历主脚本找 `repeat_forever` 的代码（如 vm_test 的 split_main）无需为 warp 写特例；正确包法 = `K.onStart(K.warp([初始化]), K.forever([K.warp([循环体])]))`——warp 包住 forever 的循环体，不是 forever 本身。

## 四、生成 DSL 速查（bcm4gen.js 导出）
先 `const K = require("./bcm4gen.js"); K.loadDefs("../data/block_defs.json");`

### 项目骨架
| 意图 | 调用 |
|---|---|
| 背景(scene) | `K.defScene("背景", [styleId,...])` |
| 角色 | `K.defActor(name, [styleId,...], {x,y,scale,visible})` |
| 造型(style) | `K.defStyle(name, url, cdn?)` — url 为 dataURI 或 http(s)；cdn 可显式指定（复用官方空白背景 CDN 地址） |
| 全局变量 | `K.defVar(name, value=0, visible=false, pos=null)` |
| 列表 | `K.defList(name)` |
| 角色(克隆)变量 | `K.defRoleVar(name, actorId, value=0)` |
| 音频 | `K.addAudio(name, dataUriOrUrl)` → 返回 id，给 `K.play(id)` |
| 写脚本(角色) | `K.script(actorId, K.onStart(...body))` |
| 写脚本(克隆) | `K.cloneScript(actorId, [...body])` |
| 写脚本(背景) | `K.sceneScript(K.onStart(...body))` |
| 写出 | `K.write("out.bcm4", "作品名")` |

### 积木 → 调用
| 积木 | 调用 | 备注 |
|---|---|---|
| 当角色被点击 | `K.onStart(...stmts)` / `K.onClone(...stmts)` | 绿旗/克隆帽 |
| 重复 N 次 | `K.repeatN(K.N(n) 或 表达式, [...body])` | times 接节点 |
| 重复执行 | `K.forever([...body])` | DO 接链 |
| 如果…否则 | `K.ifChain([{cond, body}, {cond, body}, {cond:null, body}])` | **if/else-if，高阈值优先** |
| 一步执行(warp) | `K.warp([...body])` | 仅包有界循环 |
| 移动 N 步 | `K.move(n)` | `self_go_forward`，输入名 `steps` |
| 移到 x,y | `K.moveTo(x, y)` | |
| 右/左转 | `K.turn(deg)` | |
| 改变坐标 | `K.chgCoord("x"|"y", "increase"|"decrease", val)` | |
| 显示/隐藏 | `K.appear()` / `K.hide()` | |
| 切换造型 | `K.costume(i)` | i 1 基 |
| 逐渐消失/显示 | `K.fade(t)` / `K.self_gradually_show?` | |
| 说/大小 | `K.scaleUp(v)` / `K.shake(t)` | |
| 画笔 | `K.penDown()` `K.penUp()` `K.penColor(c)` `K.penSize(s)` `K.clearDraw()` `K.imageStamp()` | |
| 克隆 | `K.mirror(actorId)` 创建 / `K.dispose()` 自毁 / `K.cloneIdx()` 当前克隆序号 / `K.cloneNum(actorId)` | |
| 坐标读取 | `K.getX()` `K.getY()` `K.mouseX()` `K.mouseY()` `K.mDown()` | |
| 变量 | `K.V(name)` 读 / `K.setV(name, val)` 设 / `K.chgV(name, val)` 增减 | |
| 列表 | `K.LST(name)` 读 / `K.listAdd(l,v)` / `K.listSet(l,i,v)` / `K.listGet(l,i)` / `K.listLen(l)` | |
| 运算 | `K.add/sub/mul/div(a,b)` `K.eq/ne/gt/lt/gte/lte(a,b)` `K.and/or/not(a,b)` `K.abs/sqrt(a)` `K.rnd(a,b)` `K.mod(a,b)` `K.N(数字)` | 算子节点自带 `out:true` |
| 音频 | `K.play(id)` `K.stopAud(id)` | id 来自 `K.addAudio` |
| 等待 | `K.wait(t)` | |

### 字面量与表达式
- 数字字面量：`K.N(10)`（也可直接传裸数字给 `move/wait/costume...`，helpers 内部用 `lit()` 自动包）。
- 传表达式：所有 helper 的标量参数都接受「节点」（如 `K.move(K.add(K.V("步"), K.N(1)))`），`lit()` 会原样透传，避免 `N(N(x))` 把值变 `[object Object]`。
- 串链：`K.chain(a, b, c)` 把若干语句连成链（helpers 内部已用）。

## 五、看懂 .bcm4（bcm4_read.py）
```
python bcm4_read.py <作品>.bcm4 [角色/场景名过滤...] [--maxlines N] [--no-vars]
```
输出：变量/列表清单 + 每个角色/场景的脚本树（中文积木名+参数，if/else-if 正确缩进）。
复杂作品加 `--maxlines` 限行；按名字过滤只看某角色；真实作品可直接读（已验证 7MB/10 角色/87 变量）。

## 六、写完必跑的校验
```
node check_connections.js out.bcm4     # 连接（输入名/类型）必须 ALL CONNECTIONS OK
python validate_bcm4.py out.bcm4       # 顶层键/块数/造型数，必须 0 errors 0 warnings
python verify_procedures.py out.bcm4   # ★ 过程块契约（复刻编辑器加载断言），必须 ✓
```
三道都过，再用 `bcm4_read.py` 反编译回读一次，确认行为与预期一致（生成↔反编译闭环）。

### ★ `verify_procedures.py`：唯一能提前判死「文件打不开」的专项校验
`validate_bcm4.py` 查的是信封/结构；**「编辑器打不开」这个故障由编辑器内部的 `assert` 决定**，
静态结构全绿也可能照样打不开。`verify_procedures.py` 把编辑器 JSON loader（bundle 模块 `FlGc`）
的过程块断言原样复刻：
- DEF 块 `fields.NAME` 非空（`assert(name)`）
- DEF 块每个 `PARAMS<n>` 输入连上的块 **必须是 `procedures_2_stable_parameter`**（`assert(t.type === PARAM_ON_BLOCK)`）★致命
- 该参数块必须有非空的 `param_name`（`assert(param_name)`）★致命
- CALL 块 `fields.NAME` 非空；mutation 里每个 `<procedures_2_parameter_shadow name="X">` 恰好含 1 个 `name=""`
- `def_id` 找不到对应定义 → 仅警告（编辑器会回退到按名字查找，不致命）

标定：真实作品 球体物理 ✓、空白 基础.bcm4 ✓、人为把参数块改回 `procedures_2_parameter` 的反例 ✗（32 条致命）。
**改任何涉及函数的生成逻辑后，必须跑这一道。**

## 七、编辑器信封格式不变量（2026-10-23 实战修正，违反任意一条 → 编辑器拒绝打开）

以真实作品（4.11.20 保存）为基准逐字段 diff 得出，`validate_bcm4.py` 第 8 节已固化为检查：

1. **`codemao_value` 不能是 null**；整数（球体物理 `332857612`）或字符串（空白作品 `"333123015"`）均可，别过度约束成「必须整数」。
2. **theatre 禁写三键**：`current_entity` / `current_scene` / `style_collections`——真实作品没有，多写会触发严格校验失败。
3. **场景必须自持背景造型**：`scene.styles` 非空、`current_style_id ∈ styles` 且能在 `theatre.styles` 注册表解析到。旧版 `defScene` 丢 styleIds 导致 `styles:[]`+悬空引用，是「生成成功但打不开」的头号根因。
4. **style 的 `rotate_center_painter` 建议含**（球体物理有、空白作品没有也能开）——不是硬性；含上无副作用。
5. **`toolbox` 必须含 `lang`/`cellphone`/`pen` 三键**（真实作品取值 `lang/cellphone/pen:false`、`advanced/cloud_variable:true`、`current_type:"procedure"`）。
6. 可达性检查把 `procedures_2_defnoreturn`/`return_value` **也当根**——函数定义在编辑器里本就是顶层脚本，只认 hat 根会把过程式作品整片误报 unreachable。
7. **块图三一致性**（`check_connections.js` 之外还必须查）：① 每个块都有 connections 条目（铁律 8）；② `parent_id` 与 connections 父子关系完全互指；③ 影子块的 shadows XML id == 块自身 id。写个 30 秒的 Python diff 脚本全量 Assert，比凭眼睛看可靠。

排查方法：拿一个**确定能打开**的真实作品做结构级 diff（顶层键集 / actor 键集 / scene 键集 / style 键集 / toolbox 键集 + 标量字段类型），逐项对齐，不要凭模板猜。

## 八、kitten4 编辑器 bundle = 权威规格（2026-10-23 发现，强烈建议先查它再猜）
`tools/kitten.js`（5.4 MB，webpack 打包的编辑器真身，`window.__JS_RETRY__["kitten.*.js"]`）
里有**全部块定义、加载器、断言**。比任何猜测都权威，排查必看。
（编辑器真身 kitten.js，约 5.4 MB；本地路径因机器而异，可在 K4xAI/tools/ 或 Desktop/kitten4作品/tools/ 找到）

**怎么用**（bundle 是压缩单行，按关键字切片看）：
```bash
python - <<'PY'
src=open("kitten.js",encoding="utf-8",errors="replace").read()
i=src.find("procedures_2_stable_parameter")
print(src[max(0,i-1500):i+1500])
PY
```
常用定位点：
| 关键字 | 是什么 |
|---|---|
| `wwgp` 模块 | 过程块常量表：`PARAM_ON_BLOCK="procedures_2_stable_parameter"`、`PARAM="procedures_2_parameter"`、`PARAM_PREFIX="PARAMS"`、`ARG_PREFIX="ARG"`、`PARAM_NAME="param_name"`、`PARAM_DEFAULT_VALUE="param_default_value"` |
| `FlGc` 模块 | **bcm4 JSON loader**（`load_from_json`）——`.bcm4` 的 block_data_json 走这里，里面有全部致命 `assert` |
| `VCTP` 模块 | XML loader（`load_from_xml`） |
| `n/Yo` 模块 | `ProcedureManager`（`load_def_from_block` 读参数、`get_procedure_by_def`） |
| `5cXv` 模块 | `register_procedure_blocks`（过程积木的 Blockly 定义） |
| `block_data_json` | 出现处即编辑器保存/加载 block 数据的入口（`reset_element_ids` 等） |

**关键机制（铁律 11 的原理）**：编辑器加载 DEF 块时，对每个 `PARAMS<n>` 输入上的块执行
`assert(块存在 && 块.type === "procedures_2_stable_parameter")` 并再 `assert(param_name 非空)`。
**任何一个 DEF 块断言失败 → 整个 `load_from_json` 抛错 → 积木工作区加载失败 → 文件打不开**
（表现为：编辑器不报错、背景/变量正常，但积木栏消失、脚本区空白、一动就出错）。
所以「无参数的函数所在的文件能开、有参数的函数所在的文件打不开」就是这个原因。
