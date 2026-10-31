# -*- coding: utf-8 -*-
"""把官方 sb3->kitten4 转换表 (build/9.*.js 里的 var Ye={...}) 切成每个 opcode 一段，存成 JSON。"""
import json, os, re

BUILD = r"C:\Program Files\kitten4-desktop\resources\app\build"
f = [x for x in os.listdir(BUILD) if re.fullmatch(r"9\.[0-9a-f]+\.js", x)][0]
src = open(os.path.join(BUILD, f), encoding="utf-8", errors="replace").read()

i = src.find("var Ye={control_wait")
assert i > 0
j = src.index("{", i)
depth = 0
k = j
while True:
    ch = src[k]
    if ch == "{":
        depth += 1
    elif ch == "}":
        depth -= 1
        if depth == 0:
            break
    k += 1
body = src[j + 1:k]

# 按顶层 "key:function(e){" 切分
out = {}
pos = 0
pat = re.compile(r'([a-z][a-zA-Z_0-9]*):function\(e\)\{')
while True:
    m = pat.search(body, pos)
    if not m:
        break
    start = m.end() - 1  # at '{'
    d = 0
    p = start
    while True:
        if body[p] == "{":
            d += 1
        elif body[p] == "}":
            d -= 1
            if d == 0:
                break
        p += 1
    out[m.group(1)] = body[start:p + 1]
    pos = p + 1

print("opcodes extracted:", len(out))
dst = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_official_sb3_map.json")
json.dump(out, open(dst, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("saved", dst)
for k2 in list(out)[:10]:
    print(" ", k2, out[k2][:200])
