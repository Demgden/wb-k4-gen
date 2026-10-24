#!/usr/bin/env node
"use strict";
/**
 * bcm4gen.js — 通用 kitten4 (.bcm4) 生成库
 * ------------------------------------------------------------------
 * 把「积木 → 编辑器原生 bcm4」的发射逻辑与 DSL 抽成可复用模块。
 * 配合 skill 的 references/kitten4_rules.md（七条铁律）与 data/block_defs.json（默认 shadow 模板）使用。
 *
 * 用法（见 template_work.js）：
 *   const K = require("./bcm4gen.js");
 *   K.loadDefs(path.join(__dirname, "../data/block_defs.json"));
 *   K.defVar("得分", 0, true);
 *   const cat = K.defActor("猫", [styleCat]);
 *   K.script(cat, K.onStart(K.move(10), K.wait(1)));
 *   K.write("out.bcm4");
 *
 * 注意：本模块用「模块级单例状态」保存 vars/lists/actors…（与 gen_game.js 一致），
 * 每个生成脚本都是独立 node 进程，不会互相污染。需要清空重来时调用 K.reset()。
 */
const fs = require("fs");
const path = require("path");
const crypto = require("crypto");

// ============================================================ 默认输入 shadow 模板
// editor 为每个值输入都保存一份 shadow「模板」(block_defs.json 即编辑器自带的 define_block_xml 源)。
// 当输入被真实 reporter 占据时，模板以 phantom id 保留（否则编辑器改一下就坏 / 连接类型写错）。
// 字面子块 → maps 内 is_shadow 块；语句输入 → ""。铁律 5。
let DEF_XML = {};
function loadDefs(jsonPath) {
  const raw = JSON.parse(fs.readFileSync(jsonPath, "utf8"));
  DEF_XML = {};
  for (const [btype, frag] of Object.entries(raw)) {
    const inputs = {};
    const re = /<value name="([^"]+)"[^>]*>([\s\S]*?)<\/value>/g;
    let m;
    while ((m = re.exec(frag))) {
      const inner = m[2];
      const sm = inner.match(/<shadow type="([^"]+)"[^>]*>([\s\S]*?)<\/shadow>/);
      const em = inner.match(/<empty type="([^"]+)"[^>]*>([\s\S]*?)<\/empty>/);
      if (sm) inputs[m[1]] = { kind: "shadow", type: sm[1], fields: sm[2] };
      else if (em) inputs[m[1]] = { kind: "empty", type: em[1] };
    }
    DEF_XML[btype] = inputs;
  }
}

// 为「被真实 reporter 占据」的输入构造默认 shadow 模板（phantom id）。
function shadowTemplate(btype, iname, real) {
  const def = DEF_XML[btype];
  const inner = def && def[iname];
  if (!inner) return "";
  const sid = nid();
  if (inner.kind === "empty") {
    return `<empty xmlns="http://www.w3.org/1999/xhtml" type="${inner.type}" id="${sid}" visible="visible" editable="false"></empty>`;
  }
  let fields = inner.fields || "";
  const rf = real && real.fields;
  if (inner.type === "lists_get" && rf && rf.VAR) {
    fields = `<field name="VAR">${esc(rf.VAR)}</field>`;
  } else if (inner.type === "get_audios" && rf && rf.sound_id) {
    fields = `<field name="sound_id">${esc(rf.sound_id)}</field>`;
  } else if (inner.type === "get_whole_audios" && rf && rf.sound_id) {
    fields = `<field name="sound_id">${esc(rf.sound_id)}</field>`;
  } else if (inner.type === "math_number") {
    const fm = fields.match(/<field name="NUM"[^>]*>([\s\S]*?)<\/field>/);
    const num = fm ? fm[1] : "0";
    fields = `<field constraints="-Infinity,Infinity,0," allow_text="true" name="NUM">${esc(num)}</field>`;
  }
  const inline = (inner.type === "lists_get" || inner.type === "get_audios" || inner.type === "get_whole_audios") ? ' inline="true"' : "";
  return `<shadow xmlns="http://www.w3.org/1999/xhtml" type="${inner.type}" id="${sid}"${inline} visible="visible">${fields}</shadow>`;
}

