#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sb3_read.py — 把 Scratch 3 的 project.json 反编译成可读文本。

用法:
  python sb3_read.py project.json                 # 总览
  python sb3_read.py project.json Player          # 某个角色全部脚本
  python sb3_read.py project.json --stats         # opcode 统计
"""
import json
import sys
from collections import Counter


class R:
    def __init__(self, p):
        self.p = p
        self.tgt = {t["name"]: t for t in p["targets"]}
        self.bl = {}
        self.varname = {}
        for t in p["targets"]:
            for k, v in (t.get("variables") or {}).items():
                self.varname[k] = v[0]
            for k, v in (t.get("lists") or {}).items():
                self.varname[k] = v[0]
            self.bl.update(t.get("blocks") or {})
        self.broadcasts = {}
        for t in p["targets"]:
            for k, v in (t.get("broadcasts") or {}).items():
                self.broadcasts[k] = v

    def nm(self, vid):
        if isinstance(vid, list):
            vid = vid[1] if len(vid) > 1 else vid[0]
        if isinstance(vid, list):
            return str(vid[0])
        return self.varname.get(vid, vid)

    def inp(self, b, name):
        """返回该输入槽的 [类型, 值/块id] 或 None"""
        v = (b.get("inputs") or {}).get(name)
        if v is None:
            for k, vv in (b.get("inputs") or {}).items():
                if k.startswith(name + "_"):
                    v = vv
                    break
        return v

    def val(self, b, name):
        v = self.inp(b, name)
        if not v:
            return ""
        if isinstance(v[1], list):
            return str(v[1][1])
        if isinstance(v[1], str):
            return self.expr(v[1])
        return str(v[1])

    def expr(self, bid, depth=0):
        b = self.bl.get(bid)
        if not isinstance(b, dict):
            return str(bid)
        op = b["opcode"]
        f = b.get("fields") or {}
        if op in ("math_number", "math_integer", "math_whole_number"):
            return str(f.get("NUM", "?"))
        if op in ("math_positive_number",):
            return str(f.get("NUM", "?"))
        if op in ("text", "looks_costume", "sound_sounds_menu", "control_create_clone_of_menu",
                  "sensing_keyoptions", "sensing_touchingobjectmenu", "sensing_of_object_menu",
                  "motion_goto_menu", "motion_pointtowards_menu", "sensing_distancetomenu",
                  "event_broadcast_menu"):
            return str(list(f.values())[0] if f else "?")
        if op == "data_variable":
            return self.nm(f.get("VARIABLE"))
        if op == "data_listcontents":
            return self.nm(f.get("LIST"))
        if op == "argument_reporter_string_number" or op == "argument_reporter_boolean":
            return "$" + str(f.get("VALUE"))
        if op == "procedures_call":
            return f"{b.get('mutation', {}).get('proccode', '?')}"
        if op == "looks_costumenumbername":
            return f"造型[{f.get('NUMBER_NAME')}]"
        if op == "operator_mathop":
            return f"{f.get('OPERATOR')}({self.val(b,'NUM')})"
        if op in ("operator_add", "operator_subtract", "operator_multiply", "operator_divide",
                  "operator_mod", "operator_equals", "operator_lt", "operator_gt",
                  "operator_and", "operator_or"):
            sym = {"operator_add": "+", "operator_subtract": "-", "operator_multiply": "*",
                   "operator_divide": "/", "operator_mod": "mod", "operator_equals": "=",
                   "operator_lt": "<", "operator_gt": ">", "operator_and": "且", "operator_or": "或"}[op]
            return f"({self.val(b,'NUM1')} {sym} {self.val(b,'NUM2')})"
        if op == "operator_not":
            return f"不({self.val(b,'OPERAND')})"
        if op == "operator_join":
            return f"合并({self.val(b,'STRING1')},{self.val(b,'STRING2')})"
        if op == "operator_letter_of":
            return f"第{self.val(b,'LETTER')}个字符({self.val(b,'STRING')})"
        if op == "operator_length":
            return f"长度({self.val(b,'STRING')})"
        if op == "operator_contains":
            return f"({self.val(b,'STRING1')} 含 {self.val(b,'STRING2')})"
        if op == "operator_random":
            return f"随机({self.val(b,'FROM')},{self.val(b,'TO')})"
        if op == "operator_round":
            return f"四舍五入({self.val(b,'NUM')})"
        if op == "data_itemoflist":
            return f"列表[{self.nm(f.get('LIST'))}]第{self.val(b,'INDEX')}项"
        if op == "data_lengthoflist":
            return f"列表[{self.nm(f.get('LIST'))}]长度"
        if op == "data_itemnumoflist":
            return f"列表[{self.nm(f.get('LIST'))}]中{self.val(b,'ITEM')}的位置"
        if op == "data_listcontainsitem":
            return f"列表[{self.nm(f.get('LIST'))}]含{self.val(b,'ITEM')}"
        if op == "sensing_of":
            return f"[{self.val(b,'OBJECT')}]的{f.get('PROPERTY')}"
        if op == "sensing_mousex":
            return "鼠标x"
        if op == "sensing_mousey":
            return "鼠标y"
        if op == "sensing_timer":
            return "计时器"
        if op == "motion_xposition":
            return "x坐标"
        if op == "motion_yposition":
            return "y坐标"
        if op == "motion_direction":
            return "方向"
        if op == "looks_size":
            return "大小"
        if op == "sensing_keypressed":
            return f"按下{self.val(b,'KEY_OPTION')}?"
        if op == "sensing_mousedown":
            return "鼠标按下?"
        if op == "sensing_touchingobject":
            return f"碰到{self.val(b,'TOUCHINGOBJECTMENU')}?"
        if op == "sensing_distanceto":
            return f"到{self.val(b,'DISTANCETOMENU')}的距离"
        if op == "sensing_username":
            return "用户名"
        args = []
        for k, v in (b.get("inputs") or {}).items():
            args.append(f"{k}={self.val(b,k)}")
        return f"{op}({', '.join(args)})"

    def stmt(self, bid, pad=0, out=None):
        out = out if out is not None else []
        while bid:
            b = self.bl.get(bid)
            if not isinstance(b, dict):
                break
            op = b["opcode"]
            f = b.get("fields") or {}
            pre = "  " * pad
            if op == "procedures_definition":
                proto = b["inputs"]["custom_block"][1]
                pb = self.bl[proto]
                out.append(f"{pre}【定义】{pb.get('mutation',{}).get('proccode')}")
            elif op == "procedures_call":
                code = b.get("mutation", {}).get("proccode", "?")
                args = [self.val(b, k) for k in sorted((b.get("inputs") or {}), key=lambda x: int(x[1:]) if x[1:].isdigit() else 0)]
                out.append(f"{pre}调用 {code} ({', '.join(args)})")
            elif op == "control_if":
                out.append(f"{pre}如果 {self.val(b,'CONDITION')} 那么")
                if b["inputs"].get("SUBSTACK"):
                    self.stmt(b["inputs"]["SUBSTACK"][1], pad + 1, out)
            elif op == "control_if_else":
                out.append(f"{pre}如果 {self.val(b,'CONDITION')} 那么")
                if b["inputs"].get("SUBSTACK"):
                    self.stmt(b["inputs"]["SUBSTACK"][1], pad + 1, out)
                out.append(f"{pre}否则")
                if b["inputs"].get("SUBSTACK2"):
                    self.stmt(b["inputs"]["SUBSTACK2"][1], pad + 1, out)
            elif op in ("control_repeat", "control_repeat_until", "control_forever", "control_while"):
                out.append(f"{pre}{op} {self.val(b,'CONDITION') or self.val(b,'TIMES')}")
                if b["inputs"].get("SUBSTACK"):
                    self.stmt(b["inputs"]["SUBSTACK"][1], pad + 1, out)
            elif op == "event_broadcast":
                out.append(f"{pre}广播 {self.val(b,'BROADCAST_INPUT')}")
            elif op == "event_broadcastandwait":
                out.append(f"{pre}广播并等待 {self.val(b,'BROADCAST_INPUT')}")
            elif op == "data_setvariableto":
                out.append(f"{pre}{self.nm(f.get('VARIABLE'))} = {self.val(b,'VALUE')}")
            elif op == "data_changevariableby":
                out.append(f"{pre}{self.nm(f.get('VARIABLE'))} += {self.val(b,'VALUE')}")
            elif op == "data_addtolist":
                out.append(f"{pre}列表[{self.nm(f.get('LIST'))}]追加 {self.val(b,'ITEM')}")
            elif op == "data_deleteoflist":
                out.append(f"{pre}列表[{self.nm(f.get('LIST'))}]删除第{self.val(b,'INDEX')}项")
            elif op == "data_deletealloflist":
                out.append(f"{pre}清空列表[{self.nm(f.get('LIST'))}]")
            elif op == "data_insertatlist":
                out.append(f"{pre}列表[{self.nm(f.get('LIST'))}]第{self.val(b,'INDEX')}项插入 {self.val(b,'ITEM')}")
            elif op == "data_replaceitemoflist":
                out.append(f"{pre}列表[{self.nm(f.get('LIST'))}]第{self.val(b,'INDEX')}项 = {self.val(b,'ITEM')}")
            elif op == "motion_gotoxy":
                out.append(f"{pre}移到 x={self.val(b,'X')} y={self.val(b,'Y')}")
            elif op == "motion_setx":
                out.append(f"{pre}x = {self.val(b,'X')}")
            elif op == "motion_sety":
                out.append(f"{pre}y = {self.val(b,'Y')}")
            elif op == "motion_changexby":
                out.append(f"{pre}x += {self.val(b,'DX')}")
            elif op == "motion_changeyby":
                out.append(f"{pre}y += {self.val(b,'DY')}")
            elif op == "motion_pointindirection":
                out.append(f"{pre}面向 {self.val(b,'DIRECTION')} 度")
            elif op == "motion_pointtowards":
                out.append(f"{pre}面向 {self.val(b,'TOWARDS')}")
            elif op == "looks_switchcostumeto":
                out.append(f"{pre}造型 = {self.val(b,'COSTUME')}")
            elif op == "looks_seteffectto":
                out.append(f"{pre}特效[{f.get('EFFECT')}] = {self.val(b,'VALUE')}")
            elif op == "looks_changeeffectby":
                out.append(f"{pre}特效[{f.get('EFFECT')}] += {self.val(b,'CHANGE')}")
            elif op == "looks_setsizeto":
                out.append(f"{pre}大小 = {self.val(b,'SIZE')}")
            elif op == "control_wait":
                out.append(f"{pre}等待 {self.val(b,'DURATION')} 秒")
            elif op == "control_create_clone_of":
                out.append(f"{pre}克隆 {self.val(b,'CLONE_OPTION')}")
            elif op == "control_stop":
                out.append(f"{pre}停止[{f.get('STOP_OPTION')}]")
            elif op == "sound_play":
                out.append(f"{pre}播放声音 {self.val(b,'SOUND_MENU')}")
            else:
                args = []
                for k in (b.get("inputs") or {}):
                    args.append(f"{k}={self.val(b,k)}")
                out.append(f"{pre}{op} {' '.join(args)} {json.dumps(f,ensure_ascii=False) if f else ''}")
            bid = b.get("next")
        return out


HATS = {"event_whenflagclicked", "event_whenbroadcastreceived", "event_whenkeypressed",
        "event_whenthisspriteclicked", "control_start_as_clone", "procedures_definition",
        "event_whenbackdropswitchesto", "event_whengreaterthan"}


def main():
    p = json.load(open(sys.argv[1], encoding="utf-8"))
    r = R(p)
    want = sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith("--") else None
    if "--stats" in sys.argv:
        c = Counter(b["opcode"] for b in r.bl.values() if isinstance(b, dict))
        for k, v in c.most_common():
            print(f"{v:5} {k}")
        return
    for t in p["targets"]:
        if want and t["name"] != want:
            continue
        bl = t.get("blocks") or {}
        heads = [b for b in bl.values() if isinstance(b, dict) and b["opcode"] in HATS]
        print(f"\n===== {t['name']} ({len(bl)} 块 / {len(heads)} 段脚本) =====")
        print("  造型:", [c["name"] for c in t.get("costumes") or []][:12],
              "..." if len(t.get("costumes") or []) > 12 else "")
        print("  声音:", [s["name"] for s in t.get("sounds") or []])
        if t.get("variables"):
            print("  局部变量:", [v[0] for v in t["variables"].values()])
        if t.get("lists"):
            print("  局部列表:", [v[0] for v in t["lists"].values()])
        for h in heads:
            op = h["opcode"]
            f = h.get("fields") or {}
            if op == "procedures_definition":
                proto = r.bl[h["inputs"]["custom_block"][1]]
                head = "【定义】" + proto.get("mutation", {}).get("proccode", "?")
            elif op == "event_whenbroadcastreceived":
                head = f"当收到广播[{r.nm(f.get('BROADCAST_OPTION'))}]"
            elif op == "event_whenkeypressed":
                head = f"当按下[{f.get('KEY_OPTION')}]"
            elif op == "control_start_as_clone":
                head = "当作为克隆体启动"
            elif op == "event_whenflagclicked":
                head = "当绿旗被点击"
            elif op == "event_whenthisspriteclicked":
                head = "当角色被点击"
            else:
                head = op
            print(f"\n  --- {head}")
            body = h.get("next")
            if op == "procedures_definition" and h["inputs"].get("custom_block"):
                # 定义体在 next
                pass
            for line in r.stmt(body, 2) or []:
                print(line)


if __name__ == "__main__":
    main()
