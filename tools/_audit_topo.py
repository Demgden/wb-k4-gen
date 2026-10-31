# -*- coding: utf-8 -*-
"""检查连接拓扑硬伤：next 重复、一子多父、自连、环。"""
import json, sys, os, collections

path = sys.argv[1]
d = json.load(open(path, encoding="utf-8"))


def check(name, bd):
    blocks, conns = bd["blocks"], bd["connections"]
    probs = []
    multi_parent = collections.Counter()
    for src, m in conns.items():
        nxt = [t for t, c in m.items() if c.get("type") == "next"]
        if len(nxt) > 1:
            probs.append(f"NEXT>1 @{src}({blocks[src]['type']}) -> {len(nxt)}")
        if src in m:
            probs.append(f"SELF-LINK @{src}")
        for t in m:
            multi_parent[t] += 1
    for t, n in multi_parent.items():
        if n > 1:
            probs.append(f"MULTI-PARENT {t}({blocks[t]['type']}) x{n}")
    # cycle: follow next chains
    for start in blocks:
        seen = set()
        cur = start
        while True:
            nxt = [x for x, c in (conns.get(cur) or {}).items() if c.get("type") == "next"]
            if not nxt:
                break
            cur = nxt[0]
            if cur in seen or cur == start:
                probs.append(f"CYCLE from {start}")
                break
            seen.add(cur)
    if probs:
        print(f"[{name}] {len(probs)} problems")
        for p in probs[:6]:
            print("   ", p)
    return len(probs)


total = 0
for s in d["theatre"].get("scenes", {}).values():
    if s.get("block_data_json"):
        total += check("[scene] " + (s.get("name") or ""), s["block_data_json"])
for a in d["theatre"]["actors"].values():
    bd = a.get("block_data_json")
    if bd:
        total += check(a["name"], bd)
print("TOTAL", total)
