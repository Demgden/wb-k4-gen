#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""extract_dsl_api.py — 从 tools/bcm4gen.js 抽取「生成 DSL API」索引。

动机：agent 想知道「克隆体自毁用哪个函数」时，唯一的办法是通读 566 行 bcm4gen.js。
本脚本把 DSL 导出面自动抽成机器可读 JSON，agent 就能用 query_block.py --dsl 查，
而不是读源码。索引随源码自动再生，永远不会与实现漂移。

产出：data/dsl_api.json
  { "name": {"section","kind","params","editor_type","reporter","doc","warnings"} }

用法：
  python tools/extract_dsl_api.py            # 抽取并写 data/dsl_api.json
  python tools/extract_dsl_api.py --check    # 只校验：索引是否与源码同步（不写文件）
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
SRC = os.path.join(ROOT, "tools", "bcm4gen.js")
OUT = os.path.join(ROOT, "data", "dsl_api.json")

# 章节横幅形如：// ================== 音频   （结尾的 = 可有可无）
BANNER_RE = re.compile(r"^//\s*=+[\s=]*(.*?)\s*=*\s*$")
# 导出清单里的 getter（get state()）不是函数
GETTER_RE = re.compile(r"^\s*get\s+(\w+)\s*\(")


def parse_exports(src):
    """从 module.exports = { ... } 里取出导出的函数名（跳过 getter）。"""
    m = re.search(r"module\.exports\s*=\s*\{", src)
    if not m:
        raise SystemExit("找不到 module.exports")
    # 找到配对的右花括号
    i = m.end() - 1
    depth = 0
    for j in range(i, len(src)):
        if src[j] == "{":
            depth += 1
        elif src[j] == "}":
            depth -= 1
            if depth == 0:
                end = j
                break
    else:
        raise SystemExit("module.exports 花括号不配对")

    body = src[m.end():end]
    names, depth = [], 0
    for line in body.splitlines():
        s = line.strip()
        if not s or s.startswith("//"):
            continue
        if GETTER_RE.match(s):
            continue
        for tok in re.findall(r"[A-Za-z_$][A-Za-z0-9_$]*", s):
            names.append(tok)
    # 去重保序
    seen, out = set(), []
    for n in names:
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out


def find_definitions(src):
    """扫描顶层定义：名字 -> (行号, 参数列表原文, 注释块, 所属章节)。"""
    lines = src.splitlines()
    defs = {}
    section = ""
    pending_comment = []

    for idx, line in enumerate(lines):
        bm = BANNER_RE.match(line.strip())
        if bm:
            section = bm.group(1).strip()
            pending_comment = []
            continue

        # 顶层定义（列 0 开始）
        m = re.match(r"^(?:const|function)\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*(=\s*)?(\([^)]*\))?", line)
        if not m:
            if line.strip().startswith("//"):
                pending_comment.append(line.strip().lstrip("/").strip())
            else:
                pending_comment = []
            continue

        name = m.group(1)
        params = m.group(3) or ""
        if not params and m.group(2):  # const NAME = value（无参数列表）
            params = ""

        defs[name] = {
            "name": name,
            "line": idx,
            "params_raw": params,
            "comment": list(pending_comment),
            "section": section,
        }
        pending_comment = []

    return defs, lines


def body_of(lines, start_line):
    """取一个顶层定义到下一个顶层定义（或文件尾）之间的正文。"""
    out = []
    for k in range(start_line, len(lines)):
        line = lines[k]
        if k > start_line and re.match(r"^(?:const|function)\s+[A-Za-z_$][A-Za-z0-9_$]*", line):
            break
        out.append(line)
    return "\n".join(out)


def parse_params(raw):
    """把 (a, b = 0, ...rest) 解析成 [{name, default, rest}]。"""
    raw = raw.strip()
    if raw.startswith("(") and raw.endswith(")"):
        raw = raw[1:-1]
    raw = raw.strip()
    if not raw:
        return []
    params, depth, cur = [], 0, ""
    for ch in raw:
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        if ch == "," and depth == 0:
            params.append(cur)
            cur = ""
        else:
            cur += ch
    if cur.strip():
        params.append(cur)

    out = []
    for p in params:
        p = p.strip()
        if not p:
            continue
        rest = p.startswith("...")
        p = p.lstrip(".")
        default = None
        if "=" in p:
            name, default = p.split("=", 1)
            name, default = name.strip(), default.strip()
        else:
            name = p.strip()
        out.append({"name": name, "default": default, "rest": rest})
    return out


