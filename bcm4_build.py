#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bcm4_build.py — 从积木定义「从零构造」新积木，插入到现有 .bcm4。

这是 bcm4_patch.py 的补充：
  bcm4_patch.py  只会「改」和「删」已有的块；
  bcm4_build.py  负责「无中生有」——按规格造一个原项目里没有的块，接到指定位置。

数据来源（相对本脚本 ../data/）：
  block_struct.json  329 个积木的结构：output/prev/next + 每个输入的 kind
                     kind 决定这个输入是『字段』(field_*)、『值槽』(value) 还是『语句体』(statement)
  block_defs.json    133 个积木的 define_block_xml：每个值槽的默认 shadow 模板
                     缺失的（多是叶子块）用项目内同类实例兜底，再不行留空

四条必须遵守的规则（踩过坑才有）：
  1. type 必须已注册（在 block_struct 里）。未注册的 type 会让编辑器建块抛异常，
     ≥1000 块时异常被异步加载吞掉，表现为「积木栏消失 / 工作区空白」。
  2. 每个块都必须有 connections 条目，哪怕内容为空 {}。漏了会让整块积木区加载失败。
  3. 值槽即使被真实块占着，也要保留一份默认 shadow（phantom id，独立于占据者），
     否则用户以后在编辑器里改那个输入就会坏——当时不报错，属于延迟爆炸。
  4. 语句槽的 shadows 必须写成 ""。

用法:
  # 看有哪些脚本/函数，以及每条语句的执行序号（插入位置靠它定位）
  python bcm4_build.py work.bcm4 list
  python bcm4_build.py work.bcm4 show --actor 计算器 --func 遍历 --limit 15

  # 按「函数 + 第几条顶层语句」定位（--index 0 是函数体开头，-1 也是开头）
  python bcm4_build.py work.bcm4 insert --func 遍历 --index 0 --pos before --block spec.json

  # 按 show 里打印的全局编号 [N] 定位：能插到 if / 循环体内部（--index 只能到顶层）
  python bcm4_build.py work.bcm4 insert --actor 计算器 --at 803 --pos before --block spec.json
  python bcm4_build.py work.bcm4 insert --actor 计算器 --at 803 --pos before --block spec.json --write

注意 show / insert 的编号口径一致：都是「该角色内所有脚本的执行顺序」，
与 --func 过滤无关，所以同一个 [N] 在两处指的永远是同一块。

--block 可以是单块 {...}，也可以是 [{...}, {...}] 多块（按顺序串成一条链）。

积木规格 JSON（就是积木树，写法贴近编辑器）:
  {
    "type": "controls_if",
    "body": {"DO0": [
      {"type": "stop", "fields": {}}
    ]},
    "inputs": {
      "IF0": {"type": "logic_compare", "fields": {"OP": "GT"},
              "inputs": {"A": {"type": "variables_get", "fields": {"VAR": "血量"}},
                         "B": 0}}
    }
  }

  - inputs 里写数字/字符串会自建成 math_number / text 影子块
  - inputs 里写对象就是真实子块
  - fields 里的 VAR / valname 可以直接写变量『名字』，会自动换成 uuid
  - body 里是语句链数组，按顺序自动串 next
