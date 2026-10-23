#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""query_block.py — kitten4 积木特性速查（修复「查询新积木特性耗时」的缺陷）

以前查一个新积木的字段/输入/影子结构，要翻 block_defs.json（XML 字符串）或拿
真实作品反编译；现在一条命令搞定。

数据源（相对本脚本 ../ ）：
  data/block_defs.json    编辑器 define_block_xml 全集 = 字段/输入/影子默认值的权威模板
  data/block_struct.json  329 个积木的结构摘要（output/prev/next/inputs kind）
  全仓 *.bcm4             真实作品 = 用法的 ground truth（--use 模式；扫描
                          reference_works/ envelopes/ examples/ projects/ out/）

用法：
  python query_block.py <关键词>...          模糊搜索（匹配 type 名或定义 XML 内容）
  python query_block.py --type <type>        精确查一个积木：字段/输入/影子默认值
  python query_block.py --use <type>         在真实作品里找用例：各作品出现次数 + 原始 JSON + 字段取值分布
  python query_block.py --list [前缀]        列出全部（或某前缀的）积木类型
  python query_block.py --defs <type>        只看该积木的定义 XML 原文（贴进代码用）

示例：
  python query_block.py round                  # 模糊搜「round」
  python query_block.py --type math_round      # 精确结构
  python query_block.py --use check_key        # 真实作品里 check_key 都怎么用的（含全部 key 码）
  python query_block.py --list math_           # 列出所有数学积木
