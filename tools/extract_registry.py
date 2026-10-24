#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""extract_registry.py — 从 kitten.js（编辑器 bundle）抽取全部已注册积木类型。

注册模式：NAME={type:"NAME",...}（block 定义对象）
补充来源：工具箱 flyout 的 blocks:[...] 列表
输出：data/editor_block_types.json（sorted list）

用法：
  python extract_registry.py [kitten.js 路径]        # 抽取并写出 data/editor_block_types.json
  python extract_registry.py --check [kitten.js 路径] # 只校验：现有注册表是否仍与 bundle 一致
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CHECK = "--check" in sys.argv
argv = [a for a in sys.argv[1:] if a != "--check"]
CANDIDATES = [
    argv[0] if argv else "",
    os.path.join(HERE, "kitten.js"),
    os.path.join(HERE, "..", "..", "..", "..", "K4xAI", "tools", "kitten.js"),
    os.path.expanduser("~/Desktop/kitten4作品/tools/kitten.js"),
]
SRC = next((p for p in CANDIDATES if p and os.path.exists(p)), "")
OUT = os.path.join(HERE, "..", "data", "editor_block_types.json")
if not SRC:
    if CHECK:
        # 没有 bundle 可比对：只要注册表文件本身在、能解析，就算通过（不阻塞门禁）
        if os.path.exists(OUT):
            try:
                n = len(json.load(open(OUT, encoding="utf-8")))
                print("未找到 kitten.js，跳过比对（沿用现有注册表 %d 个类型）" % n)
                sys.exit(0)
            except Exception as e:
                print("FAIL: 现有注册表无法解析: %s" % e)
                sys.exit(1)
        print("FAIL: 找不到 kitten.js 且无 data/editor_block_types.json")
        sys.exit(1)
    print("找不到 kitten.js；请把编辑器 bundle 放到 tools/ 或传路径参数")
    sys.exit(1)

s = open(SRC, encoding="utf-8", errors="ignore").read()
# 注册源 1：程序化定义 NAME={type:"NAME",...}
reg = set(re.findall(r'([a-z_][a-z_0-9]*)=\{type:"\1"', s))
# 注册源 2：XML 定义 define_block_xml("NAME", ...)（block_defs.json 即此源的转储）
xml_def = set(re.findall(r'define_block_xml\("([a-z_][a-z_0-9]*)"', s))
# 注册源 3：工具箱 flyout 的 blocks:[...] 列表
fly = set()
for m in re.finditer(r'blocks:\[((?:"[a-z_0-9]+",?)*)\]', s):
    fly.update(x.strip('"') for x in m.group(1).split(",") if x.strip('"'))
# 注册源 4：代码生成器 e.register("NAME", function...)（math_number/default_value 等积木走这条）
gen = set(re.findall(r'\.register\("([a-z_][a-z_0-9]*)"', s))
# 注册源 5：XML 字符串里的 <block type="NAME"> / <shadow type="NAME">
#   （procedures_2_stable_parameter 等只在 mutation XML 里被引用）
xml_ref = set(re.findall(r'type="([a-z_][a-z_0-9]*)"', s))
# 注册源 6：TS 枚举 e[e.NAME=7]="NAME"（procedures_2_callnoreturn 等走这条）
enum = set(re.findall(r'([a-z_][a-z_0-9]*)=\d+\]="\1"', s))
# 注册源 7：逗号分隔的引号列表（>=3 个连续小写标识符，如积木名单/块类型清单）
quoted = set()
for m in re.finditer(r'"[a-z_][a-z_0-9]*"(?:\s*,\s*"[a-z_][a-z_0-9]*"){2,}', s):
    quoted.update(re.findall(r'"([a-z_][a-z_0-9]*)"', m.group(0)))

allt = sorted(reg | xml_def | fly | gen | xml_ref | enum | quoted)

if CHECK:
    if not os.path.exists(OUT):
        print("FAIL: data/editor_block_types.json 不存在")
        sys.exit(1)
    old = json.load(open(OUT, encoding="utf-8"))
    if old == allt:
        print("OK: editor_block_types.json 与 bundle 同步（%d 个类型）" % len(allt))
        sys.exit(0)
    gone = sorted(set(old) - set(allt))
    new = sorted(set(allt) - set(old))
    print("FAIL: editor_block_types.json 已过期 —— 请重跑 python extract_registry.py")
    if gone:
        print("  消失的类型: %s" % ", ".join(gone[:20]))
    if new:
        print("  新增的类型: %s" % ", ".join(new[:20]))
    sys.exit(1)

with open(OUT, "w", encoding="utf-8") as f:
    json.dump(allt, f, ensure_ascii=False, indent=0)
    f.write("\n")
print("源: %s (%.1f MB)" % (SRC, os.path.getsize(SRC) / 1048576))
print("程序化 %d + XML定义 %d + flyout %d + 生成器 %d + XML引用 %d + 枚举 %d + 引号列表 %d -> 并集 %d 个类型" % (
    len(reg), len(xml_def), len(fly), len(gen), len(xml_ref), len(enum), len(quoted), len(allt)))
print("写出: %s" % OUT)
