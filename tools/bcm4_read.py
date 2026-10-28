#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bcm4_read.py — 反编译 kitten4 .bcm4 为可读伪代码，让 AI 能"看懂"已有作品。

用法:
  python bcm4_read.py <work.bcm4> [名称过滤...] [--max N] [--no-vars]
    名称过滤: 只输出名字含该关键字的角色/场景（如: 幽灵 画笔）
    --max N : 每个脚本最多渲染 N 行（默认 200）

输出结构:
  1) 项目概览: 顶层键检查 / 变量与列表 / 音频 / 角色与造型
  2) 每个角色/场景: 按帽子块逐脚本渲染缩进伪代码（中文积木名+参数）
     - 变量/列表/音频/角色 UUID 全部还原成名字
     - controls_if 的 mutation(elseif/else) 还原成 如果/否则如果/否则
     - start_as_a_mirror 的 DO 体、on_key 等 DO 槽正确缩进
"""
import json
import re
import sys

# ---------------------------------------------------------------- 中文积木表
# key=block type, value=渲染模板: {} 内为输入名, [] 内为字段名
# 来自积木对照表(145行) + gen_game.js 实战 + block_struct.json 校对
CN = {
    # 事件/帽子
    "start_on_click": ("当角色被点击", {}),
    "start_on_tag": ("当处于标签[{tag}]", {}),
    "start_on_msg": ("当收到广播[{}{msg}]", {}),
    "on_key": ("当按下按键[{key}]", {"DO": "stmt"}),
    "on_swipe": ("当滑动屏幕", {"DO": "stmt"}),
    "on_keydown": ("当按下按键[{key}]", {"DO": "stmt"}),
    "start_as_a_mirror": ("当作为克隆启动时", {"DO": "stmt"}),
    "terminate": ("终止全部脚本", {}),
    # 广播
    "broadcast_msg": ("发送广播[{}{msg}]", {}),
    "broadcast_and_wait": ("发送广播[{}{msg}]并等待", {}),
    # 控制
    "stop": ("停止[scope={scope}]", {}),
    "restart": ("重启当前作品", {}),
    "break_loop": ("跳出循环", {}),
    "next_frame": ("下一帧", {}),
    "wait_until": ("等待[{}{condition}]", {}),
    "repeat_forever": ("重复执行", {"DO": "stmt"}),
    "repeat_n": ("重复[{}{times}]次", {"DO": "stmt"}),
    "repeat_n_times": ("重复[{}{times}]次", {"DO": "stmt"}),
    "repeat_until": ("重复执行直到[{}{condition}]", {"DO": "stmt"}),
    "repeat_forever_until": ("重复执行直到[{}{condition}]", {"DO": "stmt"}),
    "if_then_else": ("如果", {}),  # 特殊处理 mutation
    "controls_if": ("如果", {}),   # 特殊处理 mutation
    "clone": ("克隆[{}{sprite}]", {}),
    "mirror": ("生成克隆体[{sprite}]", {}),
    "dispose_clone": ("删除此克隆体", {}),
    "warp": ("一步执行(同帧完成)", {"DO": "stmt"}),
    "wait": ("等待[{}{time}]秒", {}),
    "wait_time": ("等待[{}{time}]秒", {}),
    # 侦测(克隆)
    "get_clone_index": ("自己的克隆编号", "r"),
    "get_current_clone_index": ("自己的克隆编号", "r"),
    "get_clone_num": ("[sprite]的克隆数量", "r"),
    "get_clone_index_property": ("克隆体[attribute]第[{}{index}]项属性", "r"),
    # 场景
    "switch_screen": ("切换到场景[{}{screen}]", {}),
    "switch_to_screen": ("切换到场景[{}{screen}]", {}),
    "self_scene_transition": ("以[{transition}]效果切换场景[{direction}]", {}),
    "check_screen": ("是否在屏幕范围内", "r"),
    # 运动
    "go_forward": ("移动[{}{step}]步", {}),
    "self_go_forward": ("移动[{}{steps}]步", {}),
    "move_to_target": ("移到[target={target}]", {}),
    "move_to_xy": ("移到x[{}{x}] y[{}{y}]", {}),
    "set_position": ("设置[{coordinary}]={}{value}", {}),
    "change_coordinate": ("[{coordinary}]增减[{increase}]{}{value}", {}),
    "glide_to": ("在[{time}]秒内滑行到[{coordinary}={} {value}]", {}),
    "glide_coordinate": ("在[{time}]秒内[{coordinary}]增减[{increase}]{}{value}", {}),
    "bounce_off_edge": ("碰到边缘弹回", {}),
    "rotate": ("旋转[{}{degree}]度", {}),
    "rotate_around": ("绕[sprite]旋转[{}{degree}]度", {}),
    "shake": ("震动[{}{time}]秒", {}),
    "point_towards": ("面向[target]", {}),
    "face_to": ("面向[sprite]", {}),
    "self_set_rotate_type": ("设置旋转模式[rotate_type={rotate_type}]", {}),
    "set_role_camp": ("设置阵营[role_camp={role_camp}]", {}),
    # 外观
    "set_costume": ("切换造型[index={index}]", {}),
    "set_costume_by_index": ("切换造型[{}{index}]", {}),
    "prev_next_style": ("上一个/下一个造型[{prev_next}]", {}),
    "self_prev_next_style": ("上一个/下一个造型[{prev_or_next}]", {}),
    "self_appear": ("显示", {}),
    "appear": ("显示", {}),
    "self_disappear": ("隐藏", {}),
    "disappear": ("隐藏", {}),
    "self_gradually_disappear": ("逐渐消失[{time}]", {}),
    "self_gradually_show": ("逐渐显示[{time}]", {}),
    "gradually_show_hide": ("渐变显示/隐藏[is_show={is_show} time={} {time}]", {}),
    "self_set_opacity": ("设置透明度[{}{value}]", {}),
    "set_height_scale": ("高度缩放[{increase}]{}{value}", {}),
    "add_width_height_scale": ("宽高缩放[{increase}]{}{value}", {}),
    "add_width_height_scale_2": ("宽度缩放[{increase}]{}{value}", {}),
    "set_effect": ("设置特效[scope={scope} value={} {value}]", {}),
    "change_effect": ("特效增加[scope={scope} step={} {step}]", {}),
    "clear_effects": ("清除全部特效", {}),
    "set_theratic_layer": ("移到图层[layer={layer}]", {}),
    "set_layer_with_pen": ("移到画笔层[{position}]", {}),
    "flip": ("翻转[options={options}]", {}),
    # 对话框
    "stage_dialog": ("弹窗[text]", {"text": "val"}),
    "dialog_say": ("说[{}{text}] ({time}秒)", {}),
    "ask_call": ("询问[{}{text}]并等待", {}),
    "get_answer": ("获得答案", "r"),
    "ask_and_choose": ("询问并选择[text]", {}),
    "choice_and_index": ("最后一次选择的序号", "r"),
    "translate": ("翻译成[language={} {language}] {}{text}", {}),
    "translate_result": ("翻译结果[language]", "r"),
    # 声音
    "play": ("播放声音[{}{audio}]", {}),
    "play_audio_2": ("播放声音[{}{audio}]", {}),
    "play_audio_wait": ("播放声音[{}{audio}]并等待", {}),
    "set_volume_rate": ("设置音量[select={audio_select}] {}{value}", {}),
    "change_volume_rate": ("音量增减[audio_select] {}{value}", {}),
    "stop_audio": ("停止声音[{}{audio}]", {}),
    "stop_audio_2": ("停止声音[{}{audio}]", {}),
    "play_words_audio": ("朗读[{}{text}]", {}),
    "play_words_audio_wait": ("朗读[{}{text}]并等待", {}),
    "voice_recognition": ("语音识别[lang={lang}]", "r"),
    "ask_listen": ("听写[{}{text}]", {}),
    "voice_answer": ("获得识别结果", "r"),
    "ask_record": ("录音[{}{TEXT}]", {}),
    "voice_detection": ("录音检测[state={state}]", "r"),
    # 画笔
    "pen_down": ("落笔", {}),
    "self_pen_down": ("落笔", {}),
    "pen_up": ("抬笔", {}),
    "self_pen_up": ("抬笔", {}),
    "clear_drawing": ("清除画迹", {}),
    "set_pen_size": ("笔迹粗细[{}{size}]", {}),
    "change_pen_size": ("笔迹粗细增减[{}{step}]", {}),
    "set_pen_color": ("画笔颜色[color={color}]", {}),
    "set_pen_color_property": ("颜色属性[scope={scope} {}{value}]", {}),
    "change_pen_color_property_2": ("颜色属性增减[scope={scope} {}{step}]", {}),
    "image_stamp": ("盖章", {}),
    "stamp": ("盖章", {}),
    # 侦测/运算
    "get_3": ("[sprite]的坐标[attribute={attribute}]", "r"),
    "distance_to": ("到目标的距离[axis={axis}]", "r"),
    "self_distance_to": ("到目标的距离", "r"),
    "orientation": ("角度[axis={axis}]", "r"),
    "get_rotation": ("角度[axis={axis}]", "r"),
    "mouse_info": ("鼠标[position={position}]", "r"),
    "get_mouse_info": ("鼠标[position={position}]", "r"),
    "current_time": ("计时器[op={op}]", "r"),
    "get_time": ("计时器", "r"),
    "timer_state": ("计时器状态[action={action}]", "r"),
    "show_hide_timer": ("显示/隐藏计时[state={state}]", "r"),
    "volume": ("音量", "r"),
    "get_volume": ("音量", "r"),
    "key_pressed": ("按键[key={key}]被按下?", "r"),
    "check_key": ("按键[key={key}]被按下?", "r"),
    "bump_into_color": ("碰到颜色[color={color}]?", "r"),
    "bump_into_boundary": ("碰到边缘?", "r"),
    "bump_into_other": ("碰到角色/鼠标[sprite={sprite}]?", "r"),
    # 运算
    "shadow_number": ("数值({{VALUE}})", "r"),
    "math_number": ("{NUM}", "r"),
    "shadow_text": ("文本({{VALUE}})", "r"),
    "math_op": ("({A} {OP} {B})", "r"),
    "math_arithmetic": ("({A} {OP} {B})", "r"),
    "random_num": ("随机[{a}..{b}]", "r"),
    "random": ("随机[{a}..{b}]", "r"),
    "number_property": ("({NUMBER_TO_CHECK}是否{PROPERTY})", "r"),
    "math_number_property": ("({NUMBER_TO_CHECK}是否{PROPERTY})", "r"),
    "divisible_by": ("([{NUMBER_TO_CHECK}]能被[{DIVISOR}]整除)", "r"),
    "divide_by": ("([{NUMBER_TO_CHECK}]能被[{DIVISOR}]整除)", "r"),
    "logic_operation": ("({A} {OP} {B})", "r"),
    "calculate": ("复合运算({})", "r"),
    "math_single": ("{OP}({NUM})", "r"),
    "math_modulo": ("([{DIVIDEND}]求余[{DIVISOR}])", "r"),
    "math_trig": ("{OP}({NUM})", "r"),
    "math_round": ("{OP}({NUM})", "r"),
    "logic_compare": ("({A} {OP} {B})", "r"),
    "logic_boolean": ("{BOOL}", "r"),
    "logic_negate": ("不成立({BOOL})", "r"),
    "text_type": ("转文本({{content}})", "r"),
    "text_join": ("合并({})", "r"),
    "text_length": ("文本长度({{VALUE}})", "r"),
    "text_select": ("取字符[STRING从char_start_index到char_end_index]", "r"),
    "text_contain": ("(TEXT1包含TEXT2?)", "r"),
    "text_split": ("分割(TEXT按SPLIT)", "r"),
    # 变量/列表
    "var_get": ("变量[VAR]", "r"),
    "variables_get": ("变量[{VAR}]", "r"),
    "var_set": ("变量[VAR]= {}{VALUE}", {}),
    "variables_set": ("变量[{VAR}] = {}{VALUE}", {}),
    "change_variable": ("变量[{valname}]{method} {}{n}", {}),
    "list_push": ("列表[VAR]追加{}{VALUE}", {}),
    "lists_append": ("列表[{VAR}]追加 {}{VALUE}", {}),
    "list_insert": ("列表[VAR]第[{}{INDEX}]项插入{}{VALUE}", {}),
    "lists_insert_value": ("列表[{VAR}]第[{}{INDEX}]项插入 {}{VALUE}", {}),
    "list_delete": ("列表[VAR]删除[{}{INDEX}]", {}),
    "lists_delete": ("列表[{VAR}]删除[{}{INDEX}]", {}),
    "list_replace": ("列表[VAR]第[{}{INDEX}]项替换为{}{VALUE}", {}),
    "lists_replace": ("列表[{VAR}]第[{}{INDEX}]项 = {}{VALUE}", {}),
    "list_copy": ("复制列表[VALUE]到[TARGET]", {}),
    "lists_copy": ("复制列表[{VALUE}]到[{TARGET}]", {}),
    "list_item": ("列表[VAR]第[{}{INDEX}]项", "r"),
    "lists_get_value": ("列表[{VAR}]第[{}{INDEX}]项", "r"),
    "list_length": ("列表[VAR]长度", "r"),
    "lists_length": ("列表[{VAR}]长度", "r"),
    "list_include_of": ("列表[VAR]含[{}{VALUE}]?", "r"),
    "lists_include_of": ("列表[{VAR}]含[{}{VALUE}]?", "r"),
    "list_is_empty": ("列表[VAR]为空?", "r"),
    "lists_is_empty": ("列表[{VAR}]为空?", "r"),
    "show_hide_list": ("显示/隐藏列表[FUNC][VAR]", {}),
    "lists_get": ("列表[{VAR}]", "r"),
    # 自定义过程(如有)
    "procedures_definition": ("定义过程", {}),
    "procedures_call": ("调用过程[mutation]", {}),

    # ---- self_* 变体(不带目标下拉，直接作用于自己)，槽名是小写的 ----
    "self_set_position": ("设置[{coordinary}] = {}{value}", {}),
    "self_change_coordinate": ("[{coordinary}]增减[{increase}]{}{value}", {}),
    "self_move_to": ("移到 x[{}{x}] y[{}{y}]", {}),
    "self_move_specify": ("移向[{target}]", {}),
    "self_point_towards": ("面向方向[{}{degrees}]", {}),
    "self_rotate": ("旋转[{}{degrees}]度", {}),
    "set_scale": ("设置大小为[{}{scale}]", {}),
    "set_width_height_scale": ("设置[{type}]缩放[{}{value}]", {}),
    "add_width_height_scale_2": ("[type]增加[{}{increase}]", {}),
    # ---- 画笔/图层 ----
    "self_set_pen_size": ("设置画笔粗细[{}{size}]", {}),
    "self_set_pen_color": ("设置画笔颜色[{color}]", {}),
    "self_set_pen_color_property": ("设置画笔[{scope}]为[{}{val}]", {}),
    "set_pen_path": ("设置画笔[{point}]", {}),
    "set_fill_style": ("设置填充色[{color}]", {}),
    "set_theatre_layer": ("设置层级[{layer}]", {}),
    # ---- 广播/变量显示 ----
    "self_broadcast": ("发送广播[{}{message}]", {}),
    "self_broadcast_and_wait": ("发送广播[{}{message}]并等待", {}),
    "show_hide_variable": ("[FUNC]变量[{VAR}]", {}),
}

OP_CN = {
    "EQ": "==", "NEQ": "!=", "GT": ">", "LT": "<", "LTE": "<=", "GTE": ">=",
    "ADD": "+", "MINUS": "-", "MULTIPLY": "*", "DIVIDE": "/", "POWER": "^",
    "AND": "且", "OR": "或",
    "ROOT": "√", "ABS": "|", "NEG": "-",
    "increase": "+=", "decrease": "-=",
}

ATTR_XY = {"0": "x", "1": "y"}

# 解析积木的 shadow 字面量（值输入无真实连接、用预设值/默认值时）
_SHADOW_NUM = re.compile(r'name="(?:NUM|NUMBER)"[^>]*>([^<]*)<')
_SHADOW_TXT = re.compile(r'name="TEXT"[^>]*>([^<]*)<')


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


class Reader:
    def __init__(self, proj):
        self.p = proj
        self.var_name, self.var_kind = {}, {}
        for vid, v in (proj.get("variables") or {}).items():
            self.var_name[vid] = v.get("name", vid)
            self.var_kind[vid] = v.get("type", "any")
        self.aud_name = {aid: a.get("name", aid)
                         for aid, a in (proj.get("audio") or {}).items()}
        th = proj.get("theatre") or {}
        self.actor_name = {aid: a.get("name", aid)
                           for aid, a in (th.get("actors") or {}).items()}
        self.actor_name["__self"] = "自己"
        self.scene_name = {sid: s.get("name", sid)
                           for sid, s in (th.get("scenes") or {}).items()}
        # shadow 索引: shadow块id -> {字段名: 值}
        # 用途: 有些块(field 被序列化成 "?")的真实值只存在父块的 shadows XML 里，
        #       例如 lists_get 的 VAR、被折叠成 shadow 的 math_number 的 NUM。
        self.shadow_index = {}
        ents = list((th.get("scenes") or {}).values()) + list((th.get("actors") or {}).values())
        for ent in ents:
            for _bid, bl in ((ent.get("block_data_json") or {}).get("blocks") or {}).items():
                for _slot, raw in (bl.get("shadows") or {}).items():
                    if not isinstance(raw, str) or "<shadow" not in raw:
                        continue
                    m_id = re.search(r'id="([^"]+)"', raw)
                    if not m_id:
                        continue
                    flds = dict(re.findall(r'<field[^>]*name="([^"]+)"[^>]*>([^<]*)</field>', raw))
                    if flds:
                        self.shadow_index.setdefault(m_id.group(1), {}).update(flds)

    def fields_of(self, b):
        """取字段表，值为 "?" 的占位项用 shadow XML 里的真实值补上。"""
        f = b.get("fields") or {}
        if not any(v == "?" for v in f.values()):
            return f
        fix = {k: v for k, v in (self.shadow_index.get(b.get("id")) or {}).items()
               if f.get(k) == "?"}
        if not fix:
            return f
        merged = dict(f)
        merged.update(fix)
        return merged

    def name(self, kind, uid):
        if uid is None or uid == "?" or uid == "":
            return "?"
        tbl = {"var": self.var_name, "audio": self.aud_name,
               "actor": self.actor_name, "scene": self.scene_name}.get(kind, {})
        return tbl.get(uid, f"<{kind}:{str(uid)[:10]}>")

    # ------------------------------------------------------------ 表达式
    def expr(self, bid, blocks, conns, depth=0):
        b = blocks.get(bid)
        if b is None:
            return "<?>"
        t = b.get("type", "?")
        f = self.fields_of(b)
        ins = self.inputs_of(bid, blocks, conns)

        def E(name):
            v = ins.get(name)
            if v:
                return self.expr(v, blocks, conns, depth + 1)
            s = self.shadow_literal(b, name)
            return s if s is not None else "?"

        if t in ("math_number",):
            return str(f.get("NUM") or f.get("TEXT") or "?")
        if t in ("variables_get", "var_get"):
            return self.name("var", f.get("VAR"))
        if t in ("get_audios",):
            return f"声音{self.name('audio', f.get('sound_id'))}"
        if t in ("get_whole_audios",):
            return f"整段声音{self.name('audio', f.get('sound_id'))}"
        if t == "get_3":
            ax = ATTR_XY.get(f.get("attribute"), f.get("attribute"))
            return f"{self.name('actor', f.get('sprite'))}.{ax}"
        if t == "get_mouse_info":
            return f"鼠标.{f.get('position', '?')}"
        if t == "mouse_down":
            return f"鼠标{f.get('mouse_event_type', '')}按下?"
        if t == "logic_boolean":
            return "真" if f.get("BOOL") == "TRUE" else "假"
        if t == "shadow_number":
            return str(ins.get("VALUE") or f.get("VALUE") or "?")
        if t == "shadow_text":
            return f'"{ins.get("VALUE", "?")}"'
        if t == "text_type":
            return f"text({E('content')})"
        if t in ("logic_compare", "logic_operation", "math_arithmetic"):
            op = OP_CN.get(f.get("OP"), f.get("OP"))
            if t == "logic_operation":
                op = OP_CN.get(f.get("OP"), f.get("OP"))
                return f"({E('A')} {op} {E('B')})"
            return f"({E('A')} {op} {E('B')})"
        if t == "math_single":
            op = f.get("OP")
            if op == "ABS":
                return f"|{E('NUM')}|"
            if op == "ROOT":
                return f"√({E('NUM')})"
            return f"{op}({E('NUM')})"
        if t == "change_variable":  # 有人把它当表达式
            return f"变量{self.name('var', f.get('valname'))}{OP_CN.get(f.get('method'), f.get('method'))}"

        if t == "lists_get":
            return self.name("var", f.get("VAR"))
        if t in ("procedures_2_callnoreturn", "procedures_2_callreturn"):
            return self._call_text(b, blocks, conns)
        if t == "lists_get_value":
            if "VAR" in ins:
                var = self.expr(ins["VAR"], blocks, conns, depth + 1)
            else:
                var = self.name("var", f.get("VAR"))
            ty = f.get("TYPE", "first")
            # 铁律: TYPE 只是下拉默认值残留，真实语义看 INDEX 槽有没有挂块。
            # 实测本类块 1224 个 TYPE=first 全部带 INDEX 输入，50 个 TYPE=last 全不带。
            if "INDEX" in ins:
                return f"列表[{var}]第[{self.expr(ins['INDEX'], blocks, conns, depth + 1)}]项"
            if ty in ("first",):
                return f"列表[{var}]首项"
            if ty in ("last",):
                return f"列表[{var}]末项"
            if ty in ("random",):
                return f"列表[{var}]随机项"
            return f"列表[{var}]第[{self._idx_expr(ins, E, b)}]项"
        if t in ("procedures_2_parameter", "procedures_2_stable_parameter"):
            return f"参数{f.get('param_name', '?')}"

        tpl = CN.get(t)
        if tpl and tpl[1] == "r":
            label = tpl[0]
            # 替换字段占位 {field} 与输入占位 {name}
            out = re.sub(r"\{([A-Za-z_][A-Za-z0-9_]*)\}",
                         lambda m: (self._field_or_input(m.group(1), f, ins, E)), label)
            return out.replace("{}{", "{").replace("{}", "")
        if tpl:  # 语句类模板：同样做占位替换后作为表达式渲染（孤立块/特殊场景用）
            return re.sub(r"\{([A-Za-z_][A-Za-z0-9_]*)\}",
                          lambda m: self._resolve_place(m.group(1), f, ins, E, b),
                          tpl[0]).replace("{}{", "{").replace("{}", "")
        # 兜底: 用 block_struct.json 的输入清单渲染
        return self.generic_expr(t, b, ins, E, depth)

    def _field_or_input(self, key, f, ins, E):
        if key in f:
            v = f[key]
            return ({"__self": "自己"}.get(v) or
                    self.name("actor", v) if key in ("sprite",) else str(v))
        if key in ins:
            return E(key)
        return f"{key}?"

    def generic_expr(self, t, b, ins, E, depth):
        args = []
        for k, v in ins.items():
            args.append(f"{k}={v}")
        for k, v in (b.get("fields") or {}).items():
            args.append(f"{k}={v}")
        return f"{t}({', '.join(args)})"

    def inputs_of(self, bid, blocks, conns):
        ins = {}
        for tgt, meta in (conns.get(bid) or {}).items():
            if meta.get("type") == "input":
                ins[meta.get("input_name")] = tgt
        return ins

    # ------------------------------------------------------------ 语句
    def render_chain(self, bid, blocks, conns, indent, out, maxlines):
        cur = bid
        while cur and len(out) < maxlines:
            b = blocks.get(cur)
            if b is None:
                break
            self.render_stmt(cur, b, blocks, conns, indent, out, maxlines)
            nxt = None
            for tgt, meta in (conns.get(cur) or {}).items():
                if meta.get("type") == "next":
                    nxt = tgt
            cur = nxt

    def render_stmt(self, bid, b, blocks, conns, indent, out, maxlines):
        t = b.get("type")
        f = self.fields_of(b)
        ins = self.inputs_of(bid, blocks, conns)
        bodies = self.bodies_of(bid, blocks, conns)  # input_name -> chain head
        pad = "  " * indent

        def E(name):
            v = ins.get(name)
            if v:
                return self.expr(v, blocks, conns)
            s = self.shadow_literal(b, name)
            return s if s is not None else "?"

        if t in ("controls_if", "if_then_else"):
            self.render_if(b, blocks, conns, bodies, ins, indent, out, maxlines)
            return

        if t == "lists_delete":
            var = self.expr(ins["VAR"], blocks, conns) if "VAR" in ins else self.name("var", f.get("VAR"))
            ty = f.get("TYPE", "first")
            if ty == "all":
                out.append(pad + f"清空列表[{var}]")
            elif ty == "first":
                out.append(pad + f"列表[{var}]删除首项")
            elif ty == "last":
                out.append(pad + f"列表[{var}]删除末项")
            else:
                out.append(pad + f"列表[{var}]删除第[{self._idx_expr(ins, E, b)}]项")
            return

        if t == "lists_replace" and f.get("TYPE") == "last":
            var = self.expr(ins["VAR"], blocks, conns) if "VAR" in ins else self.name("var", f.get("VAR"))
            out.append(pad + f"列表[{var}]末项 = {E('VALUE')}")
            return

        # 模板渲染
        tpl = CN.get(t)
        bodies_used = set()
        if tpl and tpl[1] != "r":
            label, spec = tpl
            txt = re.sub(r"\{([A-Za-z_][A-Za-z0-9_]*)\}",
                         lambda m: self._resolve_place(m.group(1), f, ins, E, b), label)
            out.append(pad + txt.replace("{}{", "{").replace("{}", ""))
            for name, kind in spec.items():
                if kind == "stmt" and name in bodies:
                    bodies_used.add(name)
        elif t == "variables_set":
            out.append(pad + f"变量[{self.name('var', f.get('VAR'))}] = {E('VALUE')}")
        elif t == "change_variable":
            m = OP_CN.get(f.get("method"), f.get("method"))
            out.append(pad + f"变量[{self.name('var', f.get('valname'))}] {m} {E('n')}")
        elif t == "procedures_call":
            out.append(pad + f"调用 {self.mutation_text(b)}")
        elif t in ("procedures_2_callnoreturn", "procedures_2_callreturn"):
            out.append(pad + self._call_text(b, blocks, conns))
        elif t == "procedures_2_return_value":
            v = ins.get("VALUE")
            val = self.expr(v, blocks, conns) if v else (self.shadow_literal(b, "VALUE") or "?")
            out.append(pad + f"返回 {val}")
        else:
            # 兜底: generic 语句渲染
            args = []
            for k, v in ins.items():
                vv = self.expr(v, blocks, conns) if v else "?"
                args.append(f"{k}={vv}")
            for k, v in f.items():
                args.append(f"{k}={v}")
            out.append(pad + f"{t}({', '.join(args)})")

        # 挂体渲染（repeat/forever/on_key/warp/start_as_a_mirror...）
        for name, head in bodies.items():
            if name == "ELSE":
                continue
            self.render_chain(head, blocks, conns, indent + 1, out, maxlines)
        if t in ("start_as_a_mirror", "on_key", "on_keydown", "on_swipe") and not bodies:
            out.append(pad + "(空)")

    def _resolve_place(self, key, f, ins, E, b):
        if key.startswith("_"):
            return key[1:]
        if key in f:
            v = f[key]
            if key in ("sprite",):
                return self.name("actor", v)
            if key in ("VAR", "valname"):
                return self.name("var", v)
            if key in ("sound_id", "audio"):
                return self.name("audio", v)
            if key in ("msg",):
                return str(v)
            return str(v)
        if key == "INDEX":
            return self._idx_expr(ins, E, b)
        if key == "VAR" and key not in f and key in ins:
            return E(key)
        if key in ins:
            return E(key)
        return f"{key}?"

    def bodies_of(self, bid, blocks, conns):
        bodies = {}
        for tgt, meta in (conns.get(bid) or {}).items():
            if meta.get("type") == "input" and meta.get("input_type") == "statement":
                bodies[meta.get("input_name")] = tgt
        return bodies

    def render_if(self, b, blocks, conns, bodies, ins, indent, out, maxlines):
        t = b.get("type")
        pad = "  " * indent
        mut = b.get("mutation") or ""
        m = re.search(r'elseif="(\d+)"', mut)
        n_elseif = int(m.group(1)) if m else 0
        has_else = bool(re.search(r'else="1"', mut))
        pad2 = "  " * (indent + 1)

        def cond_str(idx):
            v = ins.get(f"IF{idx}")
            return self.expr(v, blocks, conns) if v else "?"

        out.append(pad + f"如果 {cond_str(0)} :")
        if bodies.get("DO0"):
            self.render_chain(bodies["DO0"], blocks, conns, indent + 1, out, maxlines)
        for i in range(1, n_elseif + 1):
            out.append(pad + f"否则如果 {cond_str(i)} :")
            if bodies.get(f"DO{i}"):
                self.render_chain(bodies[f"DO{i}"], blocks, conns, indent + 1, out, maxlines)
        if has_else:
            out.append(pad + "否则 :")
            if bodies.get("ELSE"):
                self.render_chain(bodies["ELSE"], blocks, conns, indent + 1, out, maxlines)

    def mutation_text(self, b):
        mut = b.get("mutation") or ""
        return re.sub(r"<[^>]+>", "", mut).strip() or (b.get("mutation") or "")[:80]

    def shadow_literal(self, b, input_name):
        sh = (b.get("shadows") or {}).get(input_name)
        if not sh:
            return None
        m = _SHADOW_NUM.search(sh)
        if m:
            return m.group(1)
        m = _SHADOW_TXT.search(sh)
        if m:
            return '"' + m.group(1) + '"'
        if 'name="BOOL"' in sh:
            return "真" if "TRUE" in sh else "假"
        return None

    def _idx_expr(self, ins, E, b):
        """列表索引输入名不统一(INDEX/NUM/NUMBER)，统一解析。"""
        for k in ("INDEX", "NUM", "NUMBER"):
            if k in ins:
                return E(k)
        for k in ("INDEX", "NUM", "NUMBER"):
            s = self.shadow_literal(b, k)
            if s is not None:
                return s
        return "<无索引槽>"

    def render_procedure(self, bid, b, blocks, conns, indent, out, maxlines):
        t = b.get("type")
        f = self.fields_of(b)
        name = f.get("NAME", "?")
        bodies = self.bodies_of(bid, blocks, conns)
        ins = self.inputs_of(bid, blocks, conns)
        pad = "  " * indent
        if t == "procedures_2_return_value":
            v = ins.get("VALUE")
            val = self.expr(v, blocks, conns) if v else (self.shadow_literal(b, "VALUE") or "?")
            out.append(f"{pad}函数 {name}() -> {val}")
            return
        sig = ", ".join(self._def_params(bid, blocks, conns))
        out.append(f"{pad}函数 {name}({sig}):")
        stack = bodies.get("STACK")
        if stack:
            self.render_chain(stack, blocks, conns, indent + 1, out, maxlines)
        else:
            out.append(pad + "  (空)")

    def _def_params(self, bid, blocks, conns):
        """定义块的形参列表：PARAMS<n> 输入上挂的是 procedures_2_stable_parameter，
        其 param_name 字段才是真实形参名（铁律 11）。返回按 n 排序的名字列表。"""
        params = []
        for iname, tgt in self.inputs_of(bid, blocks, conns).items():
            if not str(iname).startswith("PARAMS"):
                continue
            try:
                idx = int(str(iname)[len("PARAMS"):])
            except ValueError:
                continue
            tb = blocks.get(tgt) or {}
            pn = (tb.get("fields") or {}).get("param_name")
            params.append((idx, pn if pn else "?"))
        params.sort()
        return [p for _i, p in params]

    def _call_text(self, b, blocks, conns):
        f = self.fields_of(b)
        ins = self.inputs_of(b["id"], blocks, conns)
        name = f.get("NAME", "?")
        args = []
        for i in range(8):
            key = f"ARG{i}"
            if key in ins:
                args.append(self.expr(ins[key], blocks, conns))
            elif key in f and f[key]:
                v = f[key]
                if v in blocks:
                    args.append(self.expr(v, blocks, conns))
                else:
                    args.append(str(v))
            else:
                break
        return f"调用 {name}({', '.join(args)})"

    # ------------------------------------------------------------ 概览
    def hat_label(self, b):
        t = b.get("type")
        f = self.fields_of(b)
        if t == "start_on_click":
            return "当角色被点击"
        if t == "start_as_a_mirror":
            return "当作为克隆启动时"
        if t in ("on_key", "on_keydown"):
            return f"当按下按键[{f.get('key', '?')}]"
        if t == "on_swipe":
            return "当滑动屏幕"
        if t == "start_on_msg":
            return f"当收到广播[{f.get('msg') or self.shadow_msg(b) or '?'}]"
        if t == "self_listen":
            return f"当收到广播[{self.shadow_msg(b) or '?'}]"
        if t == "start_on_tag":
            return f"当处于标签[{f.get('tag', '?')}]"
        return t

    def shadow_msg(self, b):
        """广播消息藏在 shadows['message'] 的 XML 里，不在 fields 里。"""
        sh = (b.get("shadows") or {}).get("message") or ""
        m = re.search(r'name="MESSAGE"[^>]*>([^<]*)<', sh)
        return m.group(1) if m else ""


def dump_entity(r, ent, kind, filters, maxlines):
    name = ent.get("name") or "?"
    if filters and not any(x in name for x in filters):
        return
    bdj = ent.get("block_data_json") or {}
    blocks = bdj.get("blocks") or {}
    conns = bdj.get("connections") or {}
    styles = ent.get("styles") or []
    print(f"\n{'=' * 62}")
    print(f"{kind}: {name}   (积木 {len(blocks)} 个, 造型 {len(styles)} 个)")
    print("=" * 62)
    tops = [b for b in blocks.values() if not b.get("parent_id")]
    tops.sort(key=lambda x: (x.get("location") or [0, 9e9])[1])
    HATS = {"start_on_click", "start_as_a_mirror", "on_key", "on_keydown",
            "on_swipe", "start_on_msg", "start_on_tag", "start_on_cloud_msg",
            "self_listen"}
    for hat in tops:
        t0 = hat.get("type")
        if t0 in ("procedures_2_defnoreturn", "procedures_2_return_value"):
            out = []
            r.render_procedure(hat["id"], hat, blocks, conns, 0, out, maxlines)
            for line in out[:maxlines]:
                print(line)
            if len(out) > maxlines:
                print(f"  ... (截断, 共 {len(out)} 行)")
            continue
        if hat.get("type") not in HATS:
            # 未挂到任何脚本下的孤立积木（拖了一半/被拆下的）
            txt = r.expr(hat["id"], blocks, conns)
            print(f"\n── 孤立积木 @ loc{hat.get('location')}: {txt}")
            continue
        print(f"\n── 脚本 @ loc{hat.get('location')}: {r.hat_label(hat)}")
        out = []
        if hat.get("type") in ("start_as_a_mirror", "self_listen"):
            bodies = r.bodies_of(hat["id"], blocks, conns)
            if bodies.get("DO"):
                r.render_chain(bodies["DO"], blocks, conns, 1, out, maxlines)
            else:
                out.append("  (空)")
        else:
            nxt = None
            for tgt, meta in (conns.get(hat["id"]) or {}).items():
                if meta.get("type") == "next":
                    nxt = tgt
            if nxt:
                r.render_chain(nxt, blocks, conns, 1, out, maxlines)
            else:
                out.append("  (空)")
        for line in out[:maxlines]:
            print(line)
        if len(out) > maxlines:
            print(f"  ... (截断, 共 {len(out)} 行)")


def dump_vars(proj):
    print("\n----- 变量 / 列表 -----")
    for vid, v in (proj.get("variables") or {}).items():
        kind = "列表" if v.get("type") == "list" else "变量"
        scope = "全局" if v.get("is_global", True) else "角色"
        val = v.get("value")
        vs = json.dumps(val, ensure_ascii=False) if isinstance(val, list) else val
        print(f"  [{kind}·{scope}] {v.get('name')}  = {vs}")
    auds = proj.get("audio") or {}
    if auds:
        print(f"----- 音频 ({len(auds)}) -----")
        for a in auds.values():
            print(f"  [音] {a.get('name')}")


def main():
    args = sys.argv[1:]
    path = args[0] if args else None
    if not path:
        print(__doc__)
        sys.exit(2)
    filters, maxlines, no_vars = [], 200, False
    i = 1
    while i < len(args):
        a = args[i]
        if a == "--max":
            maxlines = int(args[i + 1]); i += 2
        elif a == "--no-vars":
            no_vars = True; i += 1
        else:
            filters.append(a); i += 1

    proj = load(path)
    th = proj.get("theatre") or {}
    r = Reader(proj)

    print(f"# {proj.get('project_name', '?')}   ({path})")
    std_missing = [k for k in (
        "project_name", "theatre", "variables", "variable_order", "audio",
        "audio_order", "broadcasts", "toolbox", "toolbox_order", "painter") if k not in proj]
    if "compile_result" in proj:
        print("!! 警告: 含顶层 compile_result（编辑器会忽略 block_data_json）")
    if std_missing:
        print(f"!! 缺少顶层键: {std_missing}")
    print(f"actors={len(th.get('actors') or {})} scenes={len(th.get('scenes') or {})}"
          f" variables={len(proj.get('variables') or {})} audio={len(proj.get('audio') or {})}")
    if not no_vars and not filters:
        # 给了角色/场景名过滤时，跳过全局变量大段，直接看该角色脚本
        dump_vars(proj)
    for sid, sc in (th.get("scenes") or {}).items():
        dump_entity(r, sc, "场景", filters, maxlines)
    for aid, ac in (th.get("actors") or {}).items():
        dump_entity(r, ac, "角色", filters, maxlines)


if __name__ == "__main__":
    main()
