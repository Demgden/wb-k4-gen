#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sb3_to_bcm4.py — 把 Scratch 3 工程（.sb3 解包后的 project.json + 素材）转成 .bcm4。

设计取舍：
  * 画布用 480×360（与 Scratch 舞台同尺寸），所有坐标 / 数值字面量 **原样不动**，
    物理常数（速度、重力、插值系数）不需要按比例换算，最大程度保真。
  * Scratch 的 PNG 造型都是 2 倍图（bitmapResolution=2），统一缩到 1 倍存进去，
    这样像素尺寸与 Scratch 一致；旋转中心 rc 本来就以「造型单位」计，直接用。
  * 结构表 block_struct.json 缺的积木类型在本脚本 STRUCT_EXTRA 里补；
    值槽的 phantom shadow 由 repair_shadows() 统一补齐（规则 3）。

用法:
  python sb3_to_bcm4.py <sb3目录> <输出.bcm4> [--no-audio] [--report report.json]
"""
import argparse
import base64
import io
import json
import os
import re
import sys
import uuid
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import bcm4_build as B  # noqa: E402
from bcm4_json import dumps as js_dumps  # noqa: E402

NS = uuid.UUID("6f9619ff-8b86-d011-b42d-00c04fc964ff")
XML = 'xmlns="http://www.w3.org/1999/xhtml"'

# ---------------------------------------------------------------- 补结构表
STRUCT_EXTRA = {
    "procedures_2_defnoreturn": {"output": False, "prev": False, "next": False, "inputs": []},
    "procedures_2_callnoreturn": {"output": False, "prev": True, "next": True, "inputs": []},
    "procedures_2_callreturn": {"output": True, "prev": False, "next": False, "inputs": []},
    "procedures_2_parameter": {"output": True, "prev": False, "next": False, "inputs": []},
    "procedures_2_stable_parameter": {"output": True, "prev": False, "next": False, "inputs": []},
    # k4 自带「返回」积木：自制积木体内的「停止当前脚本」应该用它，而不是 stop
    "procedures_2_return_value": {"output": False, "prev": True, "next": True, "inputs": []},
    "bump": {"output": True, "prev": False, "next": False, "inputs": []},
    "math_trig": {"output": True, "prev": False, "next": False,
                  "inputs": [{"name": "OP", "kind": "field_dropdown"},
                             {"name": "NUM", "kind": "value"}]},
}
for _k, _v in STRUCT_EXTRA.items():
    B.STRUCT.setdefault(_k, _v)

HATS = {
    "event_whenflagclicked", "event_whenbroadcastreceived", "event_whenkeypressed",
    "event_whenthisspriteclicked", "control_start_as_clone", "procedures_definition",
    "event_whenbackdropswitchesto", "event_whengreaterthan",
}
# 这些 opcode 只是下拉菜单，本身不是积木
MENUS = {
    "looks_costume", "sound_sounds_menu", "control_create_clone_of_menu",
    "sensing_keyoptions", "sensing_touchingobjectmenu", "sensing_of_object_menu",
    "motion_goto_menu", "motion_pointtowards_menu", "sensing_distancetomenu",
    "event_broadcast_menu", "argument_reporter_string_number",
}

KEYS = {
    "space": "32", "left arrow": "37", "up arrow": "38", "right arrow": "39",
    "down arrow": "40", "enter": "13", "any": "any",
}
for _c in "abcdefghijklmnopqrstuvwxyz":
    KEYS[_c] = str(ord(_c.upper()))
for _c in "0123456789":
    KEYS[_c] = str(ord(_c))

EFFECT = {"COLOR": "0", "GHOST": "1", "BRIGHTNESS": "2", "PIXELATE": "3",
          "FISHEYE": "5", "WHIRL": "5", "MOSAIC": "7"}
ATTR = {"x position": "0", "y position": "1", "costume #": "2", "direction": "3",
        "costume name": "4", "size": "5", "volume": "6"}
MATHOP = {
    "abs": ("math_single", "ABS"), "floor": ("math_round", "ROUNDDOWN"),
    "ceiling": ("math_round", "ROUNDUP"), "sqrt": ("math_single", "ROOT"),
    "sin": ("math_trig", "SIN"), "cos": ("math_trig", "COS"), "tan": ("math_trig", "TAN"),
    "asin": ("math_trig", "ASIN"), "acos": ("math_trig", "ACOS"), "atan": ("math_trig", "ATAN"),
    "ln": ("math_single", "LN"), "log": ("math_single", "LOG10"),
    "e ^": ("math_single", "EXP"), "10 ^": ("math_single", "POW10"),
}
ARITH = {"operator_add": "ADD", "operator_subtract": "MINUS",
         "operator_multiply": "MULTIPLY", "operator_divide": "DIVIDE"}
CMP = {"operator_equals": "EQ", "operator_lt": "LT", "operator_gt": "GT"}


def uid(tag):
    return str(uuid.uuid5(NS, tag))


def num_or_text(s):
    """Scratch 的数字字面量是字符串，能转数字就转（与 kitten default_value 语义一致）"""
    try:
        f = float(s)
    except (TypeError, ValueError):
        return s
    if f == int(f) and abs(f) < 1e15:
        return int(f)
    return f


class Conv:
    def __init__(self, sb3dir, out, keep_audio=True):
        self.dir = sb3dir
        self.out = out
        self.keep_audio = keep_audio
        with open(os.path.join(sb3dir, "project.json"), encoding="utf-8") as f:
            self.p = json.load(f)
        self.targets = {t["name"]: t for t in self.p["targets"]}
        self.stage = next(t for t in self.p["targets"] if t["isStage"])
        self.unmapped = Counter()
        self.warnings = []
        self.empties = []
        self.style_of = {}       # (target, costume name) -> style uuid
        self.varmap = {}         # (target, scratch var id) -> uuid
        self.procs = {}          # target -> {proccode: (base_name, argnames, def_uuid)}
        self.proc_name_used = {}  # 全局自定义积木名占用表（k4 是作品级共享）
        self.cur = {}
        self.cur_target = None
        self.cur_actor = None
        self.in_proc = False
        self.B = None
        self.blocks = {}
        self.conns = {}
        self._build_env()

    # ------------------------------------------------------------ 信封
    def _build_env(self):
        env_path = os.path.join(HERE, "..", "envelopes", "空白作品.bcm4")
        with open(env_path, encoding="utf-8") as f:
            env = json.load(f)
        env["project_name"] = "Getting Over It"
        env["size"] = {"width": 480, "height": 360}
        env["variables"] = {}
        env["variable_order"] = []
        env["audio"] = {}
        env["audio_order"] = []
        env["broadcasts"] = {}
        th = env["theatre"]
        th["actors"] = {}
        th["groups"] = {}
        th["videos"] = {}
        th["timer"] = {}
        # 场景：复用空白场景那一条，造型稍后覆盖
        sid = th["scenes_order"][0]
        sc = th["scenes"][sid]
        sc["name"] = "背景"
        sc["styles"] = []
        sc["current_style_id"] = ""
        sc["group_order"] = []
        sc["actors"] = []
        for k in list(th["styles"]):
            if k != "ae8bcd36-25d3-4ea4-b907-38d4ccf4621b":
                del th["styles"][k]
        self.scene_id = sid
        self.scene = sc
        self.proj = env

    # ------------------------------------------------------------ 素材
    def _asset_url(self, rec):
        path = os.path.join(self.dir, rec["md5ext"])
        fmt = (rec.get("dataFormat") or "").lower()
        raw = open(path, "rb").read()
        if fmt in ("jpg", "jpeg"):
            mime = "image/jpeg"
        elif fmt == "wav":
            mime = "audio/wav"
        elif fmt == "mp3":
            mime = "audio/mpeg"
        elif fmt == "ogg":
            mime = "audio/ogg"
        else:
            mime = "application/octet-stream"
        return "data:%s;base64,%s" % (mime, base64.b64encode(raw).decode("ascii"))

    def _costume_raw(self, cos):
        """造型素材 → (原始字节, 宽, 高, mime)，尺寸一律取**自然显示尺寸**。

        实测（真实编辑器 + get_canvas_screenshot 标定）：k4 画角色造型是
        「1 纹理像素 = 1 舞台单位」，跟 Scratch 的自然尺寸完全一致，
        所以这里既不能放大也不能缩。get_canvas_screenshot 输出的是半个舞台
        （舞台只占画面中央 240x180），别被它误导成 0.5 倍。
          * SVG → width/height 原样
          * bitmapResolution=2 的位图 → 缩到一半才是自然尺寸
          * bitmapResolution=1 的位图 → 原样
        """
        path = os.path.join(self.dir, cos["md5ext"])
        fmt = (cos.get("dataFormat") or "").lower()
        res = int(cos.get("bitmapResolution") or 1) or 1
        raw = open(path, "rb").read()
        if fmt == "svg":
            b, w, h = self._scale_svg(raw, 1.0)
            return b, w, h, "image/svg+xml"
        if fmt in ("png", "jpg", "jpeg"):
            out, w, h = self._resize_bitmap(raw, 1.0 / res)
            return out, w, h, ("image/png" if fmt == "png" else "image/jpeg")
        return raw, 0, 0, "application/octet-stream"

    # ------------------------------------------------------------ 空图兜底
    _DRAW_RE = re.compile(
        r"<(path|rect|circle|ellipse|polygon|polyline|line|image|text|use|foreignObject)\b")

    @staticmethod
    def _png_transparent(w=32, h=32):
        """生成一张合法的透明 PNG（k4 遇到“空造型”会整只角色加载失败）"""
        import struct
        import zlib
        w, h = max(1, int(w)), max(1, int(h))
        raw = b"".join(b"\x00" + b"\x00\x00\x00\x00" * w for _ in range(h))

        def chunk(tag, data):
            body = tag + data
            return (struct.pack(">I", len(data)) + body
                    + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF))

        ihdr = struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)
        return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
                + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))

    def _image_is_empty(self, raw, mime):
        """素材里没有真正画出东西 → True

        * SVG：去掉 defs/title/desc/style 后没有任何绘制元素
        * 位图：逐像素看 alpha 是否全 0（不能按字节数判断 —— 纯白/纯黑的
          480x360 图压完只有一两百字节，会被误判成空图）
        """
        if not raw:
            return True
        if mime == "image/svg+xml":
            txt = raw.decode("utf-8", errors="replace")
            body = re.sub(r"<(defs|title|desc|style)\b.*?</\1>", "", txt, flags=re.S)
            return not self._DRAW_RE.search(body)
        if mime.startswith("image/"):
            try:
                from PIL import Image
                im = Image.open(io.BytesIO(raw))
                if im.mode not in ("RGBA", "LA", "P", "PA", "RGB", "L"):
                    return False
                if im.mode in ("RGB", "L"):
                    return False
                return im.convert("RGBA").getchannel("A").getextrema() == (0, 0)
            except Exception:
                return False
        return False

    @classmethod
    def _blank_url(cls, w=32, h=32):
        return ("data:image/png;base64,"
                + base64.b64encode(cls._png_transparent(w, h)).decode("ascii"))

    @staticmethod
    def _resize_bitmap(raw, k):
        """按倍数缩放位图，返回 (字节, 宽, 高)。k=1 时原样返回。"""
        try:
            from PIL import Image
        except ImportError:
            import struct
            w, h = struct.unpack(">II", raw[16:24]) if raw[:8] == b"\x89PNG\r\n\x1a\n" else (0, 0)
            return raw, w, h
        im = Image.open(io.BytesIO(raw))
        w0, h0 = im.size
        tw, th = max(1, int(round(w0 * k))), max(1, int(round(h0 * k)))
        if (tw, th) == (w0, h0):
            return raw, w0, h0
        im = im.resize((tw, th), Image.LANCZOS)
        buf = io.BytesIO()
        # 不透明图转调色板（原 Scratch 素材多为此类），体积能压掉一个数量级
        try:
            opaque = im.mode in ("RGB", "L") or (
                im.mode in ("RGBA", "LA") and im.getchannel("A").getextrema() == (255, 255))
            if opaque:
                im.convert("RGB").convert("P", palette=Image.ADAPTIVE, colors=256).save(
                    buf, format="PNG", optimize=True)
            else:
                im.save(buf, format="PNG", optimize=True)
        except Exception:
            buf = io.BytesIO()
            im.save(buf, format="PNG", optimize=True)
        return buf.getvalue(), tw, th

    @staticmethod
    def _scale_svg(raw, k):
        """把 SVG 造型等比放大 k 倍，返回 (字节, 宽, 高)。

        Scratch 按 <svg width/height> 渲染造型；k4 画纹理时只按像素算，
        所以直接翻倍 width/height。没有 viewBox 的 SVG（Scratch 导出的
        hitbox 图常见）要补一个 viewBox，否则内容不会跟着放大。
        """
        s = raw.decode("utf-8", "replace")

        def fnum(v):
            try:
                return float(v)
            except (TypeError, ValueError):
                return None

        m = re.search(r"<svg\b[^>]*>", s)
        if not m:
            return raw, 0, 0
        tag = m.group(0)
        w = fnum((re.search(r'\bwidth="([\d.eE+-]+)(?:px)?"', tag) or [None, None])[1])
        h = fnum((re.search(r'\bheight="([\d.eE+-]+)(?:px)?"', tag) or [None, None])[1])
        vb = re.search(r'\bviewBox="([^"]+)"', tag)
        if vb:
            parts = [fnum(x) for x in re.split(r"[,\s]+", vb.group(1).strip()) if x]
            vw, vh = (parts[2], parts[3]) if len(parts) == 4 else (None, None)
        else:
            vw = vh = None
        if not w:
            w = vw
        if not h:
            h = vh
        if not w or not h:
            return raw, 0, 0
        if k == 1.0:
            return raw, w, h
        new = tag
        new = re.sub(r'\bwidth="[\d.eE+-]+(?:px)?"', 'width="%g"' % (w * k), new, count=1)
        new = re.sub(r'\bheight="[\d.eE+-]+(?:px)?"', 'height="%g"' % (h * k), new, count=1)
        if not vb:
            new = new[:-1] + ' viewBox="0 0 %g %g">' % (w, h)
        return (s.replace(tag, new, 1).encode("utf-8"), w * k, h * k)

    # ------------------------------------------------------------ 变量/广播
    def _build_vars(self):
        for t in self.p["targets"]:
            for vid, rec_v in (t.get("variables") or {}).items():
                name, val = rec_v[0], rec_v[1]
                k = uid("var:%s:%s" % (t["name"], vid))
                self.varmap[(t["name"], vid)] = k
                rec = {
                    "id": k, "type": "any", "is_global": bool(t["isStage"]),
                    "scale": 1, "theme": "pure", "name": name, "value": val,
                    "offset": {"x": 0, "y": 0},
                    "position": {"x": 0, "y": 0}, "visible": False,
                }
                if not t["isStage"]:
                    rec["current_entity"] = uid("actor:" + t["name"])
                self.proj["variables"][k] = rec
                self.proj["variable_order"].append(k)
            for lid, rec_l in (t.get("lists") or {}).items():
                name, val = rec_l[0], rec_l[1]
                k = uid("list:%s:%s" % (t["name"], lid))
                self.varmap[(t["name"], lid)] = k
                rec = {
                    "id": k, "type": "list", "is_global": bool(t["isStage"]),
                    "scale": 1, "theme": "common", "name": name,
                    "value": [v for v in (val or [])],
                    "offset": {"x": 0, "y": 0},
                    "position": {"x": 0, "y": 0}, "visible": False,
                }
                if not t["isStage"]:
                    rec["current_entity"] = uid("actor:" + t["name"])
                self.proj["variables"][k] = rec
                self.proj["variable_order"].append(k)

    def _build_broadcasts(self):
        """k4 的 broadcasts 是「实体 → 该实体可见的广播名列表」，不是「广播 → [名字]」。
        每个角色都有自己的命名空间，舞台单独一条，再加一条 toJSON:["Hi"]（新建作品的默认项，
        真实作品里都有）。列表给全集，保证任何下拉都能选到。"""
        names = set()
        for t in self.p["targets"]:
            for b in (t.get("blocks") or {}).values():
                if not isinstance(b, dict):
                    continue
                op = b["opcode"]
                f = b.get("fields") or {}
                if op == "event_whenbroadcastreceived":
                    v = f.get("BROADCAST_OPTION")
                    nm = v[0] if isinstance(v, list) else v
                    if nm:
                        names.add(str(nm))
                for k, v in (b.get("inputs") or {}).items():
                    if isinstance(v, list) and len(v) > 1 and isinstance(v[1], list) and v[1] and v[1][0] == 11:
                        if v[1][1]:
                            names.add(str(v[1][1]))
        self.bc_names = set(names)
        full = sorted(names)
        bc = self.proj["broadcasts"]
        bc["toJSON"] = ["Hi"]
        bc[self.scene_id] = (["Hi"] + [n for n in full if n != "Hi"])
        for t in self.p["targets"]:
            if t["isStage"]:
                continue
            bc[uid("actor:" + t["name"])] = (["Hi"] + [n for n in full if n != "Hi"])

    # ------------------------------------------------------------ 造型
    def _add_costumes(self, t, owner_rec):
        styles, cur = [], None
        for cos in t.get("costumes") or []:
            sid = uid("style:%s:%s" % (t["name"], cos["md5ext"] + ":" + cos["name"]))
            raw, w, h, mime = self._costume_raw(cos)
            res = int(cos.get("bitmapResolution") or 1) or 1
            # k4 的 rotate_center / pivot 是「相对造型中心」的偏移（真实作品里
            # florr 148/168、jelly car 8/10 张造型都是 0,0），单位是舞台单位
            # = 造型自然像素。Scratch 的 rotationCenter 是从左上角量的，
            # 所以要减掉自然尺寸的一半；位图还要先按 bitmapResolution 折回自然尺寸。
            rx = float(cos.get("rotationCenterX") or 0) / res - (w or 0) / 2.0
            ry = float(cos.get("rotationCenterY") or 0) / res - (h or 0) / 2.0
            # 空图（全透明位图、没有绘制内容的 SVG）k4 会加载失败，
            # 换一张同尺寸的透明 PNG，旋转中心才不会错位
            if self._image_is_empty(raw, mime):
                raw = self._png_transparent(w or 32, h or 32)
                mime = "image/png"
                self.empties.append("%s/%s" % (t["name"], cos.get("name")))
            url = "data:%s;base64,%s" % (mime, base64.b64encode(raw).decode("ascii"))
            st = {
                "id": sid, "name": cos["name"],
                "rotate_center": {"x": rx, "y": ry},
                "adaptive": True,
                "url": url, "cdn_url": "",
                "pivot": {"x": rx, "y": ry},
                "rotate_center_painter": {"x": rx, "y": ry},
            }
            self.proj["theatre"]["styles"][sid] = st
            styles.append(sid)
            self.style_of[(t["name"], cos["name"])] = sid
            cur = cur or sid
        # SB3 的 currentCostume 决定角色默认显示哪张造型（Player=player、Level=0x1x…），
        # 不能一律取第一张，否则编辑器/运行开始时是错的造型
        ci = t.get("currentCostume")
        if styles and isinstance(ci, int) and 0 <= ci < len(styles):
            cur = styles[ci]
        if not styles:
            # SB3 里没有造型的角色：k4 的 actor 必须有至少一个 style，否则整只角色加载失败
            sid = uid("style:%s:__blank" % t["name"])
            st = {
                "id": sid, "name": "空白",
                "rotate_center": {"x": 16, "y": 16}, "adaptive": True,
                "url": self._blank_url(32, 32),
                "cdn_url": "",
                "pivot": {"x": 16, "y": 16},
                "rotate_center_painter": {"x": 16, "y": 16},
            }
            self.proj["theatre"]["styles"][sid] = st
            styles.append(sid)
            self.style_of[(t["name"], "空白")] = sid
            cur = sid
            self.warnings.append("角色 %s 在 sb3 里没有造型，已补一张空白造型" % t["name"])
        owner_rec["styles"] = styles
        owner_rec["current_style_id"] = cur or ""
        return styles

    # ------------------------------------------------------------ 场景/角色
    def build_entities(self):
        self._build_vars()
        self._build_broadcasts()
        # 场景造型
        self._add_costumes(self.stage, self.scene)
        # 角色
        order = self.stage.get("layerOrder") or [i for i in range(len(self.p["targets"]))]
        by_index = list(self.p["targets"])
        lay = []
        for i in order:
            t = by_index[i] if isinstance(i, int) and i < len(by_index) else None
            if t is not None and not t["isStage"]:
                lay.append(t)
        for t in lay:
            aid = uid("actor:" + t["name"])
            actor = {
                "name": t["name"],
                "x": t.get("x", 0), "y": t.get("y", 0),
                "scale": t.get("size", 100),
                "rotation": 90 - float(t.get("direction", 90)),
                "rotation_type": {"all around": 0, "left-right": 1, "don't rotate": 2}.get(
                    t.get("rotationStyle"), 0),
                "id": aid,
                "draggable": bool(t.get("draggable")),
                "visible": t.get("visible", True),
                "lock": False, "user_change_r_c": False,
                "scene": self.scene_id,
                "editable_in_tuition_mode": True,
                "workspace_offset": {"x": 40, "y": 40},
                "block_data_json": {"blocks": {}, "connections": {}, "comments": {}},
            }
            self._add_costumes(t, actor)
            self.proj["theatre"]["actors"][aid] = actor
            gid = uid("group:" + t["name"])
            self.proj["theatre"]["groups"][gid] = {
                "id": gid, "name": "", "is_fold": False, "is_group": False,
                "actors": [aid], "scene": self.scene_id, "visible": True,
            }
            self.scene["group_order"].insert(0, gid)   # 铁律 4：数组开头=最上层

    # ------------------------------------------------------------ 音频
    def build_audio(self):
        if not self.keep_audio:
            return
        for t in self.p["targets"]:
            for s in t.get("sounds") or []:
                aid = uid("audio:%s:%s" % (t["name"], s["md5ext"]))
                url = self._asset_url(s)
                self.proj["audio"][aid] = {
                    "id": aid, "name": s["name"], "effects": [],
                    # sb3 的 rate 是采样率（48000），k4 的 playback_rate 是倍速，正常速度就是 1
                    "playback_rate": 1,
                    "volume": 1, "cdn_url": "", "url": url,
                }
                self.proj["audio_order"].append(aid)
                self.sound_id[(t["name"], s["name"])] = aid
        if self.proj["audio"]:
            self.proj["toolbox"]["audio"] = True

    # ------------------------------------------------------------ 表达式
    def _vget(self, name, vid):
        key = self.varmap.get((self.cur_target, vid))
        if key is None:
            # 可能是全局变量：按名字去全局里找
            for (tn, _), k in self.varmap.items():
                if tn == self.stage["name"] and self.proj["variables"][k]["name"] == name:
                    key = k
                    break
        if key is None:
            for k, v in self.proj["variables"].items():
                if v["name"] == name and v["type"] != "list":
                    key = k
                    break
        if key is None:
            self.warnings.append("变量找不到: %s" % name)
            key = uid("var:missing:" + str(name))
            self.proj["variables"][key] = {
                "id": key, "type": "any", "is_global": True, "scale": 1,
                "theme": "pure", "name": name, "value": 0, "offset": {"x": 0, "y": 0},
                "position": {"x": 0, "y": 0}, "visible": False}
        return key

    def _lget(self, name, lid):
        key = self.varmap.get((self.cur_target, lid))
        if key is None:
            for k, v in self.proj["variables"].items():
                if v["name"] == name and v["type"] == "list":
                    key = k
                    break
        if key is None:
            self.warnings.append("列表找不到: %s" % name)
            key = uid("list:missing:" + str(name))
            self.proj["variables"][key] = {
                "id": key, "type": "list", "is_global": True, "scale": 1,
                "theme": "common", "name": name, "value": [], "offset": {"x": 0, "y": 0},
                "position": {"x": 0, "y": 0}, "visible": False}
        return key

    def literal(self, prim):
        """Scratch 输入里的原语 [4,"0.5"] / [10,"abc"] / [11,name,id] / [12,..] / [13,..]"""
        code = prim[0]
        if code in (4, 5, 6, 7, 8, 9):
            return num_or_text(prim[1])
        if code == 10:
            return num_or_text(prim[1])      # "1" → 1：与 Scratch 的比较/运算一致
        if code == 11:
            return {"type": "broadcast_input", "fields": {"MESSAGE": prim[1]}}
        if code == 12:
            return {"type": "variables_get", "fields": {"VAR": self._vget(prim[1], prim[2])}}
        if code == 13:
            return {"type": "lists_get", "fields": {"VAR": self._lget(prim[1], prim[2])}}
        return str(prim[1])

    @staticmethod
    def to_angle(x):
        """Scratch 方向(0=上,顺时针+) → kitten 角度(0=右,逆时针+)。同一式子双向可逆。"""
        if isinstance(x, (int, float)):
            return 90 - x
        return {"type": "math_arithmetic", "fields": {"OP": "MINUS"},
                "inputs": {"A": 90, "B": x}}

    def arg(self, b, name, default=0):
        v = (b.get("inputs") or {}).get(name)
        if v is None:
            return default
        payload = v[1]
        if isinstance(payload, list):
            return self.literal(payload)
        if isinstance(payload, str):
            return self.expr(payload)
        return default

    def has_in(self, b, name):
        v = (b.get("inputs") or {}).get(name)
        return bool(v) and isinstance(v[1], str)

    def expr(self, bid):
        b = self.cur.get(bid)
        if not isinstance(b, dict):
            return 0
        spec = self.bspec(b)
        if spec is None:
            self.unmapped[b["opcode"]] += 1
            return {"type": "default_value", "fields": {"TEXT": ""}}
        return spec

    # ------------------------------------------------------------ 积木 → 规格
    @staticmethod
    def _norm_fields(b):
        out = {}
        for k, v in (b.get("fields") or {}).items():
            if isinstance(v, list) and len(v) == 2 and v[1] is None:
                v = v[0]
            out[k] = v
        return out

    @staticmethod
    def _var_pair(f, key):
        v = f.get(key)
        if isinstance(v, list):
            return v[0], v[1]
        return v, v

    def bspec(self, b):
        op = b["opcode"]
        f = self._norm_fields(b)
        A = self.arg

        # ---- 运动
        if op == "motion_movesteps":
            return {"type": "self_go_forward", "inputs": {"steps": A(b, "STEPS")}}
        if op in ("motion_turnright", "motion_turnleft"):
            d = A(b, "DEGREES")
            # kitten 角度逆时针为正：右转 = 减角度
            if op == "motion_turnright":
                d = {"type": "math_single", "fields": {"OP": "NEG"}, "inputs": {"NUM": d}}
            return {"type": "self_rotate", "inputs": {"degrees": d}}
        if op == "motion_gotoxy":
            return {"type": "self_move_to", "inputs": {"x": A(b, "X"), "y": A(b, "Y")}}
        if op == "motion_goto":
            tgt = self.menu_field(b, "TO")
            if tgt == "_mouse_":
                return {"type": "self_move_specify", "fields": {"target": "__pointer"}}
            return {"type": "self_move_specify", "fields": {"target": self.actor_ref(tgt)}}
        if op == "motion_setx":
            return {"type": "self_set_position", "fields": {"coordinary": "x"},
                    "inputs": {"value": A(b, "X")}}
        if op == "motion_sety":
            return {"type": "self_set_position", "fields": {"coordinary": "y"},
                    "inputs": {"value": A(b, "Y")}}
        if op == "motion_changexby":
            return {"type": "self_change_coordinate",
                    "fields": {"coordinary": "x", "increase": "increase"},
                    "inputs": {"value": A(b, "DX")}}
        if op == "motion_changeyby":
            return {"type": "self_change_coordinate",
                    "fields": {"coordinary": "y", "increase": "increase"},
                    "inputs": {"value": A(b, "DY")}}
        if op == "motion_pointindirection":
            return {"type": "self_point_towards",
                    "inputs": {"degrees": self.to_angle(A(b, "DIRECTION", 90))}}
        if op == "motion_pointtowards":
            tgt = self.menu_field(b, "TOWARDS")
            return {"type": "self_face_to", "fields": {"sprite": self.actor_ref(tgt)}}
        if op == "motion_xposition":
            return {"type": "get_3", "fields": {"sprite": "__self", "attribute": "0"}}
        if op == "motion_yposition":
            return {"type": "get_3", "fields": {"sprite": "__self", "attribute": "1"}}
        if op == "motion_direction":
            return self.to_angle({"type": "get_3",
                                  "fields": {"sprite": "__self", "attribute": "3"}})
        if op == "motion_setrotationstyle":
            return {"type": "self_set_rotation_type",
                    "fields": {"rotation_type": {"all around": "0", "left-right": "1",
                                                 "don't rotate": "2"}.get(f.get("STYLE"), "0")}}
        if op == "motion_glidesecstoxy":
            return {"type": "self_glide_to",
                    "inputs": {"x": A(b, "X"), "y": A(b, "Y"), "time": A(b, "SECS")}}

        # ---- 外观
        if op == "looks_switchcostumeto":
            v = (b.get("inputs") or {}).get("COSTUME")
            if v and isinstance(v[1], list):
                code = v[1][0]
                if code in (10, 11):          # 造型名
                    return self._costume_by_name(v[1])
                if code in (4, 5, 6, 7, 9):   # 造型号
                    return {"type": "set_costume_by_index",
                            "inputs": {"index": num_or_text(v[1][1])}}
                return self._costume_by_expr(self.literal(v[1]))
            if v and isinstance(v[1], str):
                blk = self.cur.get(v[1]) or {}
                if blk.get("opcode") == "looks_costume":
                    return self._costume_by_name(
                        [10, (blk.get("fields") or {}).get("COSTUME")])
                return self._costume_by_expr(self.expr(v[1]))
            return {"type": "self_prev_next_style", "fields": {"prev_or_next": "next"}}
        if op == "looks_nextcostume":
            return {"type": "self_prev_next_style", "fields": {"prev_or_next": "next"}}
        if op == "looks_show":
            return {"type": "self_appear"}
        if op == "looks_hide":
            return {"type": "self_disappear"}
        if op == "looks_setsizeto":
            return {"type": "set_scale", "inputs": {"scale": A(b, "SIZE", 100)}}
        if op == "looks_size":
            return {"type": "get_3", "fields": {"sprite": "__self", "attribute": "5"}}
        if op == "looks_costumenumbername":
            attr = "4" if f.get("NUMBER_NAME") == "name" else "2"
            return {"type": "get_3", "fields": {"sprite": "__self", "attribute": attr}}
        if op == "looks_seteffectto":
            return {"type": "self_set_effect_2",
                    "fields": {"scope": EFFECT.get(f.get("EFFECT"), "1")},
                    "inputs": {"val": A(b, "VALUE")}}
        if op == "looks_changeeffectby":
            return {"type": "self_change_effect_3",
                    "fields": {"scope": EFFECT.get(f.get("EFFECT"), "1"),
                               "increase": "increase"},
                    "inputs": {"steps": A(b, "CHANGE")}}
        if op == "looks_cleargraphiceffects":
            return {"type": "self_clear_effects"}
        if op == "looks_gotofrontback":
            return {"type": "set_theatre_layer",
                    "fields": {"layer": "peak" if f.get("FRONT_BACK") == "front" else "bottom"}}
        if op == "looks_goforwardbackwardlayers":
            n = A(b, "NUM")
            if f.get("FORWARD_BACKWARD") == "backward":
                n = {"type": "math_single", "fields": {"OP": "NEG"}, "inputs": {"NUM": n}}
            return {"type": "self_change_layer", "inputs": {"n": n}}

        # ---- 事件（发送广播）
        if op in ("event_broadcast", "event_broadcastandwait"):
            nm = self.menu_field(b, "BROADCAST_INPUT")
            if isinstance(nm, list):
                nm = nm[0]
            kind = "self_broadcast" if op == "event_broadcast" else "self_broadcast_and_wait"
            return {"type": kind,
                    "inputs": {"message": {"type": "broadcast_input",
                                           "fields": {"MESSAGE": nm}}}}

        # ---- 声音
        # 运行时的音频解析器（kitten.js play_audio_2 → m(e)）支持三种入参：
        # "all"、序号、**音频名/音频 id 字符串**。所以声音名是表达式时可以直接把
        # 表达式塞进 audio 槽，不需要先查表换算。
        if op in ("sound_play", "sound_playuntildone"):
            kind = "play_audio_2" if op == "sound_play" else "play_audio_and_wait_2"
            return {"type": kind, "inputs": {"audio": self._audio_ref(b)}}
        if op in ("sound_setvolumeto", "sound_seteffectto",
                  "sound_changevolumeby", "sound_changeeffectby"):
            return self._sound_attr(b, op)
        if op == "sound_cleareffects":
            return None
        if op == "sound_stopallsounds":
            return {"type": "stop_all_audios"}

        # ---- 控制
        if op == "control_wait":
            return {"type": "wait", "inputs": {"time": A(b, "DURATION")}}
        if op == "control_repeat":
            return {"type": "repeat_n_times", "inputs": {"times": A(b, "TIMES", 10)},
                    "body": {"DO": self.sub(b, "SUBSTACK")}}
        if op == "control_forever":
            return {"type": "repeat_forever", "body": {"DO": self.sub(b, "SUBSTACK")}}
        if op == "control_repeat_until":
            return {"type": "repeat_forever_until",
                    "inputs": {"condition": A(b, "CONDITION", {"type": "logic_empty"})},
                    "body": {"DO": self.sub(b, "SUBSTACK")}}
        if op == "control_while":
            return {"type": "repeat_forever_until",
                    "inputs": {"condition": {"type": "logic_negate",
                                             "inputs": {"BOOL": A(b, "CONDITION")}}},
                    "body": {"DO": self.sub(b, "SUBSTACK")}}
        if op == "control_if":
            return {"type": "controls_if",
                    "inputs": {"IF0": A(b, "CONDITION", {"type": "logic_empty"})},
                    "body": {"DO0": self.sub(b, "SUBSTACK")}}
        if op == "control_if_else":
            return {"type": "controls_if",
                    "inputs": {"IF0": A(b, "CONDITION", {"type": "logic_empty"})},
                    "body": {"DO0": self.sub(b, "SUBSTACK"), "ELSE": self.sub(b, "SUBSTACK2")}}
        if op == "control_wait_until":
            return {"type": "wait_until",
                    "inputs": {"condition": A(b, "CONDITION", {"type": "logic_empty"})}}
        if op == "control_stop":
            if self.in_proc and f.get("STOP_OPTION") == "this script":
                # Scratch 的「停止当前脚本」在自制积木里就是「返回」。
                # k4 有专门的 return 积木，用它才不会连带中断调用方。
                return {"type": "procedures_2_return_value",
                        "mutation": '<mutation %s items="0"></mutation>' % XML,
                        "drop_shadows": ["VALUE"],
                        "empty_shadows": ["PROCEDURES_2_DEFRETURN_RETURN",
                                          "PROCEDURES_2_DEFRETURN_RETURN_MUTATOR"]}
            return {"type": "stop", "fields": {"scope": {"all": "0", "this script": "1",
                                                         "other scripts in sprite": "2"}.get(
                f.get("STOP_OPTION"), "0")}}
        if op == "control_create_clone_of":
            tgt = self.menu_field(b, "CLONE_OPTION")
            # "克隆自己" = mirror（下拉选角色，与 Scratch 的 create clone of 语义一致）；
            # clone 是「分裂」，会额外要 x/y 且行为不同，别用。
            sprite = "__self" if tgt in ("_myself_", None) else self.actor_ref(tgt)
            return {"type": "mirror", "fields": {"sprite": sprite}}
        if op == "control_delete_this_clone":
            return {"type": "dispose_clone"}

        # ---- 侦测
        if op == "sensing_keypressed":
            key = self.menu_field(b, "KEY_OPTION")
            return {"type": "check_key",
                    "fields": {"key_event_type": "down", "key": KEYS.get(str(key), "any")}}
        if op == "sensing_mousex":
            return {"type": "get_mouse_info", "fields": {"position": "x"}}
        if op == "sensing_mousey":
            return {"type": "get_mouse_info", "fields": {"position": "y"}}
        if op == "sensing_mousedown":
            return {"type": "mouse_down", "fields": {"mouse_event_type": "down"}}
        if op == "sensing_timer":
            return {"type": "get_timer"}
        if op == "sensing_resettimer":
            return {"type": "reset_timer"}
        if op == "sensing_username":
            return {"type": "username_get"}
        if op == "sensing_touchingobject":
            tgt = self.menu_field(b, "TOUCHINGOBJECTMENU")
            if tgt == "_edge_":
                return {"type": "self_out_of_boundary", "fields": {"boundary": "0"}}  # 0=整个边界
            if tgt == "_mouse_":
                return {"type": "bump", "fields": {"sprite1": "__self", "sprite2": "__mouse"}}
            return {"type": "bump",
                    "fields": {"sprite1": "__self", "sprite2": self.actor_ref(tgt)}}
        if op == "sensing_distanceto":
            tgt = self.menu_field(b, "DISTANCETOMENU")
            return {"type": "self_distance_to",
                    "fields": {"sprite": "__mouse" if tgt == "_mouse_" else self.actor_ref(tgt)}}
        if op == "sensing_of":
            obj = self.menu_field(b, "OBJECT")
            prop = f.get("PROPERTY")
            if obj == "_stage_":
                k = None
                for kk, v in self.proj["variables"].items():
                    if v["name"] == prop and v["type"] != "list":
                        k = kk
                        break
                return {"type": "variables_get", "fields": {"VAR": k or prop}}
            if prop == "direction":
                return self.to_angle({"type": "get_3",
                                      "fields": {"sprite": self.actor_ref(obj),
                                                 "attribute": "3"}})
            return {"type": "get_3", "fields": {"sprite": self.actor_ref(obj),
                                                "attribute": ATTR.get(prop, "0")}}

        # ---- 运算
        if op in ARITH:
            return {"type": "math_arithmetic", "fields": {"OP": ARITH[op]},
                    "inputs": {"A": A(b, "NUM1"), "B": A(b, "NUM2")}}
        if op in CMP:
            return {"type": "logic_compare", "fields": {"OP": CMP[op]},
                    "inputs": {"A": A(b, "OPERAND1"), "B": A(b, "OPERAND2")}}
        if op in ("operator_and", "operator_or"):
            return {"type": "logic_operation",
                    "fields": {"OP": "AND" if op == "operator_and" else "OR"},
                    "inputs": {"A": A(b, "OPERAND1"), "B": A(b, "OPERAND2")}}
        if op == "operator_not":
            return {"type": "logic_negate", "inputs": {"BOOL": A(b, "OPERAND")}}
        if op == "operator_join":
            return {"type": "text_join", "mutation": '<mutation %s items="2"></mutation>' % XML,
                    "inputs": {"ADD0": A(b, "STRING1", ""), "ADD1": A(b, "STRING2", "")}}
        if op == "operator_letter_of":
            n = A(b, "LETTER", 1)
            return {"type": "text_select",
                    "inputs": {"string": A(b, "STRING", ""),
                               "char_start_index": n, "char_end_index": n}}
        if op == "operator_length":
            return {"type": "text_length", "inputs": {"VALUE": A(b, "STRING", "")}}
        if op == "operator_contains":
            return {"type": "text_contain",
                    "inputs": {"TEXT1": A(b, "STRING1", ""), "TEXT2": A(b, "STRING2", "")}}
        if op == "operator_random":
            return {"type": "random", "inputs": {"a": A(b, "FROM", 1), "b": A(b, "TO", 10)}}
        if op == "operator_mod":
            return {"type": "math_modulo",
                    "inputs": {"DIVIDEND": A(b, "NUM1"), "DIVISOR": A(b, "NUM2")}}
        if op == "operator_round":
            return {"type": "math_round", "fields": {"OP": "ROUND"},
                    "inputs": {"NUM": A(b, "NUM")}}
        if op == "operator_mathop":
            kind, code = MATHOP.get(f.get("OPERATOR"), ("math_single", "ABS"))
            return {"type": kind, "fields": {"OP": code}, "inputs": {"NUM": A(b, "NUM")}}

        # ---- 变量/列表
        if op == "data_setvariableto":
            return {"type": "variables_set",
                    "fields": {"VAR": self._vget(*self._var_pair(f, "VARIABLE"))},
                    "inputs": {"VALUE": A(b, "VALUE", "")}}
        if op == "data_changevariableby":
            v = A(b, "VALUE", 1)
            method = "increase"
            if isinstance(v, (int, float)) and v < 0:
                method, v = "decrease", abs(v)
            return {"type": "change_variable",
                    "fields": {"valname": self._vget(*self._var_pair(f, "VARIABLE")),
                               "method": method},
                    "inputs": {"n": v}}
        if op == "data_showvariable":
            return {"type": "show_hide_variable",
                    "fields": {"FUNC": "show",
                               "VAR": self._vget(*self._var_pair(f, "VARIABLE"))}}
        if op == "data_hidevariable":
            return {"type": "show_hide_variable",
                    "fields": {"FUNC": "hide",
                               "VAR": self._vget(*self._var_pair(f, "VARIABLE"))}}
        if op == "data_showlist":
            return {"type": "show_hide_list",
                    "fields": {"FUNC": "show", "VAR": self._lget(*self._var_pair(f, "LIST"))}}
        if op == "data_hidelist":
            return {"type": "show_hide_list",
                    "fields": {"FUNC": "hide", "VAR": self._lget(*self._var_pair(f, "LIST"))}}
        if op == "data_addtolist":
            return {"type": "lists_append",
                    "inputs": {"VAR": {"type": "lists_get",
                                       "fields": {"VAR": self._lget(*self._var_pair(f, "LIST"))}},
                               "VALUE": A(b, "ITEM", "")}}
        if op == "data_deletealloflist":
            return {"type": "lists_delete",
                    "fields": {"TYPE": "all"},
                    "inputs": {"VAR": {"type": "lists_get",
                                       "fields": {"VAR": self._lget(*self._var_pair(f, "LIST"))}}}}
        if op in ("data_deleteoflist", "data_itemoflist"):
            lid = self._lget(*self._var_pair(f, "LIST"))
            idx = (b.get("inputs") or {}).get("INDEX")
            lit = None
            if idx and isinstance(idx[1], list):
                lit = str(idx[1][1])
            if op == "data_deleteoflist":
                if lit == "all":
                    return {"type": "lists_delete", "fields": {"TYPE": "all"},
                            "inputs": {"VAR": {"type": "lists_get", "fields": {"VAR": lid}}}}
                if lit == "last":
                    return {"type": "lists_delete", "fields": {"TYPE": "last"},
                            "inputs": {"VAR": {"type": "lists_get", "fields": {"VAR": lid}}}}
                return {"type": "lists_delete", "fields": {"TYPE": "first"},
                        "inputs": {"VAR": {"type": "lists_get", "fields": {"VAR": lid}},
                                   "INDEX": A(b, "INDEX", 1)}}
            if lit == "last":
                return {"type": "lists_get_value", "fields": {"TYPE": "last"},
                        "inputs": {"VAR": {"type": "lists_get", "fields": {"VAR": lid}}}}
            return {"type": "lists_get_value", "fields": {"TYPE": "first"},
                    "inputs": {"VAR": {"type": "lists_get", "fields": {"VAR": lid}},
                               "INDEX": A(b, "INDEX", 1)}}
        if op == "data_insertatlist":
            lid = self._lget(*self._var_pair(f, "LIST"))
            idx = (b.get("inputs") or {}).get("INDEX")
            lit = str(idx[1][1]) if idx and isinstance(idx[1], list) else None
            if lit == "last":
                return {"type": "lists_append",
                        "inputs": {"VAR": {"type": "lists_get", "fields": {"VAR": lid}},
                                   "VALUE": A(b, "ITEM", "")}}
            return {"type": "lists_insert_value",
                    "inputs": {"VAR": {"type": "lists_get", "fields": {"VAR": lid}},
                               "INDEX": A(b, "INDEX", 1), "VALUE": A(b, "ITEM", "")}}
        if op == "data_replaceitemoflist":
            lid = self._lget(*self._var_pair(f, "LIST"))
            idx = (b.get("inputs") or {}).get("INDEX")
            lit = str(idx[1][1]) if idx and isinstance(idx[1], list) else None
            if lit == "last":
                return {"type": "lists_replace", "fields": {"TYPE": "last"},
                        "inputs": {"VAR": {"type": "lists_get", "fields": {"VAR": lid}},
                                   "VALUE": A(b, "ITEM", "")}}
            return {"type": "lists_replace", "fields": {"TYPE": "first"},
                    "inputs": {"VAR": {"type": "lists_get", "fields": {"VAR": lid}},
                               "INDEX": A(b, "INDEX", 1), "VALUE": A(b, "ITEM", "")}}
        if op == "data_lengthoflist":
            return {"type": "lists_length",
                    "inputs": {"VAR": {"type": "lists_get",
                                       "fields": {"VAR": self._lget(*self._var_pair(f, "LIST"))}}}}
        if op == "data_itemnumoflist":
            return {"type": "lists_index_of",
                    "inputs": {"VAR": {"type": "lists_get",
                                       "fields": {"VAR": self._lget(*self._var_pair(f, "LIST"))}},
                               "VALUE": A(b, "ITEM", "")}}
        if op == "data_listcontainsitem":
            return {"type": "lists_is_exist",
                    "inputs": {"VAR": {"type": "lists_get",
                                       "fields": {"VAR": self._lget(*self._var_pair(f, "LIST"))}},
                               "VALUE": A(b, "ITEM", "")}}
        if op == "data_itemoflist":
            return None

        # ---- 过程
        if op == "procedures_call":
            return self._proc_call(b)
        if op in ("argument_reporter_string_number", "argument_reporter_boolean"):
            name = f.get("VALUE")
            if isinstance(name, list):
                name = name[0]
            return {"type": "procedures_2_parameter", "fields": {"param_name": str(name)}}

        if op in MENUS:
            return None
        return None

    # ------------------------------------------------------------ 辅助
    def menu_field(self, b, slot):
        v = (b.get("inputs") or {}).get(slot)
        if not v:
            return None
        if isinstance(v[1], list):
            return v[1][1] if len(v[1]) > 1 else None
        blk = self.cur.get(v[1])
        if isinstance(blk, dict):
            f = self._norm_fields(blk)
            if f:
                val = list(f.values())[0]
                return val[0] if isinstance(val, list) else val
        return None

    def actor_ref(self, name):
        if isinstance(name, list):
            name = name[0]
        if name in (None, "", "_myself_"):
            return "__self"
        if name == "_mouse_":
            return "__mouse"
        if name in self.targets:
            return uid("actor:" + name)
        return "__self"

    def _costume_by_expr(self, expr):
        """按「造型名」动态切换：Scratch 允许 switch costume to (变量)，
        kitten 只能按序号，所以在角色里塞一张「造型名表」用 index_of 换算。"""
        lid = self._style_name_list()
        return {"type": "set_costume_by_index",
                "inputs": {"index": {
                    "type": "lists_index_of",
                    "inputs": {"VAR": {"type": "lists_get", "fields": {"VAR": lid}},
                               "VALUE": expr}}}}

    def _style_name_list(self):
        key = uid("list:%s:__stylenames" % self.cur_target)
        if key in self.proj["variables"]:
            return key
        names = [c["name"] for c in (self.targets[self.cur_target].get("costumes") or [])]
        self.proj["variables"][key] = {
            "id": key, "type": "list", "is_global": False, "scale": 1,
            "theme": "common", "name": "造型名表", "value": names,
            "offset": {"x": 0, "y": 0}, "position": {"x": 0, "y": 0},
            "visible": False, "current_entity": uid("actor:" + self.cur_target)}
        self.proj["variable_order"].append(key)
        return key

    def _costume_by_name(self, prim):
        name = prim[1] if len(prim) > 1 else ""
        if isinstance(name, list):
            name = name[0]
        sid = self.style_of.get((self.cur_target, str(name)))
        if sid:
            # k4 4.11.20 里 set_costume_by_id 是废弃块：init 时 jsonInit 会抛
            # "Message does not reference all 1 arg(s)"，整个角色工作区直接空掉。
            # 正确写法是 set_costume + get_current_costume 下拉影子（带 style_id）。
            return {"type": "set_costume",
                    "inputs": {"index": {"type": "get_current_costume",
                                         "fields": {"style_id": sid},
                                         "shadow": True}}}
        # 数字造型号
        try:
            return {"type": "set_costume_by_index", "inputs": {"index": int(float(name))}}
        except (TypeError, ValueError):
            self.warnings.append("造型找不到: %s / %s" % (self.cur_target, name))
            return {"type": "self_prev_next_style", "fields": {"prev_or_next": "next"}}

    def _sound_id(self, b, slot):
        name = self.menu_field(b, slot)
        sid = self.sound_id.get((self.cur_target, str(name)))
        if sid is not None:
            return sid
        for (tn, sn), v in self.sound_id.items():
            if sn == name:
                return v
        # 菜单空掉（老 sb3 / 被删的声音）时用本角色第一条音频兜底，
        # 别把 None 当音频 id 写进 get_audios，否则那个下拉是空的
        for (tn, sn), v in self.sound_id.items():
            if tn == self.cur_target:
                return v
        return None

    def _audio_ref(self, b):
        """声音槽 → 表达式。菜单内联字面量走 get_audios(id)（精确到本条音频），
        接到块（变量/拼接）时直接把名字表达式塞进去，运行时按名字解析。"""
        v = (b.get("inputs") or {}).get("SOUND_MENU")
        if v and isinstance(v[1], str):
            blk = self.cur.get(v[1]) or {}
            if blk.get("opcode") != "sound_sounds_menu":
                return self.expr(v[1])          # 动态名字
        sid = self._sound_id(b, "SOUND_MENU")
        if sid:
            return {"type": "get_audios", "fields": {"sound_id": sid}}
        nm = self.menu_field(b, "SOUND_MENU")
        self.unmapped["声音找不到:" + str(nm)] += 1
        return {"type": "text", "fields": {"TEXT": str(nm or "")}}

    def _sound_attr(self, b, op):
        """音量/PITCH 在 Scratch 里是「整只角色的声音」；kitten 是逐条音频，
        因此只在角色只有一条音频时精确映射，多条时跳过并记账。"""
        ids = [v for (tn, sn), v in self.sound_id.items() if tn == self.cur_target]
        key, chg = "volume", op.startswith("sound_change")
        if op.endswith("effectto") or op.endswith("effectby"):
            key = "rate"
            eff = self._norm_fields(b).get("EFFECT")
            if eff != "PITCH":
                self.unmapped["音效 PAN"] += 1
                return None
        if len(ids) != 1:
            # Scratch 的音量/音高是「整只角色」；k4 是逐条音频。
            # 给每条音频都设一遍，效果等价（不丢功能）
            if not ids:
                self.unmapped["音量(无音频角色):%s" % self.cur_target] += 1
                return None
            val = self.arg(b, "VOLUME" if "VOLUME" in (b.get("inputs") or {}) else "VALUE")
            out = []
            for aid in ids:
                sp = {"type": "change_volume_or_rate_2" if chg else "set_volume_or_rate_2",
                      "fields": {"audio_key": key, "increase": "increase"} if chg
                                else {"audio_key": key},
                      "inputs": {"audio": {"type": "get_audios", "fields": {"sound_id": aid}},
                                 "audio_value": val}}
                out.append(sp)
            return out
        val = self.arg(b, "VOLUME" if "VOLUME" in (b.get("inputs") or {}) else "VALUE")
        spec = {"type": "change_volume_or_rate_2" if chg else "set_volume_or_rate_2",
                "fields": {"audio_key": key},
                "inputs": {"audio": {"type": "get_audios", "fields": {"sound_id": ids[0]}},
                           "audio_value": val}}
        if chg:
            spec["fields"]["increase"] = "increase"
        return spec

    def _proc_call(self, b):
        mut = b.get("mutation") or {}
        proccode = mut.get("proccode") or ""
        info = self.procs.get(self.cur_target, {}).get(proccode)
        if info is None:
            self.unmapped["procedures_call(未定义):" + proccode] += 1
            return None
        base, argnames, def_id = info
        argids = json.loads(mut.get("argumentids") or "[]")
        ins = {}
        mut_xml = []
        for i, aid in enumerate(argids):
            nm = argnames[i] if i < len(argnames) else ("第%d" % (i + 1))
            val = self.arg(b, aid, 0)
            # k4 里自定义积木的参数槽是 default_value 影子，放 math_number/text
            # 会在工作区左上角留一个游离的小输入框
            if isinstance(val, dict) and val.get("type") in ("math_number", "text"):
                f = val.get("fields") or {}
                txt = f.get("NUM", f.get("TEXT", "0"))
                val = {"type": "default_value", "fields": {"TEXT": str(txt)}}
            elif isinstance(val, (int, float)):
                val = {"type": "default_value", "fields": {"TEXT": str(val)}}
            ins["ARG%d" % i] = val
            mut_xml.append('<procedures_2_parameter_shadow name="%s" value="0"></procedures_2_parameter_shadow>' % nm)
        mut_s = ('<mutation %s name="%s" def_id="%s">%s</mutation>'
                 % (XML, esc_attr(base), def_id, "".join(mut_xml)))
        return {"type": "procedures_2_callnoreturn", "fields": {"NAME": base},
                "inputs": ins, "mutation": mut_s}

    def sub(self, b, slot):
        v = (b.get("inputs") or {}).get(slot)
        if not v or not isinstance(v[1], str):
            return []
        return self.chain(v[1])

    def chain(self, bid):
        out = []
        guard = 0
        while bid:
            guard += 1
            if guard > 4000:
                self.warnings.append("语句链疑似成环，已截断 @%s" % bid)
                break
            b = self.cur.get(bid)
            if not isinstance(b, dict):
                break
            spec = self.bspec(b)
            if isinstance(spec, list):
                out.extend(spec)          # 一对多展开（如整角色音量 → 逐条音频）
            elif spec:
                out.append(spec)
            else:
                self.unmapped[b["opcode"]] += 1
            bid = b.get("next")
        return out

    # ------------------------------------------------------------ 脚本
    def convert_target(self, tgt, ent):
        self.cur_target = tgt["name"]
        self.cur = tgt.get("blocks") or {}
        self.cur_actor = uid("actor:" + tgt["name"])
        blocks, conns = {}, {}
        bdj = ent["block_data_json"]
        bdj["blocks"], bdj["connections"] = blocks, conns
        self.blocks, self.conns = blocks, conns
        self.B = B.Builder(self.proj, blocks, conns)
        self.B.var_by_name = {}          # 全用 uuid，不走名字解析

        # 收集自定义积木
        self.procs[self.cur_target] = {}
        for b in self.cur.values():
            if isinstance(b, dict) and b["opcode"] == "procedures_definition":
                proto = self.cur.get(b["inputs"]["custom_block"][1]) or {}
                mut = proto.get("mutation") or {}
                code = mut.get("proccode") or ""
                base = proccode_base(code)
                # k4 的自定义积木注册表是**整个作品共享**的（不是每个角色独立），
                # 跨角色同名会触发 "Procedure xxx def exists. Renaming block ..."，
                # 名字被改成 xxx%1。这里自己先全局错开，保证定义与调用一致。
                _n = self.proc_name_used.get(base, 0) + 1
                self.proc_name_used[base] = _n
                if _n > 1:
                    base = "%s%%%d" % (base, _n - 1)
                argnames = json.loads(mut.get("argumentnames") or "[]")
                self.procs[self.cur_target][code] = (base, argnames, uid("proc:" + tgt["name"] + ":" + code))

        hats = [b for b in self.cur.values()
                if isinstance(b, dict) and b.get("parent") is None and b["opcode"] in HATS]
        hats.sort(key=lambda b: (b.get("y") or 0, b.get("x") or 0))
        for h in hats:
            try:
                self.emit(h)
            except Exception as e:  # 单条脚本失败不拖垮整个工程
                if os.environ.get("SB3_DEBUG"):
                    import traceback
                    traceback.print_exc()
                self.warnings.append("脚本转换失败 %s/%s: %s" % (tgt["name"], h["opcode"], e))

    def emit(self, h):
        op = h["opcode"]
        B_ = self.B
        if op == "procedures_definition":
            proto = self.cur.get(h["inputs"]["custom_block"][1]) or {}
            mut = proto.get("mutation") or {}
            code = mut.get("proccode") or ""
            base, argnames, def_id = self.procs[self.cur_target][code]
            warp = (mut.get("warp") == "true")
            prev_proc = self.in_proc
            self.in_proc = True
            body = self.chain(h.get("next"))
            self.in_proc = prev_proc
            if warp and body:
                body = [{"type": "warp", "body": {"DO": body}}]
            inputs = {}
            args = []
            for i, nm in enumerate(argnames):
                inputs["PARAMS%d" % i] = {
                    "type": "procedures_2_stable_parameter",
                    "fields": {"param_name": nm, "param_default_value": ""}}
                args.append('<arg name="PARAMS%d"></arg>' % i)
            spec = {"type": "procedures_2_defnoreturn", "id": def_id,
                    "fields": {"NAME": base},
                    "inputs": inputs,
                    "mutation": ('<mutation %s>%s</mutation>' % (XML, "".join(args))) if args else "",
                    "body": {"STACK": body}}
            bid = B_.build(spec)
            rec = self.blocks[bid]
            rec["shadows"]["PROCEDURES_2_DEFNORETURN_DEFINE"] = ""
            rec["shadows"]["PROCEDURES_2_DEFNORETURN_MUTATOR"] = ""
            rec["shadows"]["STACK"] = rec["shadows"].get("STACK", "")
            # 参数槽不能塞 math_number 影子：k4 会把它当数字输入框，又挂不到
            # 定义块上，最后在工作区左上角留一个游离的、拖不动的小输入框。
            # 参数名由 mutation 的 <arg name="PARAMS0"> 决定，槽留空即可。
            for i in range(len(argnames)):
                rec["shadows"].pop("PARAMS%d" % i, None)
            rec["location"] = [h.get("x") or 0, h.get("y") or 0]
            return

        body = self.chain(h.get("next"))
        if op == "event_whenflagclicked":
            spec = {"type": "start_on_click"}
        elif op == "event_whenthisspriteclicked":
            spec = {"type": "sprite_on_tap", "fields": {"actor": "__self", "type": "mouse_click"},
                    "body": {"DO": body}}
            body = None
        elif op == "event_whenbroadcastreceived":
            f = self._norm_fields(h)
            nm = f.get("BROADCAST_OPTION")
            if isinstance(nm, list):
                nm = nm[0]
            spec = {"type": "self_listen",
                    "inputs": {"message": {"type": "broadcast_input", "fields": {"MESSAGE": nm}}},
                    "body": {"DO": body}}
            body = None
        elif op == "event_whenkeypressed":
            key = KEYS.get(str(self._norm_fields(h).get("KEY_OPTION")), "any")
            spec = {"type": "on_keydown", "fields": {"key_event_type": "down", "key": key},
                    "body": {"DO": body}}
            body = None
        elif op == "control_start_as_clone":
            spec = {"type": "start_as_a_mirror", "body": {"DO": body}}
            body = None
        else:
            self.unmapped["hat:" + op] += 1
            return
        bid = B_.build(spec)
        rec = self.blocks[bid]
        rec["location"] = [h.get("x") or 0, h.get("y") or 0]
        if body:
            first = B_.build_chain(body, bid)
            if first:
                self.conns[bid][first] = {"type": "next"}
                self.blocks[first]["parent_id"] = bid

    # ------------------------------------------------------------ shadow 修复
    def num_shadow(self, v):
        sid = self.B.new_id()
        xml = ('<shadow %s type="math_number" id="%s" visible="visible">'
               '<field constraints="-Infinity,Infinity,0," allow_text="true" name="NUM">%s</field>'
               "</shadow>" % (XML, sid, v))
        return xml

    def text_shadow(self, v=""):
        sid = self.B.new_id()
        return ('<shadow %s type="text" id="%s" visible="visible">'
                '<field name="TEXT">%s</field></shadow>' % (XML, sid, v))

    def dv_shadow(self, v="0"):
        sid = self.B.new_id()
        return ('<shadow %s type="default_value" id="%s" visible="visible">'
                '<field has_been_edited="false" name="TEXT">%s</field></shadow>' % (XML, sid, v))

    def repair_shadows(self):
        """规则 3：值槽即使被真块占着也要留一份 phantom shadow"""
        fixed = 0
        for name, actor in list(self.proj["theatre"]["actors"].items()) + [
                ("场景", self.scene)]:
            blocks = (actor.get("block_data_json") or {}).get("blocks") or {}
            conns = (actor.get("block_data_json") or {}).get("connections") or {}
            for src, cs in conns.items():
                sb = blocks.get(src)
                if not sb:
                    continue
                for tgt, meta in cs.items():
                    if meta.get("type") != "input" or meta.get("input_type") != "value":
                        continue
                    slot = meta.get("input_name")
                    cur = (sb.get("shadows") or {}).get(slot)
                    if isinstance(cur, str) and cur.strip():
                        continue
                    child = blocks.get(tgt) or {}
                    ct = child.get("type")
                    if ct == "math_number":
                        xml = self.num_shadow((child.get("fields") or {}).get("NUM", "0"))
                    elif ct == "text":
                        xml = self.text_shadow((child.get("fields") or {}).get("TEXT", ""))
                    elif ct == "lists_get":
                        sid = self.B.new_id()
                        xml = ('<shadow %s type="lists_get" id="%s" visible="visible" inline="true">'
                               '<field name="VAR">%s</field></shadow>'
                               % (XML, sid, (child.get("fields") or {}).get("VAR", "")))
                    elif ct == "get_audios":
                        sid = self.B.new_id()
                        xml = ('<shadow %s type="get_audios" id="%s" visible="visible" inline="true">'
                               '<field name="sound_id">%s</field></shadow>'
                               % (XML, sid, (child.get("fields") or {}).get("sound_id", "")))
                    elif ct == "broadcast_input":
                        sid = self.B.new_id()
                        xml = ('<shadow %s type="broadcast_input" id="%s" visible="visible">'
                               '<field name="MESSAGE">%s</field></shadow>'
                               % (XML, sid, (child.get("fields") or {}).get("MESSAGE", "")))
                    else:
                        xml = self.dv_shadow("0")
                    sb.setdefault("shadows", {})[slot] = xml
                    fixed += 1
        return fixed

    def fix_broadcast_shadows(self):
        """广播头的下拉必须是「影子块本身」：broadcast_input 子块 is_shadow=True，
        且父块 shadows.message 的 id 与它一致。否则编辑器会在槽里额外渲染一个
        空白的广播积木块（没有文字、没有输入、连不上）。"""
        n = 0
        for ent in list(self.proj["theatre"]["actors"].values()) + [self.scene]:
            bdj = ent.get("block_data_json") or {}
            blocks, conns = bdj.get("blocks") or {}, bdj.get("connections") or {}
            for bid, b in blocks.items():
                if b.get("type") not in ("self_listen", "self_broadcast",
                                         "self_broadcast_and_wait"):
                    continue
                for tgt, meta in (conns.get(bid) or {}).items():
                    if meta.get("input_name") != "message":
                        continue
                    child = blocks.get(tgt)
                    if not child or child.get("type") != "broadcast_input":
                        continue
                    msg = (child.get("fields") or {}).get("MESSAGE", "")
                    if not child.get("is_shadow") or not child.get("is_output"):
                        child["is_shadow"] = True
                        child["is_output"] = True
                        n += 1
                    want = ('<shadow %s type="broadcast_input" id="%s" visible="visible">'
                            '<field name="MESSAGE">%s</field></shadow>'
                            % (XML, tgt, esc_attr(msg)))
                    sh = b.setdefault("shadows", {})
                    if sh.get("message") != want:
                        sh["message"] = want
                        n += 1
        return n

    def fix_call_args(self):
        """铁律 10：自定义积木调用的 ARG 槽里，字面量必须是 default_value 影子块，
        不能是 math_number / text（真实作品里 call 的 ARG 子块 math_number 出现 0 例）。"""
        n = 0
        for ent in list(self.proj["theatre"]["actors"].values()) + [self.scene]:
            bdj = ent.get("block_data_json") or {}
            blocks, conns = bdj.get("blocks") or {}, bdj.get("connections") or {}
            for bid, b in blocks.items():
                if b.get("type") not in ("procedures_2_callnoreturn",
                                         "procedures_2_callreturn"):
                    continue
                for tgt, meta in (conns.get(bid) or {}).items():
                    slot = meta.get("input_name") or ""
                    if not slot.startswith("ARG"):
                        continue
                    child = blocks.get(tgt)
                    if not child or child.get("type") not in ("math_number", "text"):
                        continue
                    txt = (child.get("fields") or {}).get("NUM")
                    if txt is None:
                        txt = (child.get("fields") or {}).get("TEXT", "")
                    child["type"] = "default_value"
                    child["fields"] = {"TEXT": str(txt)}
                    child["field_extra_attr"] = {"TEXT": {"has_been_edited": True}}
                    child["is_output"] = True
                    child["is_shadow"] = True
                    b.setdefault("shadows", {})[slot] = (
                        '<shadow %s type="default_value" id="%s" visible="visible">'
                        '<field has_been_edited="false" name="TEXT">0</field></shadow>'
                        % (XML, tgt))
                    n += 1
        return n

    # ------------------------------------------------------------ 主流程
    def run(self):
        self.sound_id = {}
        self.build_entities()
        self.build_audio()
        # 场景（舞台）脚本
        self.convert_target(self.stage, self.scene)
        for t in self.p["targets"]:
            if t["isStage"]:
                continue
            actor = self.proj["theatre"]["actors"][uid("actor:" + t["name"])]
            self.convert_target(t, actor)
        fixed = self.repair_shadows()
        fixed += self.fix_broadcast_shadows()
        fixed += self.fix_call_args()
        # 真实作品里 scene.actors 恒为 []：角色归属只由 groups + group_order 表达。
        # 两边都填会被重复挂载，编辑器里角色列表/代码区就会错乱。
        self.proj["theatre"]["scenes"][self.scene_id]["actors"] = []
        used = set()
        for e in list(self.proj["theatre"]["actors"].values()) + [
                self.proj["theatre"]["scenes"][self.scene_id]]:
            used |= set(e.get("styles") or [])
        for sid in [k for k in self.proj["theatre"]["styles"] if k not in used]:
            del self.proj["theatre"]["styles"][sid]
        with open(self.out, "w", encoding="utf-8") as f:
            f.write(js_dumps(self.proj))
        self.report = {
            "actors": len(self.proj["theatre"]["actors"]),
            "styles": len(self.proj["theatre"]["styles"]),
            "audio": len(self.proj["audio"]),
            "variables": len(self.proj["variables"]),
            "shadows_fixed": fixed,
            "unmapped": dict(self.unmapped),
            "warnings": self.warnings[:200],
            "empty_costumes": self.empties[:200],
            "empty_costume_count": len(self.empties),
            "bytes": os.path.getsize(self.out),
        }
        return self.report


def esc_attr(s):
    return (str(s).replace("&", "&amp;").replace('"', "&quot;")
            .replace("<", "&lt;").replace(">", "&gt;"))


def proccode_base(code):
    base = re.sub(r"%[sbn]", " ", code)
    return re.sub(r"\s+", " ", base).strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("sb3dir")
    ap.add_argument("out")
    ap.add_argument("--no-audio", action="store_true")
    ap.add_argument("--report", default="")
    a = ap.parse_args()
    c = Conv(a.sb3dir, a.out, keep_audio=not a.no_audio)
    rep = c.run()
    print(json.dumps(rep, ensure_ascii=False, indent=1))
    if a.report:
        with open(a.report, "w", encoding="utf-8") as f:
            json.dump(rep, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
