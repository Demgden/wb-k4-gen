#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ask.py — agent 的「问答入口」：查，别读。

以前 agent 拿到 tools4k4 要通读 AGENTS.md + README.md + docs/workflow.md +
docs/block_reference.md（22KB，标注「动手前必读」）+ 反推 566 行 bcm4gen.js 的 DSL，
才能开始写第一块积木 —— 光是「理解仓库」就要十几分钟、几千 token。

本工具把这些知识做成可查询的：
  orient     30 秒上手：这个仓库是什么、现在该干什么、最常用命令
  task       任务食谱（起项目/改项目/查积木/读懂作品/调试）
  dsl        查生成 DSL 函数（K.xxx）：签名 + 对应积木类型 + 注释警告
  law        查铁律（含「库已自动处理」标记，可跳过）
  symptom    按症状反查根因与防线（静默失败排查）
  paradigm   查通用范式（克隆体/背景/warp/列表…）
  guard      交付前自检清单 + 每条防线的实际命令
  blocks     透传 query_block.py（查积木结构/真实用例）

用法：
  python tools/ask.py orient
  python tools/ask.py task new
  python tools/ask.py dsl cloneIdx
  python tools/ask.py dsl --list clone
  python tools/ask.py law 7
  python tools/ask.py symptom 空白
  python tools/ask.py blocks --type math_round
"""
import json
import os
import re
import subprocess
import sys
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
DATA = os.path.join(ROOT, "data")


def dwidth(s):
    """显示宽度：CJK/全角字符占 2 列。用它做表格对齐才不会错位。"""
    w = 0
    for ch in s:
        w += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
    return w


def pad(s, width):
    """按显示宽度左对齐补空格。"""
    s = str(s)
    return s + " " * max(0, width - dwidth(s))


def load(name):
    p = os.path.join(DATA, name)
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def die(msg, code=1):
    print(msg)
    sys.exit(code)


def law_counts():
    """铁律条数从 rules.json 实时取 —— 绝不写死数字。

    写死过，然后漂了：rules.json 是 16 条，ask.py 里却写「15 条铁律」「15+1 条铁律」，
    block_reference.md 标题写「十五条」而正文编号到 16。
    门禁 verify_dsl.py 之前只比对「编号集合」（{1..16} 一致 → 通过），
    从不解析散文里的「几条」→ 计数维度是瞎的，这类漂移能一路绿灯溜过去。
    """
    rules = load("rules.json") or {}
    laws = rules.get("laws", [])
    return {
        "total": len(laws),
        "auto": sum(1 for l in laws if l.get("enforced_by") == "bcm4gen"),
        "manual": sum(1 for l in laws if l.get("enforced_by") == "manual"),
    }


# ----------------------------------------------------------------- orient
def cmd_orient(args):
    print("""== kitten4 .bcm4 开发：30 秒上手 ==

仓库 = 积木 DSL 生成器 + 已验证信封 + 三道校验 + VM 闭环测试。
工作方式：写 content.js（JS DSL 描述积木）→ 生成 .bcm4 → 校验 → 拖进 kitten4 编辑器。
硬规矩：不要手写 .bcm4 JSON，不要改 envelopes/ 里信封的结构。

【现在该干什么】按你的目标挑一条，然后直接执行，不要通读文档：
""")
    tasks = [
        ("从零做新作品", "ask.py task new      →  一键起项目"),
        ("改已有项目", "ask.py task edit     →  改 content.js 后跑 check.sh"),
        ("写某块积木前", "ask.py dsl <名字>   →  查 DSL 函数（别猜参数名）"),
        ("编辑器里出问题", "ask.py symptom <症状>  →  反查根因"),
        ("看懂别人的作品", "ask.py task read    →  反编译成伪代码"),
    ]
    for a, b in tasks:
        print("  %s%s" % (pad(a, 18), b))

    cmds = [
        ("python tools/scaffold.py <项目名>", "起新项目（唯一正确起点）"),
        ("bash projects/<项目名>/check.sh", "生成 + 校验 + 连接检查"),
        ("python tools/ask.py dsl <名字>", "查生成 DSL（写积木前必查）"),
        ("python tools/ask.py blocks --type <类型>", "查积木结构/输入/影子默认值"),
        ("bash tools/check_all.sh <作品.bcm4>", "发布门禁（信封+连接+可选 VM）"),
    ]
    print("\n【%d 条最常用命令】" % len(cmds))
    for a, b in cmds:
        print("  %s%s" % (pad(a, 46), b))

    c = law_counts()
    mistakes = [
        ("controls_if 是 if/else-if", "阈值分支必须高阈值优先排（ask.py dsl ifChain）"),
        ("布尔积木输出 Boolean，true≠1", "条件直用布尔变量，取反用 K.not（ask.py dsl not）"),
        ("math_round = floor(x+0.5)", "Python 侧禁内置 round()（ask.py law 14）"),
    ]
    print("【%d 条最容易犯的错（其余 %d 条用 ask.py law 查）】" % (len(mistakes), c["total"] - len(mistakes)))
    for i, (a, b) in enumerate(mistakes, 1):
        print("  %d. %s —— %s" % (i, a, b))

    print("""
