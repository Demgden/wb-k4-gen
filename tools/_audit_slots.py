# -*- coding: utf-8 -*-
"""模拟 k4 的 json_to_workspace_headless：每个连接的目标槽必须在父块定义里存在。
槽名不存在 → 编辑器里 console.error("Connected connection not found")，值/子块被丢弃。"""
import json, sys, os, collections

HERE = os.path.dirname(os.path.abspath(__file__))
STRUCT = json.load(open(os.path.join(HERE, "..", "data", "block_struct.json"), encoding="utf-8"))
path = sys.argv[1]
d = json.load(open(path, encoding="utf-8"))

# 动态槽：controls_if 的 IF1/DO1…、自定义积木的 PARAMS*/ARG*、文本拼接 ADD*
def dyn(type_, name):
    if type_.startswith("procedures_2_"):
        return name.startswith(("PARAMS", "ARG"))
    if type_ in ("text_join", "text_split"):
        return name.startswith(("ADD", "TEXT", "ITEM"))
    if type_.startswith("controls_if"):
        return name.startswith(("IF", "DO", "ELSE"))
    return False


bad = collections.Counter()
detail = []
unknown_type = collections.Counter()
for a in list(d["theatre"]["actors"].values()):
    bd = a["block_data_json"]
    blocks, conns = bd["blocks"], bd["connections"]
    for src, m in conns.items():
        p = blocks[src]
        st = STRUCT.get(p["type"])
        if st is None:
            unknown_type[p["type"]] += 1
            continue
        names = {i["name"] for i in st["inputs"]}
        for cid, meta in m.items():
            name = meta.get("input_name")
            if name is None:
                continue
            if name in names or dyn(p["type"], name):
                continue
            key = f'{p["type"]}.{name}'
            bad[key] += 1
            if len(detail) < 12:
                detail.append(f'{a["name"]}: {p["type"]} 没有输入槽 {name}（连了 {blocks[cid]["type"]}）')
print("未收录结构的类型:", dict(unknown_type))
print(f"槽名错误 {sum(bad.values())} 处")
for k, v in bad.most_common(20):
    print(f"  {v:4d} {k}")
for x in detail:
    print("  e.g.", x)
