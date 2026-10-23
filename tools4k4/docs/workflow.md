# 工作流 —— 从起项目到发布

三类场景：**起新作品**、**日常迭代**、**发布前检查**；外加「VM 闭环测试怎么写」。
所有命令假设当前目录是仓库根（`tools4k4/`，clone 后叫什么无所谓，进根目录即可）。

---

## 一、起一个新作品（5 分钟）

```bash
# 1. 生成骨架
python tools/scaffold.py 我的作品
#    → projects/我的作品/{content.js, gen.js, check.sh, README.md}

# 2. 先跑通空骨架（验证工具链 + 编辑器链路）
cd projects/我的作品 && bash check.sh
#    → out/我的作品.bcm4，拖进 kitten4 编辑器：应看到蓝点角色，
#      点击它得分 +1，得分 >5 变半透明

# 3. 写你的逻辑：只改 content.js
```

**content.js 怎么写**：照抄 `examples/poorphy/content.js` 的对应模式
（变量/列表/过程/循环/帽子），或 `tools/template_work.js` 的 DSL 用法。
不确定积木结构时先 `python ../../tools/query_block.py --type <type>` 再写。

**多角色/多背景**：`gen_mount.js` 目前只挂载 build(K) 生成的**第一个** actor。
多角色需在 content.js 里 `K.defActor` 多个，并自行扩展 gen.js 的挂载段
（信封里有几个角色壳就替换几个；引擎壳 = 积木最多的那个）。

---

## 二、日常迭代（改 → 生成 → 校验）

```bash
# 改完 content.js：
bash check.sh                                   # 或：node gen.js && bash ../../tools/check_all.sh out/我的作品.bcm4
```

| 校验器 | 查什么 | 失败意味 |
|---|---|---|
| `validate_bcm4.py` | 信封 schema、非法键（compile_result/current_*）、交叉引用 | 编辑器打不开或退化 |
| `check_connections.js` | 每个块都有 connections 条目（铁律 4） | 编辑器能打开但脚本区空白、一动就报错 |
| `verify_procedures.py` | 过程定义/调用的 shadows+mutation 完整 | 带函数的作品反序列化崩溃 |
| `vm_test_*.py` | 块图解释器真执行 vs 参考模型，逐帧位级对比 | 物理/逻辑与意图不符（**行为级**门禁） |

**编辑器验收**（最终裁判）：把 `out/*.bcm4` 拖进 kitten4 编辑器，
点绿旗/点角色跑一遍，看舞台表现。校验器全过 ≠ 玩法一定对，但能挡住 90% 的格式坑。

---

## 三、发布前检查

```bash
bash tools/check_all.sh out/我的作品.bcm4 vm_test.py   # 有 VM 测试就带上
# 人工过一遍 docs/block_reference.md 的 15 条铁律（尤其 3/4/6/11）
git status          # 确认 out/ 未被提交；projects/ 里没有私有作品
git add -A && git commit -m "..."
```

---

## 四、VM 闭环测试怎么写（进阶，玩法复杂后必做）

问题：Python 原型对 ≠ 积木翻译对。`examples/poorphy/vm_test_poorphy.py`
提供了一个**块图虚拟机**（VM 类：真解释 .bcm4 的 blocks/connections），
用法是「VM 执行积木 vs Python 参考模型，逐帧逐项位级对比」。

复用它：
1. `cp examples/poorphy/vm_test_poorphy.py projects/我的作品/vm_test.py`
2. 把参考模型（`Ref` 类）换成你的玩法逻辑；保留 VM 类与 `cmp_state` 框架
3. 脚本化输入（按键/鼠标/点击事件序列），跑 N 帧对比

**参考模型必须与积木位级一致**（血泪铁律）：
- 乘法/加法结合顺序逐一对应（`(invMa+invMb)+(项A+项B)` ≠ 左结合）
- 禁 `x ** 2`（Python `**` 走 C pow()，与 `x*x` 有 0.2% 概率差 1 ULP）
- `math_round` 镜像 = `float(math.floor(v + 0.5))`，禁内置 `round()`（银行家舍入）
- 调试：1e-9 容差会放过 ULP 漂移；用精确 `==` 逐帧扫描定位首处分歧帧

---

## 五、目录约定

| 目录 | 内容 | 入 git？ |
|---|---|---|
| `projects/<名字>/` | 你的作品（content.js 为主） | 是（私有作品可自行 .gitignore） |
| `out/` | 生成产物 | 否（.gitignore） |
| `envelopes/` | 信封模板 | 是 |
| `examples/` | 完整示例（PoorPhy） | 是 |
| `reference_works/` | 真实作品（查询/对照） | 是（大作品按需） |
