#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify_procedures.py —— 复刻 kitten4 编辑器「加载 bcm4 时对过程块(processures_2)的硬断言」，
在打开文件之前就判定该文件会不会让编辑器崩溃。

来源：kitten4 编辑器真实 bundle（kitten.js）里的两个 loader：
  1) JSON loader  (模块 FlGc)  load_from_json  ← .bcm4 的 block_data_json 走这条路
  2) XML  loader  (模块 VCTP)  load_from_xml
以及 ProcedureManager (模块 n/Yo) 的 load_def_from_block。

编辑器里的原始断言（逐条照抄语义）：
  A. DEF 块 fields.NAME 必须存在且非空          assert(name)
  B. DEF 块每个 PARAMS<n> 输入连上的块：
       - 必须存在                                assert(t)
       - type 必须 === "procedures_2_stable_parameter"   assert(t.type === PARAM_ON_BLOCK)
         ★ 这是历史上最致命的坑：写成 procedures_2_parameter 会让整个文件打不开
       - 字段 param_name 必须存在且非空           assert(param_name)
       - 字段 param_default_value 建议存在（缺失只导致默认值为 undefined，不致命）
  C. CALL 块 fields.NAME 必须存在且非空
  D. CALL 块 mutation 里每个 <procedures_2_parameter_shadow name="X"></...>
       必须恰好含 1 个 name="..." （编辑器 assert(t && 2===t.length)）
  E. CALL 块 mutation 的 def_id 必须能指向真实 DEF 块（编辑器 get_procedure_by_def 找不到时
     会退化成按 XML 子节点数建 ARG 输入 → 输入数与 connections 不符 → 连接失败崩溃）

用法：
  python verify_procedures.py <file.bcm4> [...]
