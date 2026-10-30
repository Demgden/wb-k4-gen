#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bcm4_patch.py — 对 kitten4 .bcm4 做"批量替换积木"（不走编辑器，直接改 JSON）。

为什么可以这样改：
  .bcm4 里的积木不是嵌套树，而是两张扁平表：
    blocks{ id: {type, fields, shadows, mutation, parent_id, location, ...} }
    connections{ id: { 目标块id : {type: next|input, input_name, input_type} } }
  blocks 只放"这个积木自己是什么、字段值是多少"；
  connections 只放"谁连着谁、连在哪个槽"。
  所以改字段/换类型/删块，本质是改这两张表，不需要理解整棵树。

用法:
  # 1) 只看不改：列出匹配到的积木（默认行为）
  python bcm4_patch.py work.bcm4 --where actor=计算器 type=math_number field.NUM=0

  # 2) 跑规则文件（默认 dry-run，加 --write 才落盘）
  python bcm4_patch.py work.bcm4 --rules rules.json
  python bcm4_patch.py work.bcm4 --rules rules.json --write

  # 3) 改全局变量初值
  python bcm4_patch.py work.bcm4 --set-var 区块大小=25 --write

规则文件格式（数组，按顺序执行；每条 = 选中一批 + 做一件事）:
  [
    {
      "note": "把碰撞用的 0 改成 1",
      "where": {"actor": "计算器", "func": "遍历", "type": "math_number",
                "field": {"NUM": "0"}},
      "do": {"set_field": {"NUM": "1"}}
    },
    {
      "where": {"actor": "计算器", "type": "lists_get_value"},
      "do": {"set_type": "lists_item"}
    },
    {
      "where": {"actor": "计算器", "type": "调用:删除首项"},
      "do": {"delete": true}
    }
  ]

where 可用键:
  actor   角色/场景名，支持子串匹配（"计算器" 命中 "计算器"）
  type    积木类型（精确）；也可写 "call:函数名" 匹配自定义过程调用
  func    只在某个脚本/函数体内找（函数名，或 "广播:刷新屏幕"）
  field   {字段名: 值}，值为字符串则精确比较，形如 "/正则/" 则正则匹配
  shadow  {字段名: 值}，匹配 shadows 里的字面量
  has     只保留同时满足这些槽有连接的块，如 ["INDEX"]
  limit   只取前 N 个（按画布 y 从上到下），用于"只改一处"

do 可用键（可组合，但 delete 要单独用）:
  set_field   {名: 值} 改 fields，并同步改 shadows 里同名 field（关键：字面量有两份）
  set_shadow  {名: 值} 只改 shadows 里的字面量
  set_type    字符串，换积木类型（新类型槽名必须与旧的一致，否则连接会错位）
  delete      true，删除块并把前后重新接上

安全策略:
  - 默认 dry-run，只打印将要发生的改动
  - --write 时先备份成 <原名>.bak.<时间戳>
  - 落盘前后都做完整性校验（连接指向、parent_id、重复 id），校验失败不写