// ============================================================ ID 助手
let _c = 0;
function nid() {
  _c++;
  return crypto.randomBytes(11).toString("base64url").slice(0, 18) + _c.toString(36);
}
function uuid() { return crypto.randomUUID(); }

// ============================================================ 音频
const audio = {};
const audio_order = [];
// 注册一段音频（dataURI 或 http(s) URL），返回声音 id，供 play()/stopAud() 引用。
function addAudio(name, url) {
  const id = uuid();
  audio[id] = { id, name, effects: "[]", playback_rate: "1", volume: "1", cdn_url: url, url };
  audio_order.push(id);
  return id;
}

// ============================================================ 变量
const vars = {};     // name -> uuid
const lists = {};    // name -> uuid
const VAR_DEFS = [];
function defVar(name, value = 0, visible = false, pos = null) {
  const id = uuid();
  vars[name] = id;
  VAR_DEFS.push({ id, name, type: "any", value, visible, pos });
  return id;
}
function defList(name) {
  const id = uuid();
  lists[name] = id;
  VAR_DEFS.push({ id, name, type: "list", value: [], visible: false, pos: null });
  return id;
}
// 角色变量（is_global:false + entity）：每个克隆体各持一份，等价于「克隆体专用」。
function defRoleVar(name, actorId, value = 0) {
  const id = uuid();
  vars[name] = id;
  VAR_DEFS.push({ id, name, type: "any", value, visible: false, pos: null, entity: actorId });
  return id;
}

// ============================================================ 积木 DSL（纯函数，无状态）
const N = v => ({ _lit: "num", type: "math_number", fields: { NUM: String(v) } });
// lit(v): 若已是积木节点（传表达式）则原样返回，否则包成数字字面量。
// 让标量助手既能接数字也能接表达式节点，避免「N(N(x))」双重包裹把值变成 [object Object]。
const isNode = v => v && (v._lit || v.type);
const lit = v => isNode(v) ? v : N(v);
const A = id => ({ _lit: "audio", type: "get_audios", fields: { sound_id: id } });
const AW = id => ({ _lit: "audio", type: "get_whole_audios", fields: { sound_id: id } });
const V = name => ({ type: "variables_get", fields: { VAR: vars[name] }, out: true });
// LST：列表引用必须按真实作品的「影子块」模式发射（is_shadow:true + shadows XML 同 id + inline="true"）。
// 旧版返回普通节点 → lists_get 成为 is_shadow:false 的真实子块，与编辑器原生 lists_get 影子模式不符。
// _lit:"list" 走 addBlock 字面分支：自动生成 is_shadow 块 + 同 id 的 inline shadow XML + connections 条目。
const LST = name => ({ _lit: "list", type: "lists_get", fields: { VAR: lists[name] }, out: true });

const setV = (name, val) => ({ type: "variables_set", fields: { VAR: vars[name] }, inputs: { VALUE: val } });
const chgV = (name, val) => ({ type: "change_variable", fields: { valname: vars[name], method: "increase" }, inputs: { n: val } });

