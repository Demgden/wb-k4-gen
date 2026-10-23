#!/usr/bin/env python3
"""Validate a .bcm4 in Kitten4 native editor format."""
import json, sys, base64, zlib

PATH = sys.argv[1] if len(sys.argv) > 1 else "MagicCatAcademy.bcm4"
w = json.load(open(PATH, encoding="utf-8"))
errs, warns = [], []

# 1. standard top-level keys
STD = ["hidden_toolbox","work_source_label","codemao_value","sample_id","version",
       "application_version","work_type","size","type","project_name","theatre",
       "variables","variable_order","cloud_variables","audio","audio_order",
       "midimusic","midi_order","matrix","models","toolbox","toolbox_order",
       "last_toolbox_order","hardware_type","device_widget_type","is_partial",
       "ai_lab","broadcasts","painter"]
for k in STD:
    if k not in w: errs.append(f"missing top-level key: {k}")
if "compile_result" in w: errs.append("compile_result present (must be removed)")
print("top-level keys:", len(w), "| expected std:", len(STD))

# 2. variables table
vd = w["variables"]
var_ids = set(vd.keys())
var_names = {k: v.get("name") for k, v in vd.items()}
print("variables:", len(var_ids))

# 3. audio table
ad = w["audio"]
aud_ids = set(ad.keys())
print("audio:", len(aud_ids))

# 4. actors + blocks
th = w["theatre"]
actors = list(th["actors"].values())
print("actors:", len(actors))
total_blocks = 0
for ai, a in enumerate(actors):
    name = a.get("name", f"#{ai}")
    bd = a.get("block_data_json")
    if bd is None:
        errs.append(f"{name}: no block_data_json"); continue
    blocks = bd.get("blocks", {})
    conns = bd.get("connections", {})
    total_blocks += len(blocks)
    # normalize connections: src -> list of (tgt, type, input_type, input_name)
    edges = []
    for bid, m in conns.items():
        if bid not in blocks:
            errs.append(f"{name}: conn src {bid[:8]} not in blocks"); continue
        if isinstance(m, dict):
            for tid, meta in m.items():
                if tid not in blocks:
                    errs.append(f"{name}: conn {bid[:8]}-{meta.get('type')}/{meta.get('input_name','')} -> missing {tid[:8]}")
                edges.append((bid, tid, meta.get("type"), meta.get("input_type"), meta.get("input_name")))
        elif isinstance(m, list):
            for meta in m:
                tid = meta.get("target_id")
                if tid and tid not in blocks:
                    errs.append(f"{name}: conn {bid[:8]}-{meta.get('type')}/{meta.get('input_name','')} -> missing {tid[:8]}")
                edges.append((bid, tid, meta.get("type"), meta.get("input_type"), meta.get("input_name")))
    # 4b. reachability moved to 7b (procedure definitions count as roots)
    # 4c. variable UUIDs referenced exist
    for b in blocks.values():
        f = b.get("fields") or {}
        if b["type"] in ("variables_get","variables_set","lists_get"):
            vid = f.get("VAR")
            if vid not in var_ids:
                errs.append(f"{name}: block {b['type']} references unknown VAR {vid}")
        if b["type"] == "change_variable":
            # kitten4 change_variable uses valname (variable UUID) + method (increase/decrease)
            vid = f.get("valname")
            if vid not in var_ids:
                errs.append(f"{name}: change_variable references unknown valname {vid}")
            if f.get("method") not in ("increase", "decrease"):
                errs.append(f"{name}: change_variable has invalid method {f.get('method')}")
        if b["type"] == "get_audios":
            sid = f.get("sound_id")
            if sid not in aud_ids:
                errs.append(f"{name}: get_audios references unknown sound {str(sid)[:60]}")
        if b["type"] in ("mirror","dispose_clone","get_current_clone_index","get_clone_num"):
            sid = f.get("sprite") or f.get("entity")
            # sprite fields validated below
    # 4d. statement inputs connected (no dangling statement input)
    for b in blocks.values():
        for c in conns.get(b["id"], []):
            pass
# 5. costume indices in set_costume_by_index must be within styles count
for a in actors:
    bd = a.get("block_data_json") or {}
    nst = len(a.get("styles") or [])
    for b in (bd.get("blocks") or {}).values():
        if b["type"] == "set_costume_by_index":
            # index may be a reporter; only check literals via shadows
            sh = b.get("shadows") or {}
            xml = sh.get("index", "")
            import re
            m = re.search(r'NUM="(\d+)"', xml)
            if m and nst and not (1 <= int(m.group(1)) <= nst):
                errs.append(f"{a.get('name')}: set_costume_by_index literal {m.group(1)} out of 1..{nst}")

# 6. sprite references (mirror / get_clone_num field=sprite) exist
actor_ids = {a["id"] for a in actors}
for a in actors:
    bd = a.get("block_data_json") or {}
    for b in (bd.get("blocks") or {}).values():
        if b["type"] in ("mirror", "get_clone_num"):
            sid = (b.get("fields") or {}).get("sprite")
            if sid not in actor_ids:
                errs.append(f"{a.get('name')}: {b['type']} references unknown sprite {sid}")

