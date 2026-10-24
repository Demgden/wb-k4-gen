#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify_dsl.py — 「知识库与实现一致性」门禁。

ask.py / rules.json / dsl_api.json 是给 agent 查的知识库。知识库一旦与实现漂移，
agent 就会照着过期信息写出坏代码 —— 而且比没查还糟（它以为自己查过了）。
所以知识库必须像生成产物一样被门禁守住。

本工具检查 4 件事：
  1. dsl_api.json 与 tools/bcm4gen.js 同步（源码改了、索引没改 → 报错）
  2. dsl_api.json 里每个 editor_type 都在编辑器注册表内（抓 Scratch 名混用，如 math_mod）
  3. rules.json 每条「[库已自动]」声明的 proof 正则都能在 bcm4gen.js 匹配到
     （防止知识库宣称「库已帮你处理」而实际没处理 —— agent 会因此跳过防御）
  4. rules.json 里引用的 API 名在 dsl_api.json 中都真实存在

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