const add = (a, b) => ({ type: "math_arithmetic", fields: { OP: "ADD" }, inputs: { A: a, B: b }, out: true });
const sub = (a, b) => ({ type: "math_arithmetic", fields: { OP: "MINUS" }, inputs: { A: a, B: b }, out: true });
const mul = (a, b) => ({ type: "math_arithmetic", fields: { OP: "MULTIPLY" }, inputs: { A: a, B: b }, out: true });
const div = (a, b) => ({ type: "math_arithmetic", fields: { OP: "DIVIDE" }, inputs: { A: a, B: b }, out: true });
const eq = (a, b) => ({ type: "logic_compare", fields: { OP: "EQ" }, inputs: { A: a, B: b }, out: true });
const ne = (a, b) => ({ type: "logic_compare", fields: { OP: "NEQ" }, inputs: { A: a, B: b }, out: true });
const gt = (a, b) => ({ type: "logic_compare", fields: { OP: "GT" }, inputs: { A: a, B: b }, out: true });
const lt = (a, b) => ({ type: "logic_compare", fields: { OP: "LT" }, inputs: { A: a, B: b }, out: true });
const gte = (a, b) => ({ type: "logic_compare", fields: { OP: "GTE" }, inputs: { A: a, B: b }, out: true });
const lte = (a, b) => ({ type: "logic_compare", fields: { OP: "LTE" }, inputs: { A: a, B: b }, out: true });
const and = (a, b) => ({ type: "logic_operation", fields: { OP: "AND" }, inputs: { A: a, B: b }, out: true });
const or = (a, b) => ({ type: "logic_operation", fields: { OP: "OR" }, inputs: { A: a, B: b }, out: true });
const not = a => ({ type: "logic_negate", inputs: { BOOL: a }, out: true });
const abs = a => ({ type: "math_single", fields: { OP: "ABS" }, inputs: { NUM: a }, out: true });
const sqrt = a => ({ type: "math_single", fields: { OP: "ROOT" }, inputs: { NUM: a }, out: true });
// 四舍五入取整（kitten4 的 math_round，OP=ROUND；无保留位数选项，结果恒为整数）
const round = a => ({ type: "math_round", fields: { OP: "ROUND" }, inputs: { NUM: a }, out: true });
// 欧氏步长（逐帧位移真实长度），比曼哈顿更接近实际行程，避免斜向手势采样过早触发。
// 注意：参数传变量名；V() 每次新建节点，同一节点对象用于 A、B 两输入会丢一条边（mul 缺 A）。
const stepLen = (nx, ny) => sqrt(add(mul(V(nx), V(nx)), mul(V(ny), V(ny))));
const rnd = (a, b) => ({ type: "random", inputs: { a: a, b: b }, out: true });
// 取模。注意：kitten4 的类型名是 math_modulo，不是 Scratch 的 math_mod——
// 未注册类型会让编辑器建块抛异常（≥1000 块走异步加载、异常被吞）→ 工作区空白/积木不连接
const mod = (a, b) => ({ type: "math_modulo", inputs: { DIVIDEND: a, DIVISOR: b }, out: true });

const B = (type, fields = {}, inputs = {}, body = null, mutation = "") => ({ type, fields, inputs, body, mutation });
const move = n => B("self_go_forward", {}, { steps: lit(n) });
const moveTo = (x, y) => B("self_move_to", {}, { x: lit(x), y: lit(y) });
const turn = deg => B("self_rotate", { direction: "left" }, { degrees: lit(deg) });
const chgCoord = (axis, dir, val) => B("self_change_coordinate", { coordinary: axis, increase: dir }, { value: lit(val) });
const getX = () => ({ type: "get_3", fields: { sprite: "__self", attribute: "0" }, out: true });
const getY = () => ({ type: "get_3", fields: { sprite: "__self", attribute: "1" }, out: true });
const mouseX = () => ({ type: "get_mouse_info", fields: { position: "x" }, out: true });
const mouseY = () => ({ type: "get_mouse_info", fields: { position: "y" }, out: true });
const mDown = () => ({ type: "mouse_down", fields: { mouse_event_type: "down" }, out: true });
const mirror = actorId => B("mirror", { sprite: actorId });
const dispose = () => B("dispose_clone");
const cloneIdx = () => ({ type: "get_current_clone_index", out: true });
const cloneNum = actorId => ({ type: "get_clone_num", fields: { sprite: actorId }, out: true });
const appear = () => B("self_appear");
const hide = () => B("self_disappear");
const costume = i => B("set_costume_by_index", {}, { index: lit(i) });
const fade = t => B("self_gradually_disappear", {}, { time: lit(t) });
const scaleUp = v => B("self_change_scale_2", { increase: "increase" }, { scale: lit(v) });
const shake = t => B("self_shake", {}, { time: lit(t) });
const penDown = () => B("self_pen_down");
const penUp = () => B("self_pen_up");
const penColor = c => B("self_set_pen_color", { color: lit(c) });
const penSize = s => B("self_set_pen_size", {}, { size: N(s) });
const clearDraw = () => B("clear_drawing");
const play = id => B("play_audio_2", {}, { audio: A(id) });
const stopAud = id => B("stop_audio_2", {}, { audio: AW(id) });
const listAdd = (l, v) => B("lists_append", {}, { VAR: LST(l), VALUE: v });
const listSet = (l, i, v) => B("lists_replace", {}, { VAR: LST(l), INDEX: lit(i), VALUE: v });
const listGet = (l, i) => ({ type: "lists_get_value", inputs: { VAR: LST(l), INDEX: lit(i) }, out: true });
const listLen = l => ({ type: "lists_length", inputs: { VAR: LST(l) }, out: true });
const wait = t => B("wait", {}, { time: lit(t) });
const forever = body => B("repeat_forever", {}, {}, { DO: chain(...body) });
const repeatN = (t, body) => B("repeat_n_times", {}, { times: t }, { DO: chain(...body) });
// 切换「背景造型」也用 set_costume_by_index（与角色造型同一积木，1 基）。index 1 基。
const setScene = i => B("set_costume_by_index", {}, { index: lit(i) });
const imageStamp = () => B("image_stamp");
// warp / 一步执行：内部嵌套循环同帧跑完，再等 1 帧。用于克隆体初始化原子化。
// 注意：warp 只能包「有界」循环；内部 repeat_forever 会在「一帧」内无法展开 → VM/编辑器会卡死。
const warp = body => B("warp", {}, {}, { DO: chain(...body) });

