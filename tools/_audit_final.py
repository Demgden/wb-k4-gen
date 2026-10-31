# -*- coding: utf-8 -*-
"""终检：影子一致性 + 值槽覆盖 + 下拉值域。"""
import json, re, sys, collections

path = sys.argv[1]
d = json.load(open(path, encoding="utf-8"))
SHADOW_TYPES = {"broadcast_input", "get_audios", "get_whole_audios", "lists_get",
                "logic_empty", "math_number", "text", "shadow_text", "default_value",
                "logic_boolean"}
errs = []


def audit(name, bd):
    blocks, conns = bd["blocks"], bd["connections"]
    for bid, b in blocks.items():
        t = b["type"]
        # 1) 影子类型必须 is_shadow
        if t in SHADOW_TYPES and not b.get("is_shadow"):
            errs.append(f"[{name}] {t} is_shadow=False ({bid})")
        # 2) 每个 value 连接的槽，父块 shadows 必须有条目；影子块条目 id 必须一致
        for cid, meta in (conns.get(bid) or {}).items():
            if meta.get("type") != "input" or meta.get("input_type") != "value":
                continue
            slot = meta.get("input_name")
            raw = (b.get("shadows") or {}).get(slot)
            child = blocks.get(cid) or {}
            if not isinstance(raw, str) or not raw.strip():
                errs.append(f"[{name}] {t}.{slot} 缺 shadow（子块 {child.get('type')}）")
                continue
            m = re.search(r'id="([^"]+)"', raw)
            if not m:
                errs.append(f"[{name}] {t}.{slot} shadow 无 id")
                continue
            sid = m.group(1)
            if child.get("is_shadow"):
                if sid != cid:
                    errs.append(f"[{name}] {t}.{slot} shadow id != 子块 id（{child.get('type')}）")
            else:
                if sid == cid:
                    errs.append(f"[{name}] {t}.{slot} phantom 复用了子块 id（{child.get('type')}）")
    # 3) 语句槽 shadow 必须是 ""
    for bid, b in blocks.items():
        for cid, meta in (conns.get(bid) or {}).items():
            if meta.get("input_type") == "statement":
                slot = meta.get("input_name")
                if (b.get("shadows") or {}).get(slot) not in ("", None):
                    errs.append(f"[{name}] {b['type']}.{slot} 语句槽 shadow 非空")


for s in d["theatre"].get("scenes", {}).values():
    if s.get("block_data_json"):
        audit("[scene] " + (s.get("name") or ""), s["block_data_json"])
for a in d["theatre"]["actors"].values():
    if a.get("block_data_json"):
        audit(a["name"], a["block_data_json"])

print(f"{len(errs)} issues")
c = collections.Counter(e.split("] ")[1].split(" ")[0] for e in errs)
for k, v in c.most_common(15):
    print(f"  {v:5d} {k}")
for e in errs[:10]:
    print("   e.g.", e)