退出码 0 = 全部通过；1 = 有致命问题。
"""
import json
import re
import sys

DEF = "procedures_2_defnoreturn"
RETURN = "procedures_2_return_value"
CALL_NORETURN = "procedures_2_callnoreturn"
CALL_RETURN = "procedures_2_callreturn"
PARAM_ON_BLOCK = "procedures_2_stable_parameter"   # ★ 定义块 PARAMS 槽上的参数块
PARAM = "procedures_2_parameter"                   # 函数体内引用参数
PARAM_PREFIX = "PARAMS"
ARG_PREFIX = "ARG"
FIELD_NAME = "NAME"
FIELD_PARAM_NAME = "param_name"
FIELD_PARAM_DEFAULT = "param_default_value"

SHADOW_RE = re.compile(r'<procedures_2_parameter_shadow[^>]+></procedures_2_parameter_shadow>')
NAME_ATTR_RE = re.compile(r' name="([^"]+)"')


def check_file(path):
    """返回 (errors, warnings)"""
    errors, warnings = [], []
    with open(path, encoding="utf-8") as f:
        doc = json.load(f)

    theatre = doc.get("theatre") or {}
    entities = []
    for kind in ("actors", "scenes"):
        for eid, ent in (theatre.get(kind) or {}).items():
            bdj = ent.get("block_data_json")
            if bdj and bdj.get("blocks"):
                entities.append((f"{kind[:-1]}:{ent.get('name', eid)}", bdj["blocks"], bdj.get("connections") or {}))

    if not entities:
        return errors, warnings

    # def_id 是「全局」的：函数可以定义在 A 角色、被 B 角色调用（真实作品 球体物理 就是这样）。
    # 因此要收集全文件所有 DEF 块的 id。
    global_def_ids = set()
    for _label, blocks, _conns in entities:
        for bid, b in blocks.items():
            if b.get("type") == DEF:
                global_def_ids.add(bid)

    for label, blocks, conns in entities:
        # ── B. DEF 的 PARAMS 槽 ─────────────────────────────────────────
        def_ids = {}
        for bid, b in blocks.items():
            if b.get("type") != DEF:
                continue
            name = (b.get("fields") or {}).get(FIELD_NAME)
            if not name:
                errors.append(f"[{label}] {bid}: DEF 块缺少 fields.NAME（编辑器 assert 会抛错）")
                continue
            def_ids[bid] = name

            # 找出该 def 上所有 PARAMS<n> 输入，并按 n 排序（编辑器就是这么排的）
            params = []
            for tgt, info in (conns.get(bid) or {}).items():
                if info.get("type") != "input":
                    continue
                iname = str(info.get("input_name") or "")
                if not iname.startswith(PARAM_PREFIX):
                    continue
                try:
                    idx = int(iname[len(PARAM_PREFIX):])
                except ValueError:
                    errors.append(f"[{label}] {bid}: PARAMS 输入名非法 {iname!r}")
                    continue
                params.append((idx, iname, tgt))
            params.sort()

            for idx, iname, tgt in params:
                tb = blocks.get(tgt)
                if tb is None:
                    errors.append(
                        f"[{label}] {bid}({name}): {iname} 连上的块不存在（id={tgt}）")
                    continue
                if tb.get("type") != PARAM_ON_BLOCK:
                    errors.append(
                        f"[{label}] {bid}({name}): {iname} 必须是 {PARAM_ON_BLOCK}，"
                        f"实际是 {tb.get('type')}  ← ★致命：编辑器 assert 会抛错，整个文件打不开")
                pname = (tb.get("fields") or {}).get(FIELD_PARAM_NAME)
                if not pname:
                    errors.append(
                        f"[{label}] {bid}({name}): {iname} 上的参数块缺少字段 {FIELD_PARAM_NAME}（编辑器 assert 会抛错）")
                if FIELD_PARAM_DEFAULT not in (tb.get("fields") or {}):
                    warnings.append(
                        f"[{label}] {bid}({name}): {iname} 参数块缺 {FIELD_PARAM_DEFAULT}（不致命，但与真实作品不符）")

        # ── C/D/E. CALL 块 ────────────────────────────────────────────
        for bid, b in blocks.items():
            if b.get("type") not in (CALL_NORETURN, CALL_RETURN):
                continue
            cname = (b.get("fields") or {}).get(FIELD_NAME)
            if not cname:
                errors.append(f"[{label}] {bid}: CALL 块缺少 fields.NAME（编辑器 assert 会抛错）")
            mut = b.get("mutation") or ""
            for el in SHADOW_RE.findall(mut):
                hits = NAME_ATTR_RE.findall(el)
                if len(hits) != 1:
                    errors.append(
                        f"[{label}] {bid}({cname}): mutation 里的 procedures_2_parameter_shadow "
                        f"含 {len(hits)} 个 name 属性（编辑器要求恰好 1 个）→ {el[:120]}")
            m = re.search(r'def_id="([^"]*)"', mut)
            if m and m.group(1) and m.group(1) not in global_def_ids:
                # 编辑器在 def_id 找不到时会回退到「按函数名查找」(get_procedure_by_name)，
                # 所以这不致命（真实作品 球体物理 里就有调用未定义函数的写法），只提示。
                warnings.append(
                    f"[{label}] {bid}({cname}): mutation 的 def_id={m.group(1)} 在本文件里找不到对应定义块"
                    f"（编辑器会回退到按名字查找，不致命）")

        # ── 额外体检：PARAMS 槽被 procedures_2_parameter 占用（历史坑的直观提示）──
        for bid, b in blocks.items():
            if b.get("type") != DEF:
                continue
            for tgt, info in (conns.get(bid) or {}).items():
                if info.get("type") != "input":
                    continue
                if not str(info.get("input_name") or "").startswith(PARAM_PREFIX):
                    continue
                tb = blocks.get(tgt) or {}
                if tb.get("type") == PARAM:
                    errors.append(
                        f"[{label}] {bid}: PARAMS 槽上用了 {PARAM}（应为 {PARAM_ON_BLOCK}）")
    return errors, warnings


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    rc = 0
    for path in argv[1:]:
        try:
            errors, warnings = check_file(path)
        except Exception as e:  # noqa: BLE001
            print(f"✗ {path}: 读取失败 {e}")
            rc = 1
            continue
        name = path.replace("\\", "/").split("/")[-1]
        if errors:
            rc = 1
            print(f"✗ {name}: {len(errors)} 个致命问题")
            for e in errors[:30]:
                print("    -", e)
            if len(errors) > 30:
                print(f"    ... 其余 {len(errors)-30} 条省略")
        else:
            print(f"✓ {name}: 过程块契约全部通过（编辑器加载断言不会抛错）")
        for w in warnings[:10]:
            print("    ⚠", w)
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv))