// 计时器（实证自 kitten.js）：
//   get_timer 读取「虚拟秒」，但必须先用 set_timer_state(start) 启动计时，否则恒为 0。
//   show_hide_timer 控制编辑器默认那个丑陋的计时器 UI（默认空作品会自动注入 hide+start，
//   手写作品不会 → 不调用就一直显示默认计时器）。
//   reset_timer / set_timer_state(reset) 归零并 set_time("0.00")。
const getTimer = () => ({ type: "get_timer", out: true });
const startTimer = () => B("set_timer_state", { actions: "start" });
const stopTimer = () => B("set_timer_state", { actions: "stop" });
const resetTimer = () => B("set_timer_state", { actions: "reset" });
const hideTimer = () => B("show_hide_timer", { state: "hide" });
const showTimer = () => B("show_hide_timer", { state: "show" });

// controls_if：铁律 7 —— 它是 if/else-if（首个命中即返回），不是独立多 if。
// branches 形如 [{cond, body}, {cond, body}, {cond:null, body}]，高阈值分支务必排在前面。
function ifChain(branches) {
  const inputs = {}, body = {};
  let nIf = 0;
  for (const br of branches) {
    if (br.cond) { inputs["IF" + nIf] = br.cond; body["DO" + nIf] = chain(...(br.body || [])); nIf++; }
    else { body["ELSE"] = chain(...(br.body || [])); }
  }
  const nElseIf = nIf - 1;
  const hasElse = branches.some(b => !b.cond);
  let mutation = "";
  if (nElseIf > 0 || hasElse) {
    const parts = [];
    if (nElseIf > 0) parts.push(`elseif="${nElseIf}"`);
    if (hasElse) parts.push('else="1"');
    mutation = `<mutation xmlns="http://www.w3.org/1999/xhtml" ${parts.join(" ")}></mutation>`;
  }
  return { type: "controls_if", fields: {}, inputs, body, mutation };
}

function chain(...stmts) {
  const list = stmts.filter(Boolean);
  for (let i = 0; i < list.length - 1; i++) list[i].next = list[i + 1];
  return list[0] || null;
}
const onStart = (...body) => ({ type: "start_on_click", fields: {}, inputs: {}, body: null, mutation: "", next: chain(...body) });
const onClone = (...body) => ({ type: "start_as_a_mirror", fields: {}, inputs: {}, body: { DO: chain(...body) }, mutation: "" });

// ★ 铁律 11（2026-10-23 血泪）：函数「定义」PARAMS 槽上的参数块，与函数体里「引用」参数，是两种不同类型。
//   定义槽 → procedures_2_stable_parameter（fields 带 param_default_value）
//   体引用 → procedures_2_parameter（fields 只有 param_name）
//   写反的症状：编辑器不报错、背景/变量正常，但积木栏消失、脚本区空白，整个文件打不开；
//   且「无参数的函数」所在的文件能开、「有参数的函数」所在的文件打不开（100% 吻合）。
const defParam = name => ({ type: "procedures_2_stable_parameter", fields: { param_name: name, param_default_value: "" }, out: true });
const paramRef = name => ({ type: "procedures_2_parameter", fields: { param_name: name }, out: true });