【铁律怎么用】
  %d 条铁律里 %d 条已由 tools/bcm4gen.js 自动处理，%d 条要你自己写对，%d 条有校验器兜着。
  用 ask.py law <编号> 看哪条要你操心 —— 标 [库已自动] 的可跳过。

【更多】
  ask.py task        任务食谱    ask.py symptom  症状反查    ask.py guard  交付自检
""" % (c["total"], c["auto"], c["manual"], c["total"] - c["auto"] - c["manual"]))
    return 0


# ----------------------------------------------------------------- task
TASKS = {
    "new": """== 任务：从零做新作品 ==
  1) python tools/scaffold.py <项目名>          → 生成 projects/<项目名>/ 骨架
  2) 只改 content.js。DSL 照抄 examples/poorphy/poorphy_content.js（完整范本）
                或 tools/template_work.js（最小示例）
  3) 写每一块新积木前：python tools/ask.py dsl <名字>   （别猜参数名）
  4) bash projects/<项目名>/check.sh            → 全过，产物在 out/<项目名>.bcm4
  5) 玩法有物理/状态机/计时逻辑 → 抄 examples/poorphy/vm_test_poorphy.py
     改参考模型，做闭环测试（ask.py task vm）
  6) 拖进 kitten4 编辑器人工验收：点绿旗、点角色跑一遍""",
    "edit": """== 任务：改已有项目 ==
  1) 定位：projects/<项目名>/content.js 是唯一的逻辑源；gen.js 只是挂载信封的薄包装
  2) 改完必须重跑：bash projects/<项目名>/check.sh
     —— 本格式的失败大多是静默的（校验器全过 ≠ 对的），先看 ask.py guard
  3) 若改动涉及函数/参数：python tools/verify_procedures.py <产物.bcm4>（唯一能提前判死「打不开」）
  4) 若改动涉及物理/状态机/计时：同步改 vm_test 参考模型，跑闭环测试
     —— 参考模型必须与积木位级一致（ask.py law 13）""",
    "read": """== 任务：读懂已有 .bcm4 ==
  python tools/bcm4_read.py <作品.bcm4> [角色名过滤...] [--maxlines N] [--no-vars]
  → 输出变量/列表清单 + 每个角色/场景的脚本树（中文积木名+参数，if/else-if 正确缩进）
  大作品先看 reference_works/ 目录里的文件（florr合卡 / florr-重置版 / 预瞄）。
  查某块积木在真实作品里怎么用：python tools/ask.py blocks --use <类型>""",
    "debug": """== 任务：调试（编辑器里表现不对） ==
  1) 按症状反查：python tools/ask.py symptom <症状关键词>
     例：symptom 空白 / symptom 打不开 / symptom 不消失 / symptom 不响应
  2) 三道校验：bash tools/check_all.sh <作品.bcm4>
     validate_bcm4.py（信封+结构+类型注册表）/ check_connections.js（连接）
     verify_procedures.py（函数块契约，唯一能判死「文件打不开」）
  3) 校验全绿但行为仍错 → 查铁律里标 [需自己写对] 的条目
     python tools/ask.py law          → 列出全部并标注归属
  4) VM 与编辑器分叉 → ask.py law 13 的调试方法（精确 == 逐帧扫描定位首帧分歧）""",
    "vm": """== 任务：VM 闭环测试 ==
  1) 目的：Python 参考模型 vs 积木公式，位级一致。防「校验器全过但行为错」。
  2) 照抄 examples/poorphy/vm_test_poorphy.py 改：block 图解释器 + 参考模型 + 逐帧比对
  3) 铁律（ask.py law 13 / 14）：
     - 浮点乘加结合顺序必须与积木逐一对应
     - 禁 x ** 2（Python 的 ** 走 C pow，与 x*x 有 ULP 差）→ 写 x*x
     - math_round 镜像写 float(math.floor(v + 0.5))，禁内置 round()
     - 列表越界要抛错（这样才能抓到预扩展漏项）
  4) 跑：python <vm_test.py> <作品.bcm4>
  5) 定位分叉：精确 == 逐帧扫描找首处分歧帧 → 追踪两边 variables_set/lists_replace 写入序列
     → 逐项 repr() 对比中间量""",
}


def cmd_task(args):
    if not args:
        print("可用任务：" + " / ".join(TASKS.keys()))
        return 0
    key = args[0].lower()
    for k, v in TASKS.items():
        if key == k or key in k:
            print(v)
            return 0
    die("未知任务：%s（可用：%s）" % (args[0], " ".join(TASKS.keys())))


# ----------------------------------------------------------------- dsl
def cmd_dsl(args):
    api = load("dsl_api.json")
    if not api:
        die("data/dsl_api.json 不存在，先跑：python tools/extract_dsl_api.py")
    if not args:
        print("用法：ask.py dsl <函数名> | ask.py dsl --list [前缀]")
        return 0
    if args[0] == "--list":
        pref = args[1] if len(args) > 1 else ""
        names = [k for k in api if k.lower().startswith(pref.lower())]
        if not names:
            die("没有匹配 %r 的 DSL 函数" % pref)
        # 按源码出现顺序分组，保证同一章节的函数聚在一起（字母序会把章节打散）
        names.sort(key=lambda k: (api[k].get("section", ""), api[k].get("order", 0)))
        cur = None
        for n in names:
            sec = api[n].get("section") or "(未分组)"
            if sec != cur:
                cur = sec
                print("\n-- %s --" % sec)
            p = ",".join(x["name"] for x in api[n]["params"])
            t = "  -> " + api[n]["editor_type"] if api[n]["editor_type"] else ""
            print("  K.%s%s%s" % (pad(n, 13), pad("(" + p + ")", 30), t))
        print("\n共 %d 个。细节：ask.py dsl <名字>" % len(names))
        return 0

    key = args[0]
    if key in api:
        e = api[key]
        print("K.%s(%s)" % (key, ", ".join(
            x["name"] + ("=" + x["default"] if x["default"] else "") + ("..." if x["rest"] else "")
            for x in e["params"])))
        if e["editor_type"]:
            print("  → 积木类型: %s   （%s）" % (e["editor_type"], "返回值(reporter)" if e["reporter"] else "语句(statement)"))
        if e["doc"]:
            print("  说明: %s" % e["doc"])
        if e["warnings"]:
            print("  ⚠ %s" % e["warnings"])
        print("  查这块积木的结构: ask.py blocks --type %s" % e["editor_type"] if e["editor_type"] else "")
        return 0

    # 模糊匹配
    hits = [k for k in api if key.lower() in k.lower()]
    if not hits:
        die("没有 DSL 函数 %r。列全部：ask.py dsl --list" % key)
    print("模糊匹配 %r：" % key)
    for k in sorted(hits):
        e = api[k]
        p = ",".join(x["name"] for x in e["params"])
        t = "  -> " + e["editor_type"] if e["editor_type"] else ""
        print("  K.%s%s%s" % (pad(k, 13), pad("(" + p + ")", 30), t))
    print("\n细节：ask.py dsl <名字>")


# ----------------------------------------------------------------- law
def cmd_law(args):
    rules = load("rules.json")
    if not rules:
        die("data/rules.json 不存在")
    laws = rules["laws"]
    if not args:
        c = law_counts()
        print("== %d 条铁律（标注 [库已自动] 的不必操心）==\n" % c["total"])
        for l in laws:
            tag = {"bcm4gen": "[库已自动]", "manual": "[需自己写对]", "validator": "[有校验器]"}[l["enforced_by"]]
            print("%2d. %s %s" % (l["id"], pad(l["title"], 40), tag))
        print("\n详情：ask.py law <编号>    按症状反查：ask.py symptom <关键词>")
        return 0
    try:
        n = int(args[0])
    except ValueError:
        hits = [l for l in laws if args[0].lower() in l["title"].lower() or args[0].lower() in l["keywords"]]
        if not hits:
            die("没有编号为 %s 的铁律。列出全部：ask.py law" % args[0])
        for l in hits:
            print("%2d. %s" % (l["id"], l["title"]))
        return 0
    for l in laws:
        if l["id"] == n:
            tag = {"bcm4gen": "[库已自动 —— 用对 DSL 助手即可]", "manual": "[需自己写对]", "validator": "[有校验器]"}[l["enforced_by"]]
            print("== 铁律 %d: %s ==\n%s\n" % (l["id"], l["title"], tag))
            print("症状: %s" % l["symptom"])
            print("根因: %s" % l["cause"])
            print("正确: %s" % l["fix"])
            print("防线: %s" % l["guard"])
            return 0
    die("没有编号为 %d 的铁律" % n)


# ----------------------------------------------------------------- symptom
def cmd_symptom(args):
    rules = load("rules.json")
    if not rules:
        die("data/rules.json 不存在")
    if not args:
        print("用法：ask.py symptom <症状关键词>")
        print("\n已知静默失败症状：")
        for s in rules["silent_failures"]:
            print("  - %s" % s["symptom"])
        return 0
    q = args[0].lower()
    laws = rules["laws"]
    hits = []
    for l in laws:
        blob = " ".join([l["title"], l["symptom"], l["cause"], l["fix"]] + l["keywords"]).lower()
        if q in blob:
            hits.append(l)
    for s in rules["silent_failures"]:
        blob = (s["symptom"] + " " + s["cause"] + " " + s["guard"]).lower()
        if q in blob:
            hits.append(("S", s))
    if not hits:
        print("没有匹配 %r 的已知症状。" % args[0])
        print("换词试试：空白 / 打不开 / 不消失 / 不响应 / 偏移 / 空白 / 恒0 / 分叉 / 损坏")
        print("或：ask.py symptom（不带参数列出全部已知症状）")
        return 0
    print("== 匹配 %r 的 %d 条 ==\n" % (args[0], len(hits)))
    for h in hits:
        if isinstance(h, tuple):
            s = h[1]
            print("症状: %s" % s["symptom"])
            print("根因: %s" % s["cause"])
            print("防线: %s" % s["guard"])
            print()
        else:
            tag = {"bcm4gen": "[库已自动]", "manual": "[需自己写对]", "validator": "[有校验器]"}[h["enforced_by"]]
            print("铁律 %d: %s  %s" % (h["id"], h["title"], tag))
            print("  根因: %s" % h["cause"])
            print("  正确: %s" % h["fix"])
            print("  防线: %s" % h["guard"])
            print()


# ----------------------------------------------------------------- paradigm
def cmd_paradigm(args):
    rules = load("rules.json")
    if not rules:
        die("data/rules.json 不存在")
    ps = rules["paradigms"]
    if not args:
        print("== 通用正确范式 ==")
        for p in ps:
            print("  - %s" % p["title"])
        print("\n详情：ask.py paradigm <关键词>")
        return 0
    q = args[0].lower()
    for p in ps:
        blob = (p["title"] + " " + p["rule"] + " " + " ".join(p["keywords"])).lower()
        if q in blob:
            print("== %s ==\n%s\n" % (p["title"], p["rule"]))
            print("相关 API: " + "  ".join("K." + a for a in p["api"]))
            print("查签名: ask.py dsl %s" % p["api"][0])
            return 0
    die("没有匹配 %r 的范式。列出全部：ask.py paradigm" % args[0])


# ----------------------------------------------------------------- guard
def cmd_guard(args):
    rules = load("rules.json")
    print("== 交付前自检清单 ==\n")
    print("□ bash projects/<项目名>/check.sh 全过（信封 0 errors + 连接完整）")
    print("□ 有 VM 测试的：闭环测试 PASS（ask.py task vm）")
    print("□ 改过函数的：python tools/verify_procedures.py <产物.bcm4>")
    print("□ 产物已拖进 kitten4 编辑器人工验收（点绿旗 / 点角色跑一遍）")
    print("□ 没手改任何 .bcm4；没改 envelopes/ 里信封的结构")
    print("□ 新写的积木都先过 ask.py dsl 确认签名（别猜参数名）")
    print("□ 索引/造型：可点击角色 visible:true；造型是真实 SVG/PNG（不是 1×1 透明占位）")
    print()
    print("== 三道校验 ==")
    print("  python tools/validate_bcm4.py <file.bcm4>    信封/结构/类型注册表")
    print("  node tools/check_connections.js <file.bcm4>  连接完整性")
    print("  python tools/verify_procedures.py <file.bcm4> 函数块契约（唯一能判死「打不开」）")
    print()
    if rules:
        print("== 静默失败速查（校验器全过 ≠ 对的）==")
        for s in rules["silent_failures"]:
            print("  %-46s ← %s" % (s["symptom"], s["cause"]))


# ----------------------------------------------------------------- blocks
def cmd_blocks(args):
    cmd = [sys.executable, os.path.join(HERE, "query_block.py")] + args
    return subprocess.call(cmd)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 0
    cmd = sys.argv[1]
    rest = sys.argv[2:]
    table = {
        "orient": cmd_orient, "task": cmd_task, "dsl": cmd_dsl, "law": cmd_law,
        "symptom": cmd_symptom, "paradigm": cmd_paradigm, "guard": cmd_guard, "blocks": cmd_blocks,
    }
    if cmd in table:
        return table[cmd](rest)
    if cmd in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    die("未知子命令 %r。可用：%s" % (cmd, " ".join(table.keys())))


if __name__ == "__main__":
    sys.exit(main())