"""
import glob
import json
import os
import sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
DEFS = os.path.join(ROOT, "data", "block_defs.json")
STRUCT = os.path.join(ROOT, "data", "block_struct.json")

# --use 模式的用例扫描范围：全仓 .bcm4（真实作品 + 信封 + 示例产出 + 你的项目 + out 产物）。
# 只用 reference_works/ 会漏掉绝大多数积木的真实用法（如 check_key 只在示例/项目里出现）。
WORK_DIRS = ("reference_works", "envelopes", "examples", "projects", "out")


def load_defs():
    with open(DEFS, encoding="utf-8") as f:
        return json.load(f)


def load_struct():
    if not os.path.exists(STRUCT):
        return {}
    with open(STRUCT, encoding="utf-8") as f:
        return json.load(f)


def parse_xml(xml_str):
    """把 block_defs 的 XML 片段解析成 {fields, values, statements}。"""
    out = {"fields": {}, "values": {}, "statements": []}
    try:
        root = ET.fromstring("<block>" + xml_str + "</block>")
    except ET.ParseError:
        return out
    for el in root:
        if el.tag == "field":
            out["fields"][el.get("name")] = (el.text or "").strip()
        elif el.tag == "value":
            sh = el.find("shadow")
            if sh is not None:
                fd = {f.get("name"): (f.text or "").strip() for f in sh.findall("field")}
                out["values"][el.get("name")] = {"shadow": sh.get("type"), "fields": fd}
            else:
                out["values"][el.get("name")] = {"shadow": None, "fields": {}}
        elif el.tag == "statement":
            out["statements"].append(el.get("name"))
    return out


def show_type(t, defs, struct, raw=False):
    xml_str = defs.get(t)
    st = struct.get(t, {})
    print("=" * 72)
    print("type: %s" % t)
    if st:
        print("  output=%s prev=%s next=%s" % (
            st.get("output"), st.get("prev"), st.get("next")))
        if st.get("inputs"):
            print("  inputs: " + ", ".join(
                "%s(%s)" % (i["name"], i.get("kind")) for i in st["inputs"]))
    if xml_str is None:
        print("  （block_defs.json 无此类型的影子模板；可能无值输入，或名字拼写不同）")
        print("  近似类型: " + ", ".join(k for k in defs if t.split("_")[0] in k)[:200] or "无")
        return
    if raw:
        print(xml_str)
        return
    p = parse_xml(xml_str)
    if p["fields"]:
        print("  fields:")
        for n, v in p["fields"].items():
            print("    %-22s 默认=%r" % (n, v))
    if p["values"]:
        print("  value inputs（含默认影子）:")
        for n, v in p["values"].items():
            if v["shadow"]:
                print("    %-22s shadow=%s %s" % (n, v["shadow"], v["fields"]))
            else:
                print("    %-22s （无默认影子）" % n)
    if p["statements"]:
        print("  statement inputs: " + ", ".join(p["statements"]))


def iter_work_paths():
    """全仓 .bcm4 路径（去重、排序确定），含 projects/ 与 out/（用户自己的作品是最相关的用例）。"""
    seen = set()
    for d in WORK_DIRS:
        base = os.path.join(ROOT, d)
        if not os.path.isdir(base):
            continue
        for p in sorted(glob.glob(os.path.join(base, "**", "*.bcm4"), recursive=True)):
            if p not in seen:
                seen.add(p)
                yield p


def iter_work_blocks():
    """遍历全仓 .bcm4，yield (相对路径标签, block_dict)。"""
    for path in iter_work_paths():
        name = os.path.relpath(path, ROOT).replace(os.sep, "/")
        try:
            with open(path, encoding="utf-8") as f:
                w = json.load(f)
        except Exception as e:
            print("!! 读取失败 %s: %s" % (name, e), file=sys.stderr)
            continue
        for a in w.get("theatre", {}).get("actors", {}).values():
            for b in a.get("block_data_json", {}).get("blocks", {}).values():
                yield name, b


def use_type(t):
    counts, examples, fieldvals = {}, {}, {}
    for name, b in iter_work_blocks():
        if b.get("type") != t:
            continue
        counts[name] = counts.get(name, 0) + 1
        examples.setdefault(name, b)
        for fn, fv in (b.get("fields") or {}).items():
            fieldvals.setdefault(fn, {}).setdefault(str(fv), 0)
            fieldvals[fn][str(fv)] += 1
    if not counts:
        print("全仓 .bcm4（reference_works/envelopes/examples/projects/out）里没有 %s 的用例。" % t)
        print("（可把更大的真实作品拷进 reference_works/ 再查，或用 --type 看模板）")
        return
    print("type: %s —— 真实作品用例（全仓扫描）" % t)
    for name, c in sorted(counts.items()):
        print("  %-42s × %d" % (name, c))
    for fn, dist in sorted(fieldvals.items()):
        items = sorted(dist.items(), key=lambda kv: -kv[1])
        print("  field %s 取值分布: %s" % (
            fn, ", ".join("%r×%d" % (k, v) for k, v in items[:12])))
    name0 = sorted(examples)[0]
    print("  原始 JSON 样例（来自 %s）:" % name0)
    print("  " + json.dumps(examples[name0], ensure_ascii=False, indent=2).replace("\n", "\n  "))


def fuzzy(words, defs):
    hits = []
    for t, xml_str in defs.items():
        blob = t + " " + (xml_str or "")
        if all(w in blob for w in words):
            hits.append(t)
    return hits


def main():
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        return 1
    defs, struct = load_defs(), load_struct()
    mode = args[0]
    if mode == "--type" and len(args) > 1:
        show_type(args[1], defs, struct)
    elif mode == "--defs" and len(args) > 1:
        show_type(args[1], defs, struct, raw=True)
    elif mode == "--use" and len(args) > 1:
        use_type(args[1])
    elif mode == "--list":
        prefix = args[1] if len(args) > 1 else ""
        ts = sorted(t for t in defs if t.startswith(prefix))
        print("共 %d 个类型（前缀 %r）：" % (len(ts), prefix))
        for i in range(0, len(ts), 4):
            print("  " + "  ".join("%-28s" % t for t in ts[i:i + 4]))
    else:
        words = [a for a in args if not a.startswith("--")]
        hits = fuzzy(words, defs)
        print("关键词 %s → %d 个匹配:" % (words, len(hits)))
        for t in hits[:40]:
            p = parse_xml(defs[t])
            desc = []
            if p["fields"]:
                desc.append("fields: " + ",".join("%s=%r" % kv for kv in list(p["fields"].items())[:4]))
            if p["values"]:
                desc.append("inputs: " + ",".join(p["values"]))
            if struct.get(t, {}).get("output"):
                desc.append("[reporter]")
            print("  %-30s %s" % (t, " | ".join(desc)))
        if len(hits) > 40:
            print("  … 其余 %d 个，加 --list 或更精确关键词" % (len(hits) - 40))
    return 0


if __name__ == "__main__":
    sys.exit(main())