// ============================================================ Emitter
function esc(s) { return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;"); }

function baseDef(b, loc) {
  return {
    type: b.type, id: b.id, is_shadow: false, collapsed: false, disabled: false,
    deletable: true, movable: true, editable: true, visible: "visible",
    location: loc, shadows: {}, fields: { ...(b.fields || {}) },
    field_constraints: {}, field_extra_attr: {}, comment: null,
    mutation: b.mutation || "", is_output: b.out ? true : false, parent_id: null,
  };
}

function addBlock(b, blocks, conns, loc) {
  if (!b.id) b.id = nid();
  const id = b.id;
  blocks[id] = baseDef(b, loc);
  if (!conns[id]) conns[id] = {};
  // value 输入
  for (const [name, val] of Object.entries(b.inputs || {})) {
    if (val == null) continue;
    if (val._lit) {
      if (!val.id) val.id = nid();
      // 自定义函数调用（procedures_2_call*）的 ARG 输入：字面量必须转成 default_value 影子块。
      // 真实作品铁证（球体物理）：math_number 作为 call ARG 子块 0 例；数字实参一律以
      // default_value{TEXT} 影子呈现——子块 is_shadow:true + shadows XML 同 id + has_been_edited=true。
      let vnode = val;
      if (/^procedures_2_call/.test(b.type) && /^ARG\d+$/.test(name) && vnode.type === "math_number") {
        vnode = { _lit: "defval", type: "default_value", fields: { TEXT: String(vnode.fields.NUM) }, id: vnode.id, out: true };
      }
      const sdef = baseDef(vnode, [0, 0]);
      sdef.is_shadow = true;
      // deletable 对齐真实作品：球体物理中 deletable=false 的块为 0，影子块全部 true
      sdef.deletable = true;
      // is_output：reporter 影子（lists_get/text/audio/default_value）为 true；math_number 真实作品两种都有（null 合法）
      sdef.is_output = vnode.type === "math_number" ? null : true;
      if (vnode.type === "math_number") sdef.field_constraints = { NUM: { min: null, max: null, precision: 0, mod: null } };
      if (vnode.type === "default_value") sdef.field_extra_attr = { TEXT: { has_been_edited: true } };
      blocks[vnode.id] = sdef;
      // ★ 铁律 8（新增，血泪）：每个块——包括叶子影子块——都必须有 connections 条目（无子块则 {}）。
      // 旧版只给「有子块的父块」建条目 → 268 个 math_number 叶子影子块只有 blocks 没有 connections →
      // 编辑器按 connections 建块树时子块未注册 → 整个积木区加载失败（表现为积木栏消失、一动就出错）。
      if (!conns[vnode.id]) conns[vnode.id] = {};
      const flds = Object.entries(vnode.fields).map(([k, v]) =>
        vnode.type === "math_number"
          ? `<field constraints="-Infinity,Infinity,0," allow_text="true" name="${k}">${esc(v)}</field>`
          : vnode.type === "default_value"
            ? `<field has_been_edited="true" name="${k}">${esc(v)}</field>`
            : `<field name="${k}">${esc(v)}</field>`).join("");
      const litInline = (vnode.type === "get_audios" || vnode.type === "get_whole_audios" || vnode.type === "lists_get") ? ' inline="true"' : "";
      blocks[id].shadows[name] = `<shadow xmlns="http://www.w3.org/1999/xhtml" type="${vnode.type}" id="${vnode.id}"${litInline} visible="visible">${flds}</shadow>`;
      conns[id][vnode.id] = { type: "input", input_type: "value", input_name: name };
      blocks[vnode.id].parent_id = id;
    } else {
      addBlock(val, blocks, conns, [0, 0]);
      conns[id][val.id] = { type: "input", input_type: "value", input_name: name };
      blocks[val.id].parent_id = id;
      // 真实 reporter 占据输入：保留默认 shadow 模板（phantom id）
      blocks[id].shadows[name] = shadowTemplate(b.type, name, val);
    }
  }
  // 语句体：编辑器为每个命名语句输入都写 ""（铁律 5）
  for (const name of Object.keys(b.body || {})) {
    blocks[id].shadows[name] = "";
  }
  // controls_if 的 dummy 输入（加 else 按钮 / else 标签），正如真实作品
  if (b.type === "controls_if") {
    if (b.body && b.body.ELSE) blocks[id].shadows.ELSE_TEXT = "";
    else blocks[id].shadows.EXTRA_ADD_ELSE = "";
  }
  // 语句体
  for (const [name, c] of Object.entries(b.body || {})) {
    if (!c) continue;
    const first = emitChain(c, blocks, conns, [loc[0] + 60, loc[1] + 50]);
    if (first) {
      conns[id][first] = { type: "input", input_type: "statement", input_name: name };
      blocks[first].parent_id = id;
    }
  }
  return id;
}

function emitChain(start, blocks, conns, loc) {
  let cur = start, y = loc[1], prevId = null, firstId = null;
  while (cur) {
    const id = addBlock(cur, blocks, conns, [loc[0], y]);
    if (prevId) {
      conns[prevId][id] = { type: "next" };
      blocks[id].parent_id = prevId;
    } else firstId = id;
    prevId = id;
    y += 40;
    cur = cur.next;
  }
  return firstId; // 语句输入连到链首块（铁律 2：emitChain 必须返回链首）
}

function emitScript(hat, bdj, startY, withPenLayer = true) {
  const blocks = bdj.blocks, conns = bdj.connections;
  // 每个角色脚本首行插 set_layer_with_pen(below)：kitten4 默认角色在画笔图层上方，会挡住笔迹。
  // 铁律 6 + 修正：背景（真正 scene）永远最底层、无画笔功能，绝不能下移 → withPenLayer=false。
  if (withPenLayer) {
    const PEN_LAYER = { type: "set_layer_with_pen", fields: { position: "below" } };
    if (hat.body && hat.body.DO) { PEN_LAYER.next = hat.body.DO; hat.body.DO = PEN_LAYER; }
    else if (hat.next) { PEN_LAYER.next = hat.next; hat.next = PEN_LAYER; }
  }
  const id = addBlock(hat, blocks, conns, [20, startY]);
  if (hat.next) {
    let cur = hat.next, y = startY + 40, prev = id;
    while (cur) {
      const cid = addBlock(cur, blocks, conns, [20, y]);
      conns[prev][cid] = { type: "next" };
      blocks[cid].parent_id = prev;
      prev = cid;
      y += 40;
      cur = cur.next;
    }
  }
  return id;
}

// ============================================================ 角色 / 场景
let SCENE_ID = null;
let SCENE_BDJ = null;
let SCENE_STYLE_IDS = [];   // 场景自持的背景造型 id 列表（scene.styles 非空，bcm4gen 格式修正 1）
const styles = {};
const actors = {};
const groups = {};
const actorOrder = [];

function defStyle(name, url, cdn) {
  const id = uuid();
  // rotate_center_painter 必须存在：编辑器解析造型时读该字段（缺字段 → 作品无法打开，bcm4gen 格式修正 2）
  // cdn 可显式指定（如复用官方空白背景的 CDN 地址）；默认与 url 相同。
  styles[id] = { id, name, rotate_center: { x: 0, y: 0 }, rotate_center_painter: { x: 0, y: 0 }, url, cdn_url: cdn || url, pivot: { x: 0, y: 0 }, adaptive: false };
  return id;
}
// 1x1 透明 PNG，用于隐藏/不可见角色
const BLANK = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==";

function defActor(name, styleIds, opts = {}) {
  const id = uuid();
  const groupId = uuid();
  actorOrder.push(id);
  actors[id] = {
    name, x: opts.x || 0, y: opts.y || 0, scale: opts.scale || 100,
    rotation: 0, rotation_type: 0, id,
    draggable: false, lock: false, user_change_r_c: false,
    scene: SCENE_ID, editable_in_tuition_mode: true,
    workspace_offset: { x: 0, y: 0 },
    block_data_json: { blocks: {}, connections: {}, comments: {} },
    visible: opts.visible !== false,
    styles: styleIds, current_style_id: styleIds[0],
  };
  groups[groupId] = { id: groupId, name: "", is_fold: false, is_group: false, actors: [id], scene: SCENE_ID, visible: true };
  return id;
}

// 真正的编辑器背景（scene）：永远最底层，包含角色与画笔之下，无画笔功能。
// 背景造型切换逻辑写在这里，而非做成「角色」。铁律 6 修正。
function defScene(name, styleIds) {
  SCENE_ID = uuid();
  SCENE_BDJ = { blocks: {}, connections: {}, comments: {} };
  // 场景必须持有并引用自己的背景造型：styles 非空且 current_style_id 指向其中一项。
  // 旧版把 styleIds 丢弃 → scene.styles=[] + current 悬空 → 编辑器拒绝打开（bcm4gen 格式修正 1）。
  if (!styleIds || !styleIds.length) styleIds = [defStyle(name || "背景", BLANK)];
  SCENE_STYLE_IDS = styleIds.slice();
  return SCENE_ID;
}

// 便利：给某 actor 写一个「当角色被点击/绿旗」脚本
function script(actorId, hat, startY = 50, withPenLayer = true) {
  return emitScript(hat, actors[actorId].block_data_json, startY, withPenLayer);
}
// 便利：给某 actor 写一个「当作为克隆体启动时」脚本（start_as_a_mirror 只有 DO 输入）
function cloneScript(actorId, body, startY = 50) {
  const hat = onClone(...body);
  hat.body = { DO: chain(...(body || [])) };
  return emitScript(hat, actors[actorId].block_data_json, startY, true);
}
// 便利：给背景写脚本（无画笔图层下移）
function sceneScript(hat, startY = 50) {
  return emitScript(hat, SCENE_BDJ, startY, false);
}

// ============================================================ 变量收集（可被外部模板生成器复用）
function gatherVariables() {
  const variables = {};
  const variable_order = [];
  for (const d of VAR_DEFS) {
    const isRole = d.entity != null;
    variables[d.id] = {
      id: d.id, type: d.type,
      is_global: !isRole, scale: d.visible ? 0.9 : 1, theme: "common",
      current_entity: isRole ? d.entity : undefined,
      offset: { x: 0, y: 0 }, value: d.value, name: d.name,
      position: d.pos || { x: -470, y: 350 }, visible: d.visible,
    };
    if (!isRole) variable_order.push(d.id);
  }
  return { variables, variable_order };
}

// ============================================================ 组装项目
function build(projectName = "未命名作品") {
  if (!SCENE_ID) defScene("背景", []);
  const sceneTable = {
    [SCENE_ID]: {
      id: SCENE_ID,
      current_style_id: SCENE_STYLE_IDS[0],
      name: "背景",
      styles: SCENE_STYLE_IDS.slice(),
      actors: [],
      x: 0, y: 0, scale: 100, rotation: 0, rotation_type: 0,
      draggable: false, visible: true,
      screen_name: "屏幕",
      group_order: Object.keys(groups).reverse(),
      block_data_json: SCENE_BDJ || { blocks: {}, connections: {}, comments: {} },
      workspace_offset: { x: 0, y: 0 },
    },
  };

  const { variables, variable_order } = gatherVariables();

  return {
    hidden_toolbox: { toolbox: [], blocks: [] },
    work_source_label: 1,
    codemao_value: 333123015,
    sample_id: "",
    version: 25,
    application_version: "4.11.20",
    work_type: "KITTEN",
    size: { width: 1280, height: 720 },
    type: 1,
    project_name: projectName,
    theatre: {
      // 不写 current_entity / current_scene / style_collections：真实作品（4.11.20 保存）无这三键，
      // 多写反而触发编辑器严格校验失败（bcm4gen 格式修正 3）
      scenes_order: [SCENE_ID],
      scenes: sceneTable,
      actors,
      videos: {},
      styles,
      groups,
      timer: {},
    },
    variables,
    variable_order,
    cloud_variables: {},
    audio,
    audio_order,
    midimusic: [],
    midi_order: [],
    matrix: {},
    models: {},
    toolbox: {
      // 键集与取值对齐真实作品（缺 lang/cellphone/pen 三键 → 编辑器打不开，bcm4gen 格式修正 4）
      lang: false, cellphone: false, pen: false,
      current_type: "procedure", physics: false, physics2: false,
      block_ai_classification: false, block_ai_game: false,
      block_hardware_arduino: false, block_hardware_weeemake: false, block_hardware_microbit: false,
      cloud_variable: true, cloud_list: false,
      advanced: true, camera: false, video: false, wood: false,
      cognitive: false, ai_lab: false, midimusic: false, mobile_control: false,
    },
    toolbox_order: ["event", "control", "action", "appearance", "audio", "pen", "sensing", "operator", "data", "data", "procedure", "mobile_control", "physic", "physics2", "cloud_variable", "cloud_list", "advanced", "ai_lab", "ai_game", "cognitive", "camera", "video", "wood", "arduino", "weeemake", "microbit", "ai", "ml", "edu"],
    last_toolbox_order: ["event", "control", "action", "appearance", "audio", "pen", "sensing", "operator", "variable", "list", "procedure", "mobile_control", "physics", "physics2", "cloud_variable", "cloud_list", "advanced", "ai_lab", "ai_game", "cognitive", "camera", "video", "wood", "arduino", "weeemake", "microbit", "ai", "ml", "edu"],
    hardware_type: "",
    device_widget_type: null,
    is_partial: false,
    ai_lab: {},
    broadcasts: {},
    painter: { color: [] },
  };
}

function write(outPath, projectName) {
  const project = build(projectName);
  // 铁律 1：绝不能写顶层 compile_result，否则编辑器只读它、忽略 block_data_json → 脚本区空白。
  if ("compile_result" in project) delete project.compile_result;
  fs.writeFileSync(outPath, JSON.stringify(project), "utf8");
  const total = Object.values(actors).reduce((s, a) => s + Object.keys(a.block_data_json.blocks).length, 0)
    + Object.keys((SCENE_BDJ || { blocks: {} }).blocks).length;
  console.log(`Wrote ${outPath} (${(fs.statSync(outPath).size / 1024).toFixed(1)} KB)`);
  console.log(`  actors: ${Object.keys(actors).length}, styles: ${Object.keys(styles).length}, variables: ${Object.keys(project.variables).length}, blocks: ${total}`);
  return project;
}

// 清空全部单例状态（同进程多次生成时用）
function reset() {
  DEF_XML = {};
  for (const k of Object.keys(audio)) delete audio[k];
  audio_order.length = 0;
  for (const k of Object.keys(vars)) delete vars[k];
  for (const k of Object.keys(lists)) delete lists[k];
  VAR_DEFS.length = 0;
  SCENE_ID = null; SCENE_BDJ = null; SCENE_STYLE_IDS = [];
  for (const k of Object.keys(styles)) delete styles[k];
  for (const k of Object.keys(actors)) delete actors[k];
  for (const k of Object.keys(groups)) delete groups[k];
  actorOrder.length = 0;
  _c = 0;
}

module.exports = {
  loadDefs, shadowTemplate, nid, uuid, addAudio,
  defVar, defList, defRoleVar,
  N, A, AW, V, LST, setV, chgV,
  add, sub, mul, div, eq, ne, gt, lt, gte, lte, and, or, not, abs, sqrt, round, stepLen, rnd, mod,
  B, move, moveTo, turn, chgCoord, getX, getY, mouseX, mouseY, mDown, mirror, dispose,
  cloneIdx, cloneNum, appear, hide, costume, fade, scaleUp, shake,
  penDown, penUp, penColor, penSize, clearDraw, play, stopAud,
  listAdd, listSet, listGet, listLen, wait, forever, repeatN, setScene, imageStamp, warp,
  getTimer, startTimer, stopTimer, resetTimer, hideTimer, showTimer,
  ifChain, chain, onStart, onClone, defParam, paramRef,
  defStyle, defActor, defScene, script, cloneScript, sceneScript, emitScript,
  build, write, reset, gatherVariables,
  get state() { return { vars, lists, styles, actors, groups, audio, audio_order, SCENE_ID, SCENE_BDJ, actorOrder }; },
};