# type 字段必须带词边界：否则 work_type:"KITTEN" 会被误当成 type:"KITTEN"
TYPE_RE = re.compile(r'(?<![A-Za-z0-9_])type:\s*"([A-Za-z0-9_]+)"')
BTYPE_RE = re.compile(r'B\(\s*"([A-Za-z0-9_]+)"')


def _match_brace(s, start):
    """从 s[start] 处的 '{' 开始，返回配对 '}' 的下标。"""
    depth = 0
    for i in range(start, len(s)):
        if s[i] == "{":
            depth += 1
        elif s[i] == "}":
            depth -= 1
            if depth == 0:
                return i
    return -1


def returned_type(body):
    """只从「返回值表达式」里取 type 字段，深度必须为 1。

    否则会误取：
      - defVar   → type:"any"（VAR_DEFS 的变量类型，不是积木）
      - emitScript → type:"set_layer_with_pen"（函数体里另一个字面块）
    只认两种返回形态：
      箭头函数简写体   => ({ type: "x", ... })
      function 的 return { type: "x", ... }
    """
    candidates = []
    # 1) 箭头函数简写体：=> ({ ... })  或  => { ... }
    #    注意括号形态有两种：=> ({...}) 与 => {...}，都要覆盖
    for m in re.finditer(r"=>\s*(?:\(\s*)?\{", body):
        b = body.index("{", m.end() - 1)
        e = _match_brace(body, b)
        if e > b:
            candidates.append(body[b:e + 1])
    # 2) function 的 return 对象
    for m in re.finditer(r"\breturn\s*\{", body):
        b = body.index("{", m.end() - 1)
        e = _match_brace(body, b)
        if e > b:
            candidates.append(body[b:e + 1])

    for expr in candidates:
        # 只在深度 1 处找 type 字段
        depth = 0
        for i, ch in enumerate(expr):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
            elif depth == 1:
                mm = TYPE_RE.match(expr, i)
                if mm:
                    return mm.group(1)
    return None

WARN_RE = re.compile(r"(★|注意|警告|铁律|必须|禁止|不能|不要|仅|坑|风险|注意！)")


def extract():
    src = open(SRC, encoding="utf-8").read()
    exports = parse_exports(src)
    defs, lines = find_definitions(src)

    api = {}
    for name in exports:
        d = defs.get(name)
        if not d:
            # 导出但没找到顶层定义（理论上不该发生）——跳过并让 --check 报警
            continue
        body = body_of(lines, d["line"])

        etype = returned_type(body)
        if etype is None:
            # B("xxx", ...) 形式：取 B 的第一个实参
            bm = BTYPE_RE.search(body)
            if bm:
                etype = bm.group(1)

        comment = [c for c in d["comment"] if c.strip() and not c.strip().startswith("=")]
        doc_lines = [c for c in comment if not WARN_RE.search(c)]
        warn_lines = [c for c in comment if WARN_RE.search(c)]

        api[name] = {
            "section": d["section"],
            "order": d["line"],
            "kind": "reporter" if "out: true" in body else "statement",
            "params": parse_params(d["params_raw"]),
            "editor_type": etype,
            "reporter": "out: true" in body,
            "doc": " ".join(doc_lines).strip(),
            "warnings": " ".join(warn_lines).strip(),
        }
    return api, exports


def main():
    api, exports = extract()
    check = "--check" in sys.argv

    if check:
        if not os.path.exists(OUT):
            print("FAIL: data/dsl_api.json 不存在，请运行 extract_dsl_api.py")
            return 1
        old = json.load(open(OUT, encoding="utf-8"))
        if old == api:
            print("OK: dsl_api.json 与 bcm4gen.js 同步（%d 个导出）" % len(api))
            return 0
        print("FAIL: dsl_api.json 已过期 —— 源码导出面或注释变了，请重跑 extract_dsl_api.py")
        oldk, newk = set(old), set(api)
        if oldk - newk:
            print("  消失的导出: %s" % ", ".join(sorted(oldk - newk)))
        if newk - oldk:
            print("  新增的导出: %s" % ", ".join(sorted(newk - oldk)))
        changed = [k for k in (oldk & newk) if old[k] != api[k]]
        if changed:
            print("  描述/签名变化的: %s" % ", ".join(sorted(changed)[:12]))
        return 1

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(api, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
    print("wrote %s (%d 个 DSL 导出，%d 字节)" % (OUT, len(api), os.path.getsize(OUT)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