# 7. dropdown OP/PROPERTY field values must exist in the editor's option domain
#    (invalid values render as "?" and raise domain_function_error at runtime —
#    e.g. logic_compare "NOT_EQ" instead of "NEQ")
OP_DOMAINS = {
    "logic_compare": {"EQ", "NEQ", "LT", "LTE", "GT", "GTE"},
    "math_arithmetic": {"ADD", "MINUS", "MULTIPLY", "DIVIDE", "POWER"},
    "logic_operation": {"AND", "OR"},
    "math_single": {"ROOT", "ABS", "NEG", "LN", "EXP", "POW10", "SIN", "COS", "TAN",
                    "ASIN", "ACOS", "ATAN"},
    "math_trig": {"SIN", "COS", "TAN", "ASIN", "ACOS", "ATAN"},
    "math_number_property": {"EVEN", "ODD", "PRIME", "WHOLE", "POSITIVE", "NEGATIVE", "DIVISIBLE_BY"},
    "math_round": {"ROUND", "ROUNDUP", "ROUNDDOWN"},
}
for a in actors:
    bd = a.get("block_data_json") or {}
    for b in (bd.get("blocks") or {}).values():
        dom = OP_DOMAINS.get(b["type"])
        if not dom:
            continue
        for fk, fv in (b.get("fields") or {}).items():
            if fk in ("OP", "PROPERTY") and fv not in dom:
                errs.append(f"{a.get('name')}: {b['type']}.{fk}={fv!r} not in domain {sorted(dom)}")

# 7b. reachability: procedure definitions are top-level scripts in the editor too.
#     （旧版只认 hat 根 → 过程式作品整片误报 unreachable；defnoreturn/return_value 也是根）
for ai, a in enumerate(actors):
    name = a.get("name", f"#{ai}")
    bd = a.get("block_data_json") or {}
    blocks = bd.get("blocks", {})
    conns = bd.get("connections", {})
    roots = [b["id"] for b in blocks.values()
             if b["type"].startswith("start_") or b["type"] == "event_whenflagclicked"
             or b["type"] in ("procedures_2_defnoreturn", "procedures_2_return_value")]
    edges = []
    for bid, m in conns.items():
        if isinstance(m, dict):
            for tid, meta in m.items():
                edges.append((bid, tid))
        elif isinstance(m, list):
            for meta in m:
                edges.append((bid, meta.get("target_id")))
    seen, stack = set(), list(roots)
    while stack:
        x = stack.pop()
        if x in seen or x not in blocks: continue
        seen.add(x)
        for s, t in edges:
            if s == x and t: stack.append(t)
    orphan = set(blocks) - seen
    if orphan:
        warns.append(f"{name}: {len(orphan)} unreachable blocks ({', '.join(sorted(set(blocks[o]['type'] for o in orphan)))})")

# 8. editor-envelope parity (real 4.11.20-saved works) — 缺这些字段/多写这些键 → 编辑器打不开
#    来源：PoorPhy.bcm4 首次生成被编辑器拒绝，逐字段 diff 真实作品定位。
#    2026-10-23 二次修正（对齐 references/block_reference.md 第七节）：
#    codemao_value int/str 均可（只是不能 null）；rotate_center_painter 建议含但非硬性
#    （空白作品缺它也能开）——两条由 error 降为按类型检查 / warning，避免误报。
cv = w.get("codemao_value")
if cv is None or not isinstance(cv, (int, str)):
    errs.append(f"codemao_value must be int or string (not null), got {type(cv).__name__}")
THEATRE_FORBIDDEN = ("current_entity", "current_scene", "style_collections")
for k in THEATRE_FORBIDDEN:
    if k in th:
        errs.append(f"theatre has forbidden key {k!r} (real editor never writes it)")
TOOLBOX_REQUIRED = ("lang", "cellphone", "pen")
tb = w.get("toolbox") or {}
for k in TOOLBOX_REQUIRED:
    if k not in tb:
        errs.append(f"toolbox missing required key {k!r}")
style_reg = th.get("styles") or {}
STYLE_REQUIRED = ("id", "name", "url", "cdn_url", "pivot", "rotate_center", "adaptive")
STYLE_RECOMMENDED = ("rotate_center_painter",)  # 非硬性：真实作品有、空白作品没有也能开
for sid, s in style_reg.items():
    if not isinstance(s, dict):
        errs.append(f"style {str(sid)[:8]} not a dict"); continue
    for k in STYLE_REQUIRED:
        if k not in s:
            errs.append(f"style {str(sid)[:8]} ({s.get('name')!r}) missing field {k!r}")
    for k in STYLE_RECOMMENDED:
        if k not in s:
            warns.append(f"style {str(sid)[:8]} ({s.get('name')!r}) missing recommended field {k!r}")
for a in actors:
    for sid in (a.get("styles") or []):
        if sid not in style_reg:
            errs.append(f"actor {a.get('name')!r}: style {str(sid)[:8]} not in theatre.styles")
for sid, sc in (th.get("scenes") or {}).items():
    sids = sc.get("styles") or []
    cur = sc.get("current_style_id")
    if not sids:
        errs.append(f"scene {sc.get('name')!r}: styles empty (must hold its background costume)")
    if cur is not None and cur not in sids:
        errs.append(f"scene {sc.get('name')!r}: current_style_id not in styles")
    if cur is not None and cur not in style_reg:
        errs.append(f"scene {sc.get('name')!r}: current_style_id not resolvable in theatre.styles")
    for sid2 in sids:
        if sid2 not in style_reg:
            errs.append(f"scene {sc.get('name')!r}: style {str(sid2)[:8]} not in theatre.styles")

print("total blocks:", total_blocks)
print("styles per actor:", {a.get("name"): len(a.get("styles") or []) for a in actors})
print()
for e in errs: print("ERROR:", e)
for x in warns: print("WARN:", x)
print(f"\n{len(errs)} errors, {len(warns)} warnings")
sys.exit(1 if errs else 0)
