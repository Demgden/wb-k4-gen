"""与编辑器(JS)一致的 .bcm4 JSON 读写。

Python 的 json 和 JS 的 JSON.stringify 有两处不一致，写回时会让文件"看起来变了"：

1. 浮点数格式：Python 把 3.47e-06 写成科学计数法，JS 写成 0.0000034...
   （JS 规则：|x| >= 1e-6 且 < 1e21 时用定点，否则指数）
2. 整数值的浮点：Python 写 40.0，JS 写 40

这些差异不影响编辑器解析，但会让"只改了一处"的文件在 diff 里出现大量噪声，
也不利于核对写回是否精确。这里按 JS 规则重新格式化，保证无改动时字节一致。
"""

import json
import re
from decimal import Decimal

JS_FIXED_LO = 1e-6      # 小于这个值 JS 用指数写法
JS_FIXED_HI = 1e21      # 大于等于这个值 JS 用指数写法


def js_number(f):
    """按 JS Number.prototype.toString 的规则格式化一个 float。"""
    if f != f:                       # NaN
        return "null"
    if f in (float("inf"), float("-inf")):
        return "null"
    if f == 0:                       # 含 -0.0
        return "0"
    if f.is_integer() and abs(f) < JS_FIXED_HI:
        return str(int(f))
    if JS_FIXED_LO <= abs(f) < JS_FIXED_HI:
        return format(Decimal(repr(f)), "f")
    # 指数区间：JS 写作 1e+21 / 1.5e-7
    s = repr(f)
    if "e" in s or "E" in s:
        mant, _, exp = s.partition("e")
        e = int(exp)
        return f"{mant}e{'+' if e >= 0 else '-'}{abs(e)}"
    return s


def _rewrite(obj, token):
    """把需要重新格式化的 float 换成占位字符串。"""
    if isinstance(obj, float):
        s = js_number(obj)
        return obj if s == repr(obj) else f"{token}{s}{token}"
    if isinstance(obj, list):
        return [_rewrite(x, token) for x in obj]
    if isinstance(obj, dict):
        return {k: _rewrite(v, token) for k, v in obj.items()}
    return obj


def dumps(data):
    # 随机 ASCII 标记，避免与文件内容撞车，也不会被 json 转义
    import uuid
    token = f"@@JSF{uuid.uuid4().hex[:12]}@@"
    txt = json.dumps(_rewrite(data, token), ensure_ascii=False,
                     separators=(",", ":"))
    pat = '"' + re.escape(token) + '([^"]*)' + re.escape(token) + '"'
    return re.sub(pat, lambda m: m.group(1), txt)


def loads(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save(path, data, backup=None):
    """写回单行压缩 JSON（与编辑器导出一致）。backup 传路径则先备份。"""
    import shutil
    import time
    if backup:
        bak = f"{backup}.bak.{time.strftime('%Y%m%d_%H%M%S')}"
        shutil.copy2(backup, bak)
        print(f"已备份 → {bak}")
    with open(path, "w", encoding="utf-8") as f:
        f.write(dumps(data))
