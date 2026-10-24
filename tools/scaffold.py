#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""scaffold.py — 一键起一个新 .bcm4 项目骨架。

用法：
  python tools/scaffold.py <项目名>

生成 projects/<项目名>/ ：
  content.js   内容模块（积木逻辑写这里；module.exports.build = K => {...}）
  gen.js       生成器（薄包装：content.js + tools/gen_mount.js 挂到已验证信封）
  check.sh     一键：生成 → 信封校验 → 连接完整性
  README.md    本项目说明

产物默认写到仓库根的 out/<项目名>.bcm4（.gitignore 已忽略）。
项目名仅限中英文/数字/连字符/下划线。
"""
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

# 28px 蓝点 SVG（真实 dataURI——1x1 透明 PNG 占位会被编辑器判「造型损坏」）
DOT_B64 = ("PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyOCIgaGVpZ2h0PSIyOCIgdmlld0JveD0i"
           "MCAwIDI4IDI4Ij48Y2lyY2xlIGN4PSIxNCIgY3k9IjE0IiByPSIxMSIgZmlsbD0iIzRGQzNGNyIgZmlsbC1vcGFjaXR5PSIw"
           "Ljg1IiBzdHJva2U9IiMwMjg4RDEiIHN0cm9rZS13aWR0aD0iMi41Ii8+PC9zdmc+")

CONTENT_JS = '''#!/usr/bin/env node
"use strict";
/**
 * content.js — __NAME__ 的内容模块（纯内容，不写文件）。
 * 约定：module.exports.build = function (K) { ... }，在 build 里描述整个作品。
 * 可用 API 见 tools/bcm4gen.js 头部注释；语义铁律见 docs/block_reference.md。
 */
module.exports.build = function (K) {
  // ---- 造型（真实 SVG dataURI；1x1 透明 PNG 占位 = 「造型损坏」，不可用）----
  const DOT = "data:image/svg+xml;base64,''' + DOT_B64 + '''";
  const dot = K.defStyle("dot", DOT);

  // ---- 角色（必须 visible:true——不可见角色点不到，start_on_click 不触发）----
  const ACTOR = K.defActor("角色", [dot], { x: 0, y: 0, scale: 100, visible: true });

  // ---- 变量（visible:true 会显示在舞台上）----
  K.defVar("得分", 0, true, { x: 500, y: 300 });

  // ---- 脚本 1：点击角色 → 得分 +1 ----
  K.script(ACTOR, K.onStart(
    K.chgV("得分", K.N(1))
  ));

  // ---- 脚本 2：永久循环，按得分改透明度（演示 变量读取 + ifChain 兜底分支）----
  K.script(ACTOR, K.onStart(
    K.forever([
      K.ifChain([
        { cond: K.gt(K.V("得分"), K.N(5)), body: [ K.fade(K.N(0.5)) ] },
        { cond: null, body: [ K.appear() ] },     // cond:null = 末位兜底（否则）
      ]),
      K.wait(0.1),
    ])
  ));

  return { nDef: 0, nCall: 0, nRet: 0 };
};
'''

GEN_JS = '''#!/usr/bin/env node
"use strict";
/**
 * gen.js — __NAME__ 生成器。用法：node gen.js [信封.bcm4] [输出.bcm4]
 *
 * 工具链定位不用写死相对路径：项目被移出仓库后仍能找到 tools4k4。
 * 找不到时设环境变量 TOOLS4K4_HOME 指向工具链根目录。
 */
const path = require("path");
const fs = require("fs");
const { root: TOOLS_ROOT, requireTool, dataPath } = require("./kitten4_root.js");
const { mount } = requireTool("gen_mount.js");   // requireTool 内部已完成 require
const { build } = require("./content.js");

// 产物统一放到工具链的 out/ 下（与仓库布局一致；项目挪目录也不影响）
const OUT_DIR = process.env.KITTEN4_OUT_DIR || path.join(TOOLS_ROOT, "out");
if (!fs.existsSync(OUT_DIR)) fs.mkdirSync(OUT_DIR, { recursive: true });

mount({
  build,
  defsPath: dataPath("block_defs.json"),
  envelope: process.argv[2] || path.join(TOOLS_ROOT, "envelopes", "球体物理.bcm4"),
  projectName: "__NAME__",
  outPath: process.argv[3] || path.join(OUT_DIR, "__NAME__.bcm4"),
});
'''

CHECK_SH = '''#!/usr/bin/env bash
# __NAME__ 一键：生成 → 信封校验 → 连接完整性
# 工具链定位：统一走 kitten4_root.js（与 gen.js 同一个解析器），项目挪目录也不失效。
# 也可用环境变量 TOOLS4K4_HOME 显式指定工具链根。
set -e
cd "$(dirname "$0")"
HERE="$(pwd -W)"                      # Windows 风格绝对路径（pwd 默认返回 /g/...，传给原生 python/node 会变 G://g//...）

if [ -n "${TOOLS4K4_HOME:-}" ]; then
  TOOLS="$(cd "$TOOLS4K4_HOME" && pwd -W)"
else
  TOOLS="$(node -e "process.stdout.write(require(process.argv[1]).root)" "$HERE/kitten4_root.js")"
fi
WORK="$TOOLS/out/__NAME__.bcm4"

node gen.js
bash "$TOOLS/tools/check_all.sh" "$WORK"
'''

README_MD = '''# __NAME__

kitten4 .bcm4 项目（由 tools/scaffold.py 生成）。

## 开发

```bash
node gen.js        # 生成 out/__NAME__.bcm4（或 node gen.js <信封> <输出> 自选路径）
bash check.sh      # 生成 + 信封校验 + 连接完整性
```

把 `out/__NAME__.bcm4` 拖进 kitten4 编辑器即可编辑/运行。

## 改逻辑

只改 `content.js`。**不要通读文档**——查就行：

```bash
python ../../tools/ask.py orient              # 30 秒上手（先跑这个）
python ../../tools/ask.py dsl <函数名>         # 写每块积木前必查：签名 + 对应积木类型
python ../../tools/ask.py symptom <症状>      # 编辑器里出问题：按症状反查根因
python ../../tools/ask.py law                 # 铁律清单（标 [库已自动] 的可跳过）
python ../../tools/ask.py blocks --type <type>  # 查积木结构/输入/影子默认值
python ../../tools/ask.py blocks --use <type>   # 看真实作品里的用法
```

## 闭环测试（可选）

玩法变复杂后，仿照 `../../examples/poorphy/vm_test_poorphy.py` 写一个
`vm_test.py`（块图解释器 + 参考模型逐帧对比），然后：
```bash
bash ../../tools/check_all.sh "../../out/__NAME__.bcm4" vm_test.py
```
写法要点见 `python ../../tools/ask.py task vm`。
'''

# 项目自带的 AGENTS.md：让 agent 只拿到 projects/<名字>/ 目录也能快速上手，
# 不用向上找仓库根文档。
AGENTS_MD = '''# __NAME__ — agent 工作入口

kitten4 .bcm4 项目。逻辑只写在 `content.js`（JS 积木 DSL）。

**先跑这条**（别通读文档）：
```bash
python ../../tools/ask.py orient
```

## 常用

```bash
bash check.sh                                  # 生成 + 校验（改完必跑）
python ../../tools/ask.py dsl <函数名>          # 写每块积木前必查：签名/参数名/对应积木类型
python ../../tools/ask.py symptom <症状>        # 出问题：按症状反查根因
python ../../tools/ask.py law                   # 铁律（标 [库已自动] 的不必操心）
python ../../tools/ask.py task vm              # 写 VM 闭环测试
python ../../tools/ask.py guard                # 交付前自检清单
```

## 规矩

- 只改 `content.js`；`gen.js` 是挂载信封的薄包装。
- 产物在 `../../out/__NAME__.bcm4`，**不要手写 .bcm4**。
- 校验器全过 ≠ 对的：本格式的失败大多是静默的（空白/不连接/不运行）→ 看 symptom 表。
- 索引全 1 基（costume(1)=第1个造型，listGet index 1=第1项）。
'''


def main():
    if len(sys.argv) != 2 or not sys.argv[1].strip():
        print(__doc__)
        return 1
    name = sys.argv[1].strip()
    if not re.match(r"^[\w\u4e00-\u9fff-]+$", name):
        print("项目名仅限中英文/数字/连字符/下划线: %r" % name)
        return 1
    d = os.path.join(ROOT, "projects", name)
    if os.path.exists(d):
        print("已存在: %s（换个名字，或先删该目录）" % d)
        return 1
    os.makedirs(d)
    files = {
        "content.js": CONTENT_JS,
        "gen.js": GEN_JS,
        "check.sh": CHECK_SH,
        "README.md": README_MD,
        "AGENTS.md": AGENTS_MD,
    }
    for fn, body in files.items():
        with open(os.path.join(d, fn), "w", encoding="utf-8") as f:
            f.write(body.replace("__NAME__", name))
    # kitten4_root.js 原样复制进项目：项目挪出仓库后仍能定位工具链
    src = os.path.join(ROOT, "tools", "kitten4_root.js")
    if os.path.exists(src):
        with open(src, "rb") as fsrc, open(os.path.join(d, "kitten4_root.js"), "wb") as fdst:
            fdst.write(fsrc.read())
    print("已创建项目骨架: %s" % d)
    print("  content.js   积木逻辑（改这里）")
    print("  gen.js       生成器")
    print("  check.sh     一键校验")
    print("  AGENTS.md    agent 入口（先跑 ask.py orient）")
    print("  kitten4_root.js  工具链定位（项目挪目录后仍有效）")
    print()
    print("下一步：")
    print("  cd %s" % d)
    print("  python ../../tools/ask.py orient   # 30 秒上手")
    print("  bash check.sh                 # 生成 + 校验")
    print("  # 编辑 content.js 后重复上一句；产物在 out/%s.bcm4" % name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