"""
import argparse
import copy
import json
import re
import shutil
import sys
import time

from bcm4_json import dumps as js_dumps

FIELD_RE = re.compile(r'(<field[^>]*name="%s"[^>]*>)([^<]*)(</field>)')


# ---------------------------------------------------------------- 读写
def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save(path, data, backup=True):
    if backup:
        bak = f"{path}.bak.{time.strftime('%Y%m%d_%H%M%S')}"
        shutil.copy2(path, bak)
        print(f"已备份 → {bak}")
    # 原文件是单行压缩 JSON，且浮点格式按 JS 规则写回（否则会出现 3.47e-06 这类噪声）
    with open(path, "w", encoding="utf-8") as f:
        f.write(js_dumps(data))


# ---------------------------------------------------------------- 实体遍历
def entities(proj):
    th = proj.get("theatre") or {}
    for sid, sc in (th.get("scenes") or {}).items():
        yield sc.get("name") or sid, sc
    for aid, ac in (th.get("actors") or {}).items():
        yield ac.get("name") or aid, ac


def bdj_of(ent):
    b = ent.get("block_data_json") or {}
    return b.get("blocks") or {}, b.get("connections") or {}


# ---------------------------------------------------------------- 结构辅助
def roots(blocks):
    return [b for b in blocks.values() if not b.get("parent_id")]


def script_label(b):
    t = b.get("type")
    if t in ("procedures_2_defnoreturn", "procedures_2_return_value"):
        return (b.get("fields") or {}).get("NAME") or "(无名函数)"
    if t == "self_listen":
        sh = (b.get("shadows") or {}).get("message") or ""
        m = re.search(r'name="MESSAGE"[^>]*>([^<]*)<', sh)
        return "广播:" + (m.group(1) if m else "?")
    if t == "start_as_a_mirror":
        return "克隆启动"
    if t in ("start_on_click", "on_key", "on_keydown", "on_swipe", "start_on_msg"):
        return t
    return t or "?"


def owners(blocks, conns):
    """block_id -> 所属脚本名（从顶层块往下走一遍）"""
    out = {}
    for r in roots(blocks):
        label = script_label(r)
        stack = [r["id"]]
        while stack:
            cur = stack.pop()
            if cur in out or cur not in blocks:
                continue
            out[cur] = label
            for tgt in (conns.get(cur) or {}):
                if tgt in blocks:
                    stack.append(tgt)
    return out


def parents(conns):
    """block_id -> (来源块id, 连接meta)；一个块只应有一个来源"""
    out = {}
    for src, cs in conns.items():
        for tgt, meta in cs.items():
            out.setdefault(tgt, (src, meta))
    return out


# ---------------------------------------------------------------- 匹配
def _eq(actual, want):
    if actual is None:
        return False
    actual = str(actual)
    if want.startswith("/") and want.endswith("/") and len(want) > 2:
        return re.search(want[1:-1], actual) is not None
    return actual == want


def call_name(b):
    f = b.get("fields") or {}
    if "NAME" in f:
        return f["NAME"]
    m = re.search(r'name="NAME">([^<]*)<', (b.get("shadows") or {}).get("NAME") or "")
    return m.group(1) if m else None


def _name_hit(pattern, actual):
    """名字匹配：'=X' 精确，'/re/' 正则，其余子串"""
    actual = actual or ""
    if pattern.startswith("="):
        return actual == pattern[1:]
    if pattern.startswith("/") and pattern.endswith("/") and len(pattern) > 2:
        return re.search(pattern[1:-1], actual) is not None
    return pattern in actual


def _subtree(blocks, conns, bid):
    """bid 的所有后代(含自身)，不下钻 next 下一句"""
    seen, stack = set(), [bid]
    while stack:
        c = stack.pop()
        if c in seen or c not in blocks:
            continue
        seen.add(c)
        for tgt, meta in (conns.get(c) or {}).items():
            if meta.get("type") == "next":
                continue
            stack.append(tgt)
    return seen


def matches(b, where, owner, conns, blocks=None):
    t = b.get("type") or ""
    if "type" in where:
        w = where["type"]
        if w.startswith("call:"):
            if not (t.startswith("procedures_2_call") and call_name(b) == w[5:]):
                return False
        elif t != w:
            return False
    if "func" in where and not _name_hit(where["func"], owner):
        return False
    for k, v in (where.get("field") or {}).items():
        if not _eq((b.get("fields") or {}).get(k), str(v)):
            return False
    for k, v in (where.get("shadow") or {}).items():
        sh = (b.get("shadows") or {}).get(k) or ""
        m = re.search(r'<field[^>]*name="(?:NUM|TEXT|MESSAGE)"[^>]*>([^<]*)<', sh)
        if not m or not _eq(m.group(1), str(v)):
            return False
    for slot in (where.get("has") or []):
        if slot not in (conns.get(b.get("id")) or {}):
            return False
    # ---- 结构条件（需要 blocks 才能判断）----
    if blocks is not None:
        kids = conns.get(b.get("id")) or {}
        if "value_type" in where:
            # 任一「值槽」子块的类型命中（如 variables_set 的值是 text_join）
            ok = False
            for tgt, m in kids.items():
                if m.get("type") == "input" and m.get("input_type") == "value":
                    if _name_hit(where["value_type"], (blocks.get(tgt) or {}).get("type") or ""):
                        ok = True
                        break
            if not ok:
                return False
        if where.get("empty"):
            # 语句体为空（空转的循环）
            if any(m.get("type") == "input" and m.get("input_type") == "statement"
                   for m in kids.values()):
                return False
        if "has_call" in where:
            # 子树里调用了某个自定义过程
            want = where["has_call"]
            hit = False
            for c in _subtree(blocks, conns, b.get("id")):
                cb = blocks.get(c) or {}
                if (cb.get("type") or "").startswith("procedures_2_call") and \
                        _name_hit(want, (cb.get("fields") or {}).get("NAME") or ""):
                    hit = True
                    break
            if not hit:
                return False
    return True


# ---------------------------------------------------------------- 动作
def set_shadow_field(b, name, value):
    """改 shadows 里同名 field 的字面量（shadows 是 XML 字符串）"""
    sh = (b.get("shadows") or {}).get(name)
    if not isinstance(sh, str) or "<field" not in sh:
        return False
    # 该槽可能包着 shadow 块，字段名不一定和槽名相同，逐个 field 试
    def repl(m):
        return m.group(1) + str(value) + m.group(3)

    new = re.sub(r'(<field[^>]*>)([^<]*)(</field>)', repl, sh, count=1)
    if new != sh:
        b["shadows"][name] = new
        return True
    return False


def do_set_field(b, pairs):
    b.setdefault("fields", {})
    for k, v in pairs.items():
        b["fields"][k] = v
        set_shadow_field(b, k, v)


def unlink(blocks, conns, bid):
    """把 bid 从结构里摘掉，前后接上。返回 (ok, 说明)"""
    pmap = parents(conns)
    src, meta = pmap.get(bid, (None, None))
    succ = None
    for tgt, m in (conns.get(bid) or {}).items():
        if m.get("type") == "next":
            succ = tgt
    if src is None:
        # 顶层块：不能靠重接处理，只能整条链保留
        return False, "顶层块（脚本头），拒绝删除"
    for tgt, m in (conns.get(bid) or {}).items():
        if m.get("type") == "input" and m.get("input_type") == "statement":
            return False, "块内含语句体(DO/LOOP)，请先清空再删"
    kind = meta.get("type")
    if kind == "next" or (kind == "input" and meta.get("input_type") == "statement"):
        # 语句块：让 src 直接指向 succ
        del conns[src][bid]
        if succ:
            if kind == "next":
                conns[src][succ] = {"type": "next"}
            else:
                conns[src][succ] = {"type": "input",
                                    "input_type": "statement",
                                    "input_name": meta.get("input_name")}
            blocks[succ]["parent_id"] = src
    elif kind == "input":
        # 表达式块：摘掉后编辑器回落到 shadows 默认值
        del conns[src][bid]
    else:
        return False, f"未知连接类型 {kind}"

    # 连带删除它的表达式子树(只跟 value 输入，不下钻语句体和下一句)
    kill, stack = set(), [bid]
    while stack:
        c = stack.pop()
        if c in kill or c not in blocks:
            continue
        kill.add(c)
        for tgt, m in (conns.get(c) or {}).items():
            if m.get("type") == "next":
                continue
            if m.get("type") == "input" and m.get("input_type") == "statement":
                continue
            stack.append(tgt)
    for c in kill:
        blocks.pop(c, None)
        conns.pop(c, None)
    return True, f"已删除(含 {len(kill) - 1} 个表达式子块)"


# ---------------------------------------------------------------- 校验
def verify(proj):
    errs = []
    for name, ent in entities(proj):
        blocks, conns = bdj_of(ent)
        for src, cs in conns.items():
            if src not in blocks:
                errs.append(f"{name}: 连接来源 {src} 不存在")
            for tgt in cs:
                if tgt not in blocks:
                    errs.append(f"{name}: 连接目标 {tgt} 不存在")
        for bid, b in blocks.items():
            p = b.get("parent_id")
            if p and p not in blocks:
                errs.append(f"{name}: 块 {bid} 的 parent_id 悬空")
    return errs


# ---------------------------------------------------------------- 主流程
def run_rules(proj, rules, write, verbose):
    total = 0
    for ri, rule in enumerate(rules, 1):
        where = rule.get("where") or {}
        act = rule.get("do") or {}
        note = rule.get("note") or ""
        hits = []
        for name, ent in entities(proj):
            if "actor" in where and not _name_hit(where["actor"], name):
                continue
            blocks, conns = bdj_of(ent)
            own = owners(blocks, conns)
            for bid, b in list(blocks.items()):
                if matches(b, where, own.get(bid), conns, blocks):
                    loc = b.get("location") or [0, 0]
                    hits.append((name, ent, bid, loc[1]))
        hits.sort(key=lambda x: x[3])          # 按画布 y 排序，保证可复现
        if "limit" in where:
            hits = hits[: int(where["limit"])]
        hits = [(n, e, i) for n, e, i, _ in hits]
        print(f"\n[{ri}] {note or json.dumps(where, ensure_ascii=False)}")
        print(f"    命中 {len(hits)} 个")
        if verbose:
            for name, ent, bid in hits[:20]:
                blocks, _ = bdj_of(ent)
                b = blocks[bid]
                own = owners(*bdj_of(ent)).get(bid)
                print(f"      · {name} / {own} / {b.get('type')} "
                      f"fields={json.dumps(b.get('fields'), ensure_ascii=False)} "
                      f"shadows={json.dumps(b.get('shadows'), ensure_ascii=False)[:80]}")
            if len(hits) > 20:
                print(f"      ... 其余 {len(hits) - 20} 个省略")
        if not write or not hits:
            continue
        for name, ent, bid in hits:
            blocks, conns = bdj_of(ent)
            b = blocks.get(bid)
            if b is None:
                continue
            if act.get("delete"):
                ok, msg = unlink(blocks, conns, bid)
                if not ok and verbose:
                    print(f"      跳过 {bid}: {msg}")
            else:
                if act.get("set_type"):
                    b["type"] = act["set_type"]
                if act.get("set_shadow"):
                    for k, v in act["set_shadow"].items():
                        set_shadow_field(b, k, v)
                if act.get("set_field"):
                    do_set_field(b, act["set_field"])
            total += 1
    return total


def main():
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("path")
    ap.add_argument("--rules", help="规则 JSON 文件")
    ap.add_argument("--where", nargs="*", default=[], help="临时条件 形如 actor=计算器 type=math_number field.NUM=0")
    ap.add_argument("--do", nargs="*", default=[], help="临时动作 形如 field.NUM=1 / type=xxx / delete=1")
    ap.add_argument("--set-var", nargs="*", default=[], help="改全局变量初值 名=值")
    ap.add_argument("--write", action="store_true", help="真正落盘（默认只预览）")
    ap.add_argument("--no-backup", action="store_true", help="落盘时不生成 .bak 副本")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    proj = load(args.path)
    if "compile_result" in proj:
        print("!! 警告: 含顶层 compile_result，编辑器打开时会忽略 block_data_json 的改动")

    rules = []
    if args.rules:
        with open(args.rules, encoding="utf-8") as f:
            rules = json.load(f)

    # 命令行临时规则
    if args.where or args.do:
        where = {}
        for kv in args.where:
            k, _, v = kv.partition("=")
            if k.startswith("field."):
                where.setdefault("field", {})[k[6:]] = v
            elif k.startswith("shadow."):
                where.setdefault("shadow", {})[k[7:]] = v
            elif k == "has":
                where.setdefault("has", []).append(v)
            else:
                where[k] = v
        act = {}
        for kv in args.do:
            k, _, v = kv.partition("=")
            if k.startswith("field."):
                act.setdefault("set_field", {})[k[6:]] = v
            elif k.startswith("shadow."):
                act.setdefault("set_shadow", {})[k[7:]] = v
            elif k == "type":
                act["set_type"] = v
            elif k == "delete":
                act["delete"] = True
        if not act:
            act = {"delete": True} if "delete=1" in args.do else act
        rules.append({"where": where, "do": act, "note": "命令行规则"})

    before = verify(proj)
    changed = run_rules(proj, rules, args.write, args.verbose)

    # 变量初值
    if args.set_var:
        for kv in args.set_var:
            name, _, val = kv.partition("=")
            hit = False
            for vid, v in (proj.get("variables") or {}).items():
                if v.get("name") == name:
                    old = v.get("value")
                    try:
                        v["value"] = json.loads(val)
                    except json.JSONDecodeError:
                        v["value"] = val
                    print(f"变量[{name}] {old} → {v['value']}")
                    hit = True
            if not hit:
                print(f"!! 找不到变量 {name}")

    after = verify(proj)
    if after and len(after) > len(before):
        print("\n!! 结构校验发现新问题，已放弃写入：")
        for e in after[:10]:
            print("   ", e)
        sys.exit(1)

    print(f"\n共改动 {changed} 个积木 / 变化后校验问题 {len(after)} 条")
    if not args.write:
        print("(dry-run，未写盘。确认无误后加 --write)")
    else:
        save(args.path, proj, backup=not args.no_backup)


if __name__ == "__main__":
    main()