"""
import argparse
import json
import os
import random
import re
import string
import sys
import time

from bcm4_json import dumps as js_dumps

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
STRUCT_PATH = os.path.join(ROOT, "data", "block_struct.json")
DEFS_PATH = os.path.join(ROOT, "data", "block_defs.json")

ALPHABET = string.ascii_letters + string.digits
XMLNS = 'xmlns="http://www.w3.org/1999/xhtml"'

# 包装块的占位符：取值写 "$" 的槽表示「被包住的原块接到这里」
HOLDER = "$"

# 这些字段名存的是变量 uuid，允许用户直接写变量名
VAR_FIELDS = ("VAR", "valname")


# ---------------------------------------------------------------- 数据加载
def load_json(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def load_tables():
    struct = load_json(STRUCT_PATH) if os.path.exists(STRUCT_PATH) else {}
    raw = load_json(DEFS_PATH) if os.path.exists(DEFS_PATH) else {}
    defs = {}
    for btype, frag in raw.items():
        inputs = {}
        for m in re.finditer(r'<value name="([^"]+)"[^>]*>([\s\S]*?)</value>', frag):
            name, inner = m.group(1), m.group(2)
            sm = re.search(r'<shadow type="([^"]+)"[^>]*>([\s\S]*?)</shadow>', inner)
            em = re.search(r'<empty type="([^"]+)"[^>]*>([\s\S]*?)</empty>', inner)
            if sm:
                inputs[name] = {"kind": "shadow", "type": sm.group(1), "fields": sm.group(2)}
            elif em:
                inputs[name] = {"kind": "empty", "type": em.group(1)}
        if inputs:
            defs[btype] = inputs
    return struct, defs


STRUCT, DEFS = load_tables()


def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


# ---------------------------------------------------------------- 项目操作
def entities(proj):
    th = proj.get("theatre") or {}
    for sc in (th.get("scenes") or {}).values():
        yield sc.get("name") or "?", sc
    for ac in (th.get("actors") or {}).values():
        yield ac.get("name") or "?", ac


def bdj_of(ent):
    b = ent.get("block_data_json") or {}
    return b.get("blocks") or {}, b.get("connections") or {}


def parents(conns):
    out = {}
    for src, cs in conns.items():
        for tgt, meta in cs.items():
            out.setdefault(tgt, (src, meta))
    return out


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
    return t or "?"


HAT_TYPES = {"procedures_2_defnoreturn", "procedures_2_return_value",
             "self_listen", "start_as_a_mirror", "start_on_click",
             "start_on_msg", "start_on_tag", "on_key", "on_keydown",
             "on_swipe", "start_on_cloud_msg"}


def script_heads(blocks, conns):
    """返回 [(label, head_block_id, root_id)]，head 是脚本体的第一句（可能没有）"""
    out = []
    for r in blocks.values():
        if r.get("parent_id"):
            continue
        t = r.get("type")
        if t not in HAT_TYPES:
            continue          # 孤立积木，不是脚本
        label = script_label(r)
        head = None
        if t in ("procedures_2_defnoreturn", "procedures_2_return_value",
                 "start_as_a_mirror", "self_listen"):
            for tgt, m in (conns.get(r["id"]) or {}).items():
                if m.get("type") == "input" and m.get("input_type") == "statement":
                    head = tgt
        if head is None:
            for tgt, m in (conns.get(r["id"]) or {}).items():
                if m.get("type") == "next":
                    head = tgt
        out.append((label, head, r["id"]))
    return out


def _name_hit(pattern, actual):
    """'=X' 精确，'/re/' 正则，其余子串。不写 = 时 遍历 会同时命中 遍历自己。"""
    actual = actual or ""
    if pattern.startswith("="):
        return actual == pattern[1:]
    if pattern.startswith("/") and pattern.endswith("/") and len(pattern) > 2:
        return re.search(pattern[1:-1], actual) is not None
    return pattern in actual


def stmt_order(blocks, conns, label_filter=None):
    """按执行顺序列出语句：[(脚本名, 路径, 序号, 块id)]，会下钻语句体"""
    out = []

    def walk(head, path, label):
        cur, i = head, 0
        while cur and cur in blocks:
            out.append((label, path, i, cur))
            b = blocks[cur]
            for tgt, m in (conns.get(cur) or {}).items():
                if m.get("type") == "input" and m.get("input_type") == "statement":
                    sub = f"{path}/{b['type']}.{m['input_name']}" if path else f"{b['type']}.{m['input_name']}"
                    walk(tgt, sub, label)
            nxt = [t2 for t2, m2 in (conns.get(cur) or {}).items() if m2.get("type") == "next"]
            cur = nxt[0] if nxt else None
            i += 1

    for label, head, _root in script_heads(blocks, conns):
        if label_filter and not _name_hit(label_filter, label):
            continue
        if head:
            walk(head, "", label)
    return out


# ---------------------------------------------------------------- 构造器
class Builder:
    def __init__(self, proj, blocks, conns):
        self.proj = proj
        self.blocks = blocks
        self.conns = conns
        self.var_by_name = {}
        for vid, v in (proj.get("variables") or {}).items():
            self.var_by_name[v.get("name")] = vid
        self.warnings = []

    def new_id(self):
        while True:
            i = "".join(random.choice(ALPHABET) for _ in range(20))
            if i not in self.blocks:
                return i

    # -------------------------------------------------- shadow 模板
    def shadow_tpl(self, btype, iname, real_fields=None):
        """给值槽生成默认 shadow XML（phantom id）。三级来源：defs → 项目实例 → 空"""
        d = (DEFS.get(btype) or {}).get(iname)
        if d is None:
            return self._borrow_shadow(btype, iname)
        sid = self.new_id()
        if d["kind"] == "empty":
            return f'<empty {XMLNS} type="{d["type"]}" id="{sid}" visible="visible" editable="false"></empty>'
        fields = d.get("fields") or ""
        rf = real_fields or {}
        if d["type"] == "lists_get" and rf.get("VAR"):
            fields = f'<field name="VAR">{esc(rf["VAR"])}</field>'
        elif d["type"] == "get_audios" and rf.get("sound_id"):
            fields = f'<field name="sound_id">{esc(rf["sound_id"])}</field>'
        elif d["type"] == "math_number":
            m = re.search(r'name="NUM"[^>]*>([\s\S]*?)</field>', fields)
            num = m.group(1) if m else "0"
            fields = f'<field constraints="-Infinity,Infinity,0," allow_text="true" name="NUM">{esc(num)}</field>'
        inline = ' inline="true"' if d["type"] in ("lists_get", "get_audios", "get_whole_audios") else ""
        return f'<shadow {XMLNS} type="{d["type"]}" id="{sid}"{inline} visible="visible">{fields}</shadow>'

    def _borrow_shadow(self, btype, iname):
        """defs 没收录时，去项目里找一个同类块，抄它这个槽的 shadow（换掉 id）"""
        for bid, b in self.blocks.items():
            if b.get("type") != btype:
                continue
            raw = (b.get("shadows") or {}).get(iname)
            if isinstance(raw, str) and ("<shadow" in raw or "<empty" in raw):
                return re.sub(r'id="[^"]+"', f'id="{self.new_id()}"', raw, count=1)
        self.warnings.append(f"{btype}.{iname} 没有 shadow 模板（defs 与项目内都没找到），该槽留空")
        return ""

    # -------------------------------------------------- 造块
    def build(self, spec, parent=None, loc=None):
        if not isinstance(spec, dict) or "type" not in spec:
            raise ValueError(f"积木规格缺少 type: {spec!r}")
        t = spec["type"]
        if STRUCT and t not in STRUCT:
            raise ValueError(
                f"未注册的积木类型 {t!r}：编辑器打开时会抛异常（积木栏消失/工作区空白）。"
                f"用 query_block.py --list 查正确名字。")
        st = STRUCT.get(t, {})
        bid = self.new_id()
        rec = {
            "type": t, "id": bid, "comment": None, "is_shadow": False,
            "collapsed": False, "disabled": False, "deletable": True,
            "movable": True, "editable": True, "visible": "visible",
            "shadows": {}, "fields": {}, "field_constraints": {},
            "field_extra_attr": {}, "comment_extra": None,
            "mutation": spec.get("mutation") or "",
            "is_output": bool(st.get("output")),
            "parent_id": parent,
            "location": loc or [0, 0],
        }
        rec.pop("comment_extra", None)
        self.blocks[bid] = rec
        self.conns[bid] = {}

        specs_inputs = spec.get("inputs") or {}
        specs_body = spec.get("body") or {}
        inputs_meta = {i["name"]: i["kind"] for i in (st.get("inputs") or [])}

        # 0) 占位槽「$」：值写成 HOLDER 表示「这里留给被包住的原块」。
        #    先摘出来，槽位处理时跳过它，最后统一补一份默认 shadow（phantom）。
        holder_slots = [k for k, v in specs_inputs.items() if v == HOLDER]
        if holder_slots:
            specs_inputs = {k: v for k, v in specs_inputs.items() if v != HOLDER}

        # 1) 字段（field_* 类输入 + 用户显式给的 fields）
        for k, v in (spec.get("fields") or {}).items():
            rec["fields"][k] = self._resolve_field(k, v)
            if k == "VAR" and isinstance(self.blocks.get(bid), dict):
                pass

        # 2) 逐槽处理
        for name, kind in inputs_meta.items():
            if kind == "statement":
                rec["shadows"][name] = ""       # 规则 4
                chain = specs_body.get(name)
                if chain:
                    first = self.build_chain(chain, bid, offset=1)
                    if first:
                        self.conns[bid][first] = {"type": "input",
                                                  "input_type": "statement",
                                                  "input_name": name}
                        self.blocks[first]["parent_id"] = bid
                continue
            if kind == "value":
                if name in specs_inputs and specs_inputs[name] is not None:
                    val = specs_inputs[name]
                    if isinstance(val, dict):
                        # 真实子块 + phantom shadow（规则 3）
                        child = self.build(val, bid)
                        self.conns[bid][child] = {"type": "input",
                                                  "input_type": "value",
                                                  "input_name": name}
                        self.blocks[child]["parent_id"] = bid
                        rec["shadows"][name] = self.shadow_tpl(t, name, val.get("fields"))
                    else:
                        # 标量 → 自建影子块
                        self._build_literal(bid, name, val, t)
                else:
                    rec["shadows"][name] = self.shadow_tpl(t, name)
                continue
            # field_* 类：有值就写，没值走 defs 的默认
            if name in specs_inputs and specs_inputs[name] is not None:
                rec["fields"][name] = self._resolve_field(name, specs_inputs[name])

        # 3) body 里有、但 struct 没列出的槽（老版本结构表不全时兜底）
        for name, chain in specs_body.items():
            if name in inputs_meta:
                continue
            rec["shadows"][name] = ""
            first = self.build_chain(chain, bid, offset=1)
            if first:
                self.conns[bid][first] = {"type": "input",
                                          "input_type": "statement",
                                          "input_name": name}
                self.blocks[first]["parent_id"] = bid

        # 3.5) inputs 里有、但 struct 没列出的值槽（controls_if 的 IF1/IF2… 这类动态槽）
        for name, val in specs_inputs.items():
            if name in inputs_meta or val is None:
                continue
            if isinstance(val, dict):
                child = self.build(val, bid)
                self.conns[bid][child] = {"type": "input",
                                          "input_type": "value",
                                          "input_name": name}
                self.blocks[child]["parent_id"] = bid
                rec["shadows"][name] = self.shadow_tpl(t, name, val.get("fields"))
            else:
                self._build_literal(bid, name, val, t)

        # 3.8) 占位槽「$」补默认 shadow（等调用方把被包住的块接进来）
        for name in holder_slots:
            kind = inputs_meta.get(name, "value")
            rec["shadows"][name] = "" if kind == "statement" else self.shadow_tpl(t, name)

        # 4) controls_if 的 mutation 与 dummy 槽（编辑器靠它显示「加否则」按钮）
        if t == "controls_if":
            n_if = max([1] + [int(m.group(1)) + 1 for k in list(specs_body) + list(specs_inputs)
                              for m in [re.fullmatch(r"IF(\d+)", k)] if m])
            has_else = "ELSE" in specs_body
            rec["mutation"] = self._if_mutation(n_if, has_else)
            for i in range(1, n_if):
                rec["shadows"].setdefault(f"IF_TEXT{i}", "")
                rec["shadows"].setdefault(f"DO{i}", "")
                rec["shadows"].setdefault(f"IF{i}", self.shadow_tpl(t, f"IF{i}"))
            rec["shadows"].setdefault("DO0", "")
            if has_else:
                rec["shadows"]["ELSE_TEXT"] = ""
                rec["shadows"]["ELSE"] = ""
            else:
                rec["shadows"]["EXTRA_ADD_ELSE"] = ""

        # 5) 变量下拉的默认 shadow（与项目内真实块保持一致：variables_set 只带 VALUE 的 shadow）
        return bid

    def _resolve_field(self, name, val):
        if name in VAR_FIELDS and isinstance(val, str) and val in self.var_by_name:
            return self.var_by_name[val]
        return val

    def _name_of_var(self, vid):
        for name, v in self.var_by_name.items():
            if v == vid:
                return name
        return None

    def _if_mutation(self, n_if, has_else):
        parts = []
        if n_if > 1:
            parts.append(f'elseif="{n_if - 1}"')
        if has_else:
            parts.append('else="1"')
        if not parts:
            return ""
        return f'<mutation {XMLNS} {" ".join(parts)}></mutation>'

    def _build_literal(self, parent, name, val, parent_type):
        """标量输入 → 造一个 is_shadow 叶子块，并把 shadow XML 写进父块"""
        if isinstance(val, bool):
            vtype, flds = "logic_boolean", {"BOOL": "TRUE" if val else "FALSE"}
        elif isinstance(val, (int, float)):
            vtype, flds = "math_number", {"NUM": str(val)}
        else:
            vtype, flds = "text", {"TEXT": str(val)}
        sid = self.new_id()
        srec = {
            "type": vtype, "id": sid, "comment": None, "is_shadow": True,
            "collapsed": False, "disabled": False, "deletable": True,
            "movable": True, "editable": True, "visible": "visible",
            "shadows": {}, "fields": flds, "field_constraints": {},
            "field_extra_attr": {}, "mutation": "",
            "is_output": None if vtype == "math_number" else True,
            "parent_id": parent, "location": [0, 0],
        }
        if vtype == "math_number":
            srec["field_constraints"] = {"NUM": {"min": None, "max": None, "precision": 0, "mod": None}}
        self.blocks[sid] = srec
        self.conns[sid] = {}
        if vtype == "math_number":
            inner = f'<field constraints="-Infinity,Infinity,0," allow_text="true" name="NUM">{esc(val)}</field>'
        else:
            inner = "".join(f'<field name="{k}">{esc(v)}</field>' for k, v in flds.items())
        self.blocks[parent]["shadows"][name] = (
            f'<shadow {XMLNS} type="{vtype}" id="{sid}" visible="visible">{inner}</shadow>')
        self.conns[parent][sid] = {"type": "input", "input_type": "value", "input_name": name}
        return sid

    def build_chain(self, specs, parent, offset=0, loc=None):
        """造一条语句链，返回链首 id"""
        ids = []
        for i, sp in enumerate(specs):
            at = None
            if loc:
                at = [loc[0], loc[1] + i * 40]
            ids.append(self.build(sp, parent, at or [0, offset * 40 + i * 40]))
        for a, b in zip(ids, ids[1:]):
            self.conns[a][b] = {"type": "next"}
            self.blocks[b]["parent_id"] = a
        return ids[0] if ids else None

    def chain_tail(self, head):
        cur = head
        while True:
            nxt = [t for t, m in (self.conns.get(cur) or {}).items() if m.get("type") == "next"]
            if not nxt:
                return cur
            cur = nxt[0]


# ---------------------------------------------------------------- 插入
def insert_before(blocks, conns, target, head):
    pmap = parents(conns)
    src, meta = pmap.get(target, (None, None))
    if src is None:
        return False, "目标是脚本头，不能在前面插"
    tail = head
    while True:
        nxt = [t for t, m in (conns.get(tail) or {}).items() if m.get("type") == "next"]
        if not nxt:
            break
        tail = nxt[0]
    del conns[src][target]
    if meta.get("type") == "next":
        conns[src][head] = {"type": "next"}
    else:
        conns[src][head] = dict(meta)
    blocks[head]["parent_id"] = src
    conns[tail][target] = {"type": "next"}
    blocks[target]["parent_id"] = tail
    return True, "ok"


def insert_after(blocks, conns, target, head):
    tail = head
    while True:
        nxt = [t for t, m in (conns.get(tail) or {}).items() if m.get("type") == "next"]
        if not nxt:
            break
        tail = nxt[0]
    succ = [t for t, m in (conns.get(target) or {}).items() if m.get("type") == "next"]
    conns[target][head] = {"type": "next"}
    blocks[head]["parent_id"] = target
    if succ:
        conns[tail][succ[0]] = {"type": "next"}
        blocks[succ[0]]["parent_id"] = tail
    return True, "ok"


def insert_into_empty_body(blocks, conns, owner_id, slot, head):
    blocks[owner_id]["shadows"][slot] = ""
    conns[owner_id][head] = {"type": "input", "input_type": "statement", "input_name": slot}
    blocks[head]["parent_id"] = owner_id
    return True, "ok"


# ---------------------------------------------------------------- 校验
def verify(proj):
    """落盘前的完整性校验。

    除了"引用都存在"这类硬错误，还查两类会静默炸掉的形状问题
    （编辑时一切正常，用户之后一改输入就坏，所以必须在写盘前拦住）：
      · 值槽里挂了真块，但父块的 shadows 里没有该槽的模板（phantom shadow 丢失）
      · controls_if 的 mutation 与实际分支/否则槽不符
    """
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
            if bid not in conns:
                errs.append(f"{name}: 块 {bid}({b.get('type')}) 没有 connections 条目")
                continue
            p = b.get("parent_id")
            if p and p not in blocks:
                errs.append(f"{name}: 块 {bid} 的 parent_id 悬空")
            sh = b.get("shadows") or {}
            for tgt, m in conns[bid].items():
                if m.get("type") != "input":
                    continue
                nm, it = m.get("input_name"), m.get("input_type")
                if it == "value" and not isinstance(sh.get(nm), str):
                    errs.append(f"{name}: 块 {bid}({b.get('type')}) 的值槽 {nm} 挂了子块，"
                                f"但父块 shadows 缺该槽模板（phantom shadow 丢失）")
                if it == "statement" and nm not in sh:
                    errs.append(f"{name}: 块 {bid}({b.get('type')}) 的语句槽 {nm} 缺空壳标记")
            if b.get("type") == "controls_if":
                errs += [f"{name}: {e}" for e in _check_if(bid, b, conns[bid])]
    return errs


def _check_if(bid, b, cs):
    out = []
    mut = b.get("mutation") or ""
    ins = [str(m.get("input_name")) for m in cs.values()
           if m.get("type") == "input" and str(m.get("input_name")).startswith("IF")]
    n_if = max([int(x[2:]) for x in ins if x[2:].isdigit()] + [0]) + 1
    want_ei = n_if - 1
    want_else = "ELSE" in (b.get("shadows") or {})
    m_ei = re.search(r'elseif="(\d+)"', mut)
    got_ei = int(m_ei.group(1)) if m_ei else 0
    got_else = bool(re.search(r'\belse="1"', mut))
    if got_ei != want_ei:
        out.append(f"块 {bid} 的 mutation elseif={got_ei}，实际有 {want_ei} 个『否则如果』")
    if got_else != want_else:
        out.append(f"块 {bid} 的 mutation else={got_else}，实际否则槽{'有' if want_else else '无'}")
    return out


# ---------------------------------------------------------------- CLI
def find_entity(proj, actor_kw):
    for name, ent in entities(proj):
        if actor_kw in name:
            return name, ent
    raise SystemExit(f"找不到角色/场景: {actor_kw}")


def resolve_target(blocks, conns, func_kw, index):
    """按函数名 + 语句序号定位。index=-1 表示函数体为空/取函数头"""
    orders = stmt_order(blocks, conns, label_filter=func_kw)
    top = [o for o in orders if o[1] == ""]
    if index < 0:
        if top:
            return top[0][3], False
        for label, head, root in script_heads(blocks, conns):
            if _name_hit(func_kw, label):
                return root, True     # 返回脚本头，调用方改用空体插入
        raise SystemExit(f"找不到函数 {func_kw}")
    if index >= len(top):
        raise SystemExit(f"{func_kw} 顶层只有 {len(top)} 条语句，index={index} 越界")
    return top[index][3], False


def cmd_list(proj):
    for name, ent in entities(proj):
        blocks, conns = bdj_of(ent)
        heads = script_heads(blocks, conns)
        if not heads:
            continue
        print(f"\n[{name}]")
        for label, head, root in sorted(heads, key=lambda x: x[0]):
            n = len([o for o in stmt_order(blocks, conns, label) if o[1] == ""])
            print(f"   {label:28s} 顶层语句 {n}")


def func_blocks(blocks, conns, func_kw):
    """某个脚本（函数/广播/帽子）里所有块的 id 集合，含值槽里的子块。"""
    ids = set()
    for label, head, _root in script_heads(blocks, conns):
        if not _name_hit(func_kw, label):
            continue
        stack = [head] if head else []
        while stack:
            cur = stack.pop()
            if cur in ids or cur not in blocks:
                continue
            ids.add(cur)
            for tgt in (conns.get(cur) or {}):
                stack.append(tgt)
    return ids


# 这些类型不是「数值」，套数学运算会类型错乱（列表引用、文本、布尔…）
NON_NUMERIC = {"lists_get", "get_audios", "get_whole_audios", "text",
               "logic_boolean", "logic_compare", "logic_operation", "logic_negate",
               "text_join", "text_split"}


def find_wrap_targets(blocks, conns, btype, slots, scope=None):
    """列出 (父块id, 槽名, 槽里现有的块id)，只算挂了真实子块的值槽。

    会自动跳过子块是非数值类型（列表引用/文本/布尔）的槽——用 --input * 也不会误伤。
    """
    out = []
    skipped = 0
    for bid, b in blocks.items():
        if b.get("type") != btype:
            continue
        if scope is not None and bid not in scope:
            continue
        for tgt, m in (conns.get(bid) or {}).items():
            if m.get("type") != "input" or m.get("input_type") != "value":
                continue
            nm = m.get("input_name")
            if slots and nm not in slots:
                continue
            if blocks.get(tgt, {}).get("type") in NON_NUMERIC:
                skipped += 1
                continue
            out.append((bid, nm, tgt))
    return out, skipped


def wrap_slot(blocks, conns, parent_bid, slot_name, wrapper_bid, holder_slot, inner_bid):
    """把 wrapper 塞进 parent 的 slot_name 槽，原来槽里的块接到 wrapper 的 holder_slot。"""
    for t, m in list((conns.get(parent_bid) or {}).items()):
        if (m.get("type") == "input" and m.get("input_type") == "value"
                and m.get("input_name") == slot_name):
            del conns[parent_bid][t]
    conns[parent_bid][wrapper_bid] = {"type": "input", "input_type": "value",
                                      "input_name": slot_name}
    blocks[wrapper_bid]["parent_id"] = parent_bid
    if inner_bid:
        conns[wrapper_bid][inner_bid] = {"type": "input", "input_type": "value",
                                         "input_name": holder_slot}
        blocks[inner_bid]["parent_id"] = wrapper_bid


def cmd_wrap(args):
    """把某个类型的所有实例的指定值槽，各包一层包装块（如四舍五入）。

    只改连接，不增删语句，所以 show 里的 [N] 编号在 wrap 前后不变，可以反复叠。
    """
    if not args.block:
        raise SystemExit("wrap 需要 --block（包装块规格，其中一个槽写 \"$\" 表示被包住的原块）")
    if not args.type:
        raise SystemExit("wrap 需要 --type（要包哪种积木的槽，如 self_move_to）")
    spec = load_json(args.block)
    if isinstance(spec, list):
        if len(spec) != 1:
            raise SystemExit("wrap 的 --block 只能是一块")
        spec = spec[0]
    holders = [k for k, v in (spec.get("inputs") or {}).items() if v == HOLDER]
    if len(holders) != 1:
        raise SystemExit(f'包装块规格里必须且只能有一个槽写成 "{HOLDER}"，现在是 {holders}')
    holder = holders[0]

    proj = load_json(args.path)
    pool = ([find_entity(proj, args.actor)] if args.actor
            else list(entities(proj)))

    slots = None
    if args.input and args.input.strip() != "*":
        slots = {s.strip() for s in args.input.split(",") if s.strip()}
    nest = max(1, args.nest or 1)
    grand = 0
    grand_targets = 0
    for name, ent in pool:
        blocks, conns = bdj_of(ent)
        scope = func_blocks(blocks, conns, args.func) if args.func else None
        targets, skipped = find_wrap_targets(blocks, conns, args.type, slots, scope)
        if skipped:
            print(f"[{name}] 跳过 {skipped} 个非数值槽（列表引用/文本/布尔）")
        if not targets:
            continue
        if args.limit:
            targets = targets[: args.limit]
        builder = Builder(proj, blocks, conns)
        before = len(blocks)
        for parent_bid, slot_name, child in targets:
            inner = child
            for _ in range(nest):
                w = builder.build(spec, None)
                wrap_slot(blocks, conns, parent_bid, slot_name, w, holder, inner)
                inner = w
        for w in builder.warnings:
            print("   !", w)
        print(f"[{name}] {args.type} 包 {len(targets)} 个槽 × {nest} 层，"
              f"新增 {len(blocks) - before} 个块")
        grand += len(blocks) - before
        grand_targets += len(targets)

    if not grand_targets:
        raise SystemExit(f"{args.type} 没有挂在真实块上的值槽"
                         + (f"（限定槽 {sorted(slots)}）" if slots else ""))
    print(f"合计：{grand_targets} 个槽，新增 {grand} 个块")

    errs = verify(proj)
    if errs:
        print("!! 校验失败，拒绝写入：")
        for e in errs[:10]:
            print("   ", e)
        sys.exit(1)
    print("校验通过（连接/parent_id/shadow 形状全部有效）")
    if args.write:
        bak = f"{args.path}.bak.{time.strftime('%Y%m%d_%H%M%S')}"
        with open(args.path, encoding="utf-8") as src, open(bak, "w", encoding="utf-8") as dst:
            dst.write(src.read())
        print("已备份 →", bak)
        with open(args.path, "w", encoding="utf-8") as f:
            f.write(js_dumps(proj))
        print("已写入", args.path)
    else:
        print("(dry-run，未写盘。确认无误后加 --write)")


def cmd_show(args):
    name, ent = find_entity(args.path_proj, args.actor) if args.actor else (None, None)
    pool = [(name, ent)] if ent else list(entities(args.path_proj))
    for ename, ent in pool:
        blocks, conns = bdj_of(ent)
        # 编号始终按「本角色内所有脚本的执行顺序」算，与 --func 过滤无关，
        # 这样同一个 [N] 在 show 和 insert 里永远指同一个块。
        rows = stmt_order(blocks, conns, None)
        shown = [(g, r) for g, r in enumerate(rows)
                 if not args.func or _name_hit(args.func, r[0])]
        if not shown:
            continue
        print(f"\n[{ename}] {args.func or '全部'}")
        for g, (label, path, idx, bid) in shown[: (args.limit or 20)]:
            b = blocks[bid]
            f = b.get("fields") or {}
            desc = b.get("type")
            if f:
                desc += " " + json.dumps(f, ensure_ascii=False)[:70]
            if path:
                pad = "  " * (1 + path.count("/"))
                print(f"   [{g:3d}]   {pad}└ {desc}")
            else:
                print(f"   [{g:3d}] {idx:3d}  {desc}")


def main():
    ap = argparse.ArgumentParser(description="从积木定义构造新块并插入 .bcm4")
    ap.add_argument("path")
    ap.add_argument("action", choices=["list", "show", "insert", "wrap"])
    ap.add_argument("--actor", help="角色/场景名（子串）")
    ap.add_argument("--func", help="函数/脚本名（子串）；wrap 时限定只包这个函数里的槽")
    ap.add_argument("--index", type=int, default=-1, help="插入到该函数的第几条顶层语句(0起)；-1=函数体开头")
    ap.add_argument("--at", type=int, help="按 show 输出的全局编号 [N] 精确定位（可定位到 if/循环体内部）")
    ap.add_argument("--pos", choices=["before", "after"], default="before")
    ap.add_argument("--block", help="积木规格 JSON 文件")
    ap.add_argument("--type", dest="type", help="wrap：要包哪种积木（如 self_move_to）")
    ap.add_argument("--input", help="wrap：只包这些值槽，逗号分隔；* 或不写=全部值槽")
    ap.add_argument("--nest", type=int, default=1, help="wrap：套几层（默认 1）")
    ap.add_argument("--limit", type=int, help="show 默认显示 20 条；wrap 默认不限")
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    proj = load_json(args.path)
    args.path_proj = proj
    if args.action == "list":
        cmd_list(proj)
        return
    if args.action == "show":
        cmd_show(args)
        return
    if args.action == "wrap":
        cmd_wrap(args)
        return

    # ---- insert
    if not args.block:
        raise SystemExit("insert 需要 --block")
    if args.at is None and not args.func:
        raise SystemExit("insert 需要 --func/--index，或用 --at 指定 show 里的全局编号")
    spec = load_json(args.block)
    specs = spec if isinstance(spec, list) else [spec]
    for s in specs:
        if not isinstance(s, dict) or not s.get("type"):
            raise SystemExit(f"每条积木规格都必须是带 type 的对象：{s!r}")
    name, ent = find_entity(proj, args.actor) if args.actor else next(iter(entities(proj)))
    blocks, conns = bdj_of(ent)
    builder = Builder(proj, blocks, conns)

    if args.at is not None:
        # 与 show 完全一致：本角色内所有脚本的执行顺序，不做 --func 过滤
        rows = stmt_order(blocks, conns, None)
        if not 0 <= args.at < len(rows):
            raise SystemExit(f"--at {args.at} 越界（共 {len(rows)} 条）")
        label, path, idx, target = rows[args.at]
        if args.func and not _name_hit(args.func, label):
            raise SystemExit(f"--at {args.at} 落在脚本 [{label}]，与 --func {args.func} 不符")
        empty_body = False
        where = f"{label} / {path or '顶层'}"
        print(f"定位到 [{args.at}] {where} / {blocks[target]['type']}")
    else:
        target, empty_body = resolve_target(blocks, conns, args.func, args.index)
    tloc = blocks[target].get("location") or [0, 0]
    # 新块放在目标块的正上方(before)或正下方(after)，避免全叠在 (0,0)
    dy = -40 * len(specs) if args.pos == "before" else 40
    loc = [tloc[0], tloc[1] + dy]
    if empty_body:
        head = builder.build_chain(specs, target, loc=loc)
        ok, msg = insert_into_empty_body(blocks, conns, target, "STACK", head)
    elif args.pos == "before":
        head = builder.build_chain(specs, None, loc=loc)
        ok, msg = insert_before(blocks, conns, target, head)
    else:
        head = builder.build_chain(specs, None, loc=loc)
        ok, msg = insert_after(blocks, conns, target, head)

    for w in builder.warnings:
        print("   !", w)
    print(f"[{name}] 插入{'成功' if ok else '失败'}：{msg}")

    errs = verify(proj)
    if errs:
        print("!! 校验失败，拒绝写入：")
        for e in errs[:10]:
            print("   ", e)
        sys.exit(1)
    print("校验通过（连接/parent_id/connections 条目全部有效）")
    if args.write:
        bak = f"{args.path}.bak.{time.strftime('%Y%m%d_%H%M%S')}"
        with open(args.path, encoding="utf-8") as src, open(bak, "w", encoding="utf-8") as dst:
            dst.write(src.read())
        print("已备份 →", bak)
        with open(args.path, "w", encoding="utf-8") as f:
            f.write(js_dumps(proj))
        print("已写入", args.path)
    else:
        print("(dry-run，未写盘。确认无误后加 --write)")


if __name__ == "__main__":
    main()
