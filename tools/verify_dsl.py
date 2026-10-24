#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify_dsl.py — 「知识库与实现一致性」门禁。

ask.py / rules.json / dsl_api.json 是给 agent 查的知识库。知识库一旦与实现漂移，
agent 就会照着过期信息写出坏代码 —— 而且比没查还糟（它以为自己查过了）。
所以知识库必须像生成产物一样被门禁守住。

本工具检查 6 件事：
  1. dsl_api.json 与 tools/bcm4gen.js 同步（源码改了、索引没改 → 报错）
  2. dsl_api.json 里每个 editor_type 都在编辑器注册表内（抓 Scratch 名混用，如 math_mod）
  3. rules.json 每条「[库已自动]」声明的 proof 正则都能在 bcm4gen.js 匹配到
     （防止知识库宣称「库已帮你处理」而实际没处理 —— agent 会因此跳过防御）
  4. rules.json 里引用的 API 名在 dsl_api.json 中都真实存在
  5. rules.json 与 docs/block_reference.md 的铁律编号一致
  6. 散文（.md / .py 输出）里声明的「N 条铁律」等计数与 rules.json 实际条数一致
     （纯文本里的数字不可验证，必须由门禁守住 —— 否则会漂）

用法：
  python tools/verify_dsl.py            # 全查
  python tools/verify_dsl.py --quiet    # 只在失败时输出（适合 CI/门禁）
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
DATA = os.path.join(ROOT, "data")


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def main():
    quiet = "--quiet" in sys.argv
    errs, notes = [], []

    src_path = os.path.join(ROOT, "tools", "bcm4gen.js")
    api_path = os.path.join(DATA, "dsl_api.json")
    rules_path = os.path.join(DATA, "rules.json")
    reg_path = os.path.join(DATA, "editor_block_types.json")

    for p in (src_path, api_path, rules_path, reg_path):
        if not os.path.exists(p):
            print("FAIL: 缺少文件 %s" % p)
            return 1

    src = open(src_path, encoding="utf-8").read()
    api = load_json(api_path)
    rules = load_json(rules_path)
    registry = set(load_json(reg_path))

    # ---- 1. dsl_api.json 与源码同步 ----
    sys.path.insert(0, HERE)
    import extract_dsl_api
    fresh, _ = extract_dsl_api.extract()
    if fresh != api:
        only_old = set(api) - set(fresh)
        only_new = set(fresh) - set(api)
        changed = [k for k in (set(api) & set(fresh)) if api[k] != fresh[k]]
        errs.append("dsl_api.json 与 bcm4gen.js 不同步 —— 请重跑 python tools/extract_dsl_api.py")
        if only_old:
            errs.append("  已消失的导出: %s" % ", ".join(sorted(only_old)))
        if only_new:
            errs.append("  新增的导出: %s" % ", ".join(sorted(only_new)))
        if changed:
            errs.append("  描述/签名变化: %s" % ", ".join(sorted(changed)[:12]))
    else:
        notes.append("dsl_api.json 与源码同步（%d 个导出）" % len(api))

    # ---- 2. 每个 editor_type 必须在编辑器注册表内 ----
    # 这是最值钱的一条：能提前抓到「Scratch 风格类型名」类静默失败（math_mod 事故根因）
    bad_types = {}
    for name, e in api.items():
        t = e.get("editor_type")
        if t and t not in registry:
            bad_types.setdefault(t, []).append(name)
    if bad_types:
        for t, names in sorted(bad_types.items()):
            errs.append("DSL %s 产生未注册积木类型 %s（编辑器建块会抛异常 → 工作区空白）" % (", ".join(names), t))
    else:
        notes.append("全部 %d 个 DSL 产出的积木类型都在编辑器注册表内" % sum(1 for e in api.values() if e.get("editor_type")))

    # ---- 3. rules.json 的「库已自动」声明必须有源码证明 ----
    auto = [l for l in rules["laws"] if l.get("enforced_by") == "bcm4gen"]
    for l in auto:
        proof = l.get("proof")
        if not proof:
            errs.append("铁律 %d「%s」声明 [库已自动] 但没有 proof —— 无法核实" % (l["id"], l["title"]))
            continue
        if isinstance(proof, str):
            proof = [proof]
        for r in proof:
            if not re.search(r, src):
                errs.append("铁律 %d「%s」声明 [库已自动]，但源码里找不到 %r" % (l["id"], l["title"], r))
    if not errs:
        notes.append("rules.json 的 %d 条 [库已自动] 声明均能在源码中找到证明" % len(auto))

    # ---- 4. rules.json 引用的 API 名必须真实存在 ----
    for p in rules.get("paradigms", []):
        for a in p.get("api", []):
            if a not in api:
                errs.append("范式「%s」引用了不存在的 DSL 函数 K.%s" % (p["title"], a))
    for l in rules["laws"]:
        for m in re.findall(r"\bK\.([A-Za-z_][A-Za-z0-9_]*)", l.get("fix", "") + l.get("guard", "")):
            if m not in api and m not in ("B",):
                errs.append("铁律 %d 引用了不存在的 DSL 函数 K.%s" % (l["id"], m))

    # ---- 5. rules.json 与 docs/block_reference.md 的铁律条数必须一致 ----
    ref_path = os.path.join(ROOT, "docs", "block_reference.md")
    if os.path.exists(ref_path):
        ref = open(ref_path, encoding="utf-8").read()
        # 第一节「一、…条编辑器语义铁律」下的编号条目
        sec = ref.split("## 二、")[0]
        ref_ids = set()
        for m in re.finditer(r"^(\d+)\.\s+\*\*", sec, re.M):
            ref_ids.add(int(m.group(1)))
        law_ids = set(l["id"] for l in rules["laws"])
        if ref_ids != law_ids:
            only_ref = sorted(ref_ids - law_ids)
            only_json = sorted(law_ids - ref_ids)
            errs.append("rules.json 与 docs/block_reference.md 的铁律编号不一致")
            if only_ref:
                errs.append("  只在文档里: %s" % only_ref)
            if only_json:
                errs.append("  只在 rules.json 里: %s" % only_json)
        else:
            notes.append("rules.json 与 block_reference.md 铁律编号一致（%d 条）" % len(law_ids))
    else:
        notes.append("（未找到 docs/block_reference.md，跳过铁律编号一致性检查）")

    # ---- 6. 散文里声明的「N 条铁律」必须与 rules.json 实际条数一致 ----
    # 为什么要查：第 5 项只比对「编号集合」（{1..16} 一致就通过），
    # 而散文里还有另一类事实 ——「有 N 条铁律」「共 M 条要自己操心」。
    # 这些是纯文本里的数字，没有任何机制保证它们跟着数据走：
    # 实测 rules.json 是 16 条，block_reference.md 标题却写「十五条」，
    # ask.py 输出里写「15 条铁律」「15+1 条铁律」—— 门禁一路绿灯，agent 读到错数字。
    # 结论：Markdown 适合放结构，不适合放事实。事实只在 rules.json，
    # 散文里出现的计数由本项守住。
    n_total = len(rules["laws"])
    n_auto = sum(1 for l in rules["laws"] if l.get("enforced_by") == "bcm4gen")
    n_manual = sum(1 for l in rules["laws"] if l.get("enforced_by") == "manual")

    # 散文里可能用中文数字（「十六条」），也可能用阿拉伯数字（「16 条」）
    cn_digits = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
                 "六": 6, "七": 7, "八": 8, "九": 9}

    def cn2int(s):
        """数字表达式 → int。支持 1~99 中文数字，也支持「15+1」这种加法写法。
        （曾写过「15+1 条铁律」= 16 条，若只取末段会误报成 1 → 必须整体求和）
        解析不了返回 None。"""
        if not s:
            return None
        if "+" in s:
            total = 0
            for part in s.split("+"):
                v = cn2int(part.strip())
                if v is None:
                    return None
                total += v
            return total
        if s.isdigit():
            return int(s)
        if "十" not in s:
            if len(s) == 1 and s in cn_digits:
                return cn_digits[s]
            return None
        head, _, tail = s.partition("十")
        tens = cn_digits.get(head, 1) if head else 1
        ones = cn_digits.get(tail, 0) if tail else 0
        return tens * 10 + ones

    # 数字表达式：阿拉伯数字可带「+N」；或纯中文数字
    num_re = r"((?:[0-9]+)(?:\s*\+\s*[0-9]+)*|[零一二两三四五六七八九十]+)"
    # 只认「N 条铁律」和「N 条编辑器语义铁律」这种明确指向铁律条数的说法
    claim_pats = [
        (re.compile(num_re + r"\s*条(?:编辑器语义)?铁律"), n_total, "铁律总条数"),
        (re.compile(r"\[需自己写对\][^\n]*?共\s*" + num_re + r"\s*条"), n_manual, "需自己写对的条数"),
    ]
    # 扫哪些文件：所有会被 agent 当事实读的散文
    scan_files = ["AGENTS.md", "README.md", "docs/block_reference.md", "docs/workflow.md"]
    for rel in scan_files:
        p = os.path.join(ROOT, rel)
        if not os.path.exists(p):
            continue
        text = open(p, encoding="utf-8").read()
        for pat, expect, label in claim_pats:
            for m in pat.finditer(text):
                got = cn2int(m.group(1))
                if got is None:
                    continue
                if got != expect:
                    line = text[:m.start()].count("\n") + 1
                    errs.append("%s:%d 声称%s = %d，但 rules.json 实际是 %d（散文数字会漂，必须与真源一致）"
                                % (rel, line, label, got, expect))

    # ask.py 里的输出文本也扫：它直接喂给 agent，数字错了危害最大
    ask_p = os.path.join(HERE, "ask.py")
    if os.path.exists(ask_p):
        text = open(ask_p, encoding="utf-8").read()
        # 排除注释与 docstring 里的历史叙述（那些不是「声明」）
        code = "\n".join(l for l in text.splitlines() if not l.strip().startswith("#"))
        code = re.sub(r'""".*?"""', "", code, flags=re.S)
        for pat, expect, label in claim_pats:
            for m in pat.finditer(code):
                got = cn2int(m.group(1))
                if got is None:
                    continue
                if got != expect:
                    line = text[:m.start()].count("\n") + 1
                    errs.append("tools/ask.py:%d 声称%s = %d，但 rules.json 实际是 %d（输出文本会直接给 agent 读）"
                                % (line, label, got, expect))

    if not errs:
        notes.append("散文里声明的计数与 rules.json 一致（铁律 %d 条：库自动 %d / 需自己写对 %d）"
                     % (n_total, n_auto, n_manual))

    if not quiet:
        for n in notes:
            print("OK: %s" % n)
    if errs:
        print("\n".join("FAIL: " + e for e in errs))
        print("\n%d 项不一致。" % len(errs))
        return 1
    if not quiet:
        print("\nALL PASS: 知识库与实现一致")
    return 0


if __name__ == "__main__":
    sys.exit(main())
