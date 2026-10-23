#!/usr/bin/env node
"use strict";
/**
 * poorphy_content.js — PoorPhy 物理沙盒的「纯内容构建」模块（不写文件）。
 * 把 gen_poorphy.js 的全部积木/变量/函数逻辑抽出来，供两种生成器复用：
 *   - gen_poorphy.js      : 用 bcm4gen 从零搭建信封
 *   - gen_poorphy_tmpl.js  : 把内容挂载到「球体物理.bcm4」已验证的信封上
 * 约定：调用方先 require bcm4gen，loadDefs，再把 K 传进来即可。
 */
module.exports.build = function (K) {
// ============================================================ 常量
const NB = 6;          // 初始刚体数（= BODIES 行数；运行时按 G 键可追加到 NB_MAX）
const NB_MAX = 16;     // 刚体容量上限：所有状态/顶点/对列表按它预扩展（16×15/2=120 对）
const SPAWN_R = 34;    // 新刚体半径（新增参数只有「边数」，半径固定）
const EDGE_MIN = 3, EDGE_MAX = 8;  // 边数循环范围；8=圆=MAXV 槽位上限（超出会串到邻体顶点槽）
const MAXV = 8;        // 每刚体顶点槽位数（圆 = 8 边形）
const ROOM_X = 600, ROOM_Y = 300;
const GRAV = 0.5;      // 每帧重力加速度
const DAMP_V = 0.999, DAMP_W = 0.995;
const REST_WALL = 0.8;   // 墙体法向恢复系数
const ITER = 3;        // 速度求解迭代次数
const E_REST = 0.1;    // 回弹系数
const MU = 0.3;        // 摩擦系数
const SLOP = 0.5, BETA = 0.4;
const V_MAX = 40;
// 角速度上限（弧度/帧）。刚AV 内部一律用「弧度/帧」，积分到 刚角（度）时再乘 RAD2DEG。
const W_MAX = 0.15;
// ★ 角度单位换算常数（kitten4 的 math_trig 是角度制：Math.cos(i/180*Math.PI)）
//   约定：刚角 = 度（喂给 COS/SIN）；刚AV = 弧度/帧（喂给 ω×r 叉乘与 I=½mr² 惯量）。
//   历史事故：曾把 刚AV 当「度/帧」直接累加进 刚角 → 碰撞产生的自转被压缩 57.3 倍 → 肉眼完全看不到旋转。
const DEG2RAD = 0.017453292519943295;   // π/180
const RAD2DEG = 57.29577951308232;     // 180/π
const COLOR_CIRCLE = "#4FC3F7", COLOR_POLY = "#FFB74D", COLOR_WALL = "#9E9E9E";
// 背景 = 编辑器官方空白场景 SVG（1x1 透明 PNG 会被显示为「造型损坏」）。
// cdn 用官方静态地址（与空白作品.bcm4 完全一致）。
const BLANK_BG = "data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHhtbG5zOnhsaW5rPSJodHRwOi8vd3d3LnczLm9yZy8xOTk5L3hsaW5rIiB3aWR0aD0iNjE5cHgiIGlzRnJvbUJhc2VJbnBhaW50ZXIiIHRydWUiIGhlaWdodD0iODk5Ljk5OTk5OTk5OTk5OTlweCIgZGF0YS1wYXBlci1kYXRhPSJ7J3F1b3Q7dmVyc2lvbiZxdW90OzomcXVvdDsxLjAmcXVvdDt9Ij48ZyBkYXRhLXBhcGVyLWRhdGE9InsmcXVvdDtpc1dvcmtMYXllciZxdW90Ozp0cnVlLCZxdW90O2JhY2tncm91bmRDb2xvciZxdW90OzomcXVvdDsjZmZmZmZmJnF1b3Q7fSIgZmlsbD0iI2ZmZmZmZiIgZmlsbC1ydWxlPSJub256ZXJvIiBzdHJva2U9Im5vbmUiIHN0cm9rZS13aWR0aD0iMSIgc3Ryb2tlLWxpbmVjYXA9ImJ1dHQiIHN0cm9rZS1saW5lam9pbj0ibWl0ZXIiIHN0cm9rZS1taXRlcmxpbWl0PSIxMCIgc3Ryb2tlLWRhc2hhcnJheT0iIiBzdHJva2UtZGFzaG9mZnNldD0iMCIgZm9udC1mYW1pbHk9Im5vbmUiIGZvbnQtd2VpZ2h0PSJub25lIiBmb250LXNpemU9Im5vbmUiIHRleHQtYW5jaG9yPSJub25lIiBzdHlsZT0ibWl4LWJsZW5kLW1vZGUgbm9ybWFsIiB2aXNpYmlsaXR5PSJ2aXNpYmxlIiB0cmFuc2Zvcm09InNjYWxlKDEuMjQ4NzYwMzMwNTc4NTEyNCkiIHRyYW5zbGF0ZSgtMjI4LC0xKSI+PGRlZiBkZWZzRnJvbT0iS2l0dGVuUGFpbnRlciIvPjxyZWN0IHg9IjIyNy42MTExMSIgeT0iMSIgd2lkdGg9IjQxNi43Nzc3OCIgaGVpZ2h0PSI2MDUiIGRhdGEtcGFwZXItZGF0YT0ieyZxdW90O2lzQmFja2dyb3VuZFBsYWNlaG9sZGVyJnF1b3Q7OnRydWV9Ii8+PC9nPjwvc3ZnPg==";
const BLANK_BG_CDN = "https://static.codemao.cn/kitten/B1iottffw";
// 角色造型 = 28px 蓝点（可见=可点击=start_on_click 能触发；不可见 1px 角色无法点击）。
const DOT_SVG = "data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyOCIgaGVpZ2h0PSIyOCIgdmlld0JveD0iMCAwIDI4IDI4Ij48Y2lyY2xlIGN4PSIxNCIgY3k9IjE0IiByPSIxMSIgZmlsbD0iIzRGQzNGNyIgZmlsbC1vcGFjaXR5PSIwLjg1IiBzdHJva2U9IiMwMjg4RDEiIHN0cm9rZS13aWR0aD0iMi41Ii8+PC9zdmc+";

// 刚体初始规格：x, y, r, 边数(8=圆), 初始角(度), 初始角速度(度/帧), vx, vy（确定性，便于 VM 对比）
const BODIES = [
  [-380, 180, 38, 8,   0,  1.5,  1.2,  0.0],
  [-120, 240, 34, 8,   0, -1.2,  0.8,  0.0],
  [ 140, 150, 44, 4,  25,  2.6, -0.6,  0.0],
  [ 380, 220, 40, 5,  10, -2.0, -1.0,  0.0],
  [-260,  60, 36, 6,   0,  1.8,  0.5,  0.5],
  [ 240,  40, 42, 8,   0,  1.1, -0.4,  0.3],
];
const MAX_PAIRS = NB_MAX * (NB_MAX - 1) / 2; // 120（按容量上限预扩展对列表）

// ============================================================ 扩展积木助手
// 三角函数（kitten4 为角度制，已从真实作品 ROUND(ATAN(dy/dx)) 模式证实）
const trig = (op, num) => ({ type: "math_trig", fields: { OP: op }, inputs: { NUM: num }, out: true });
const sinD = num => trig("SIN", num);
const cosD = num => trig("COS", num);
// 按键轮询（真实作品结构：fields{key_event_type, key}，布尔 reporter）
const keyDown = key => ({ type: "check_key", fields: { key_event_type: "down", key: String(key) }, out: true });
// 画笔颜色是字段（十六进制字符串），不能走 lit()
const penColorHex = h => K.B("self_set_pen_color", { color: h });
const neg = a => K.sub(K.N(0), a);

// ---- 自定义函数（procedures_2） ----
const PROCS = {}; // name -> { id, params }
function param(name) { return { type: "procedures_2_parameter", fields: { param_name: name }, out: true }; }
/** ★ 定义块 PARAMS 槽上的参数块必须是 procedures_2_stable_parameter（不是 procedures_2_parameter）。
 *  规范来源：ts2kitten-main/blockly.js 头注释 + 真实作品 球体物理（能打开）实测——
 *    定义上的参数块 = procedures_2_stable_parameter，fields{param_name, param_default_value:""}
 *    函数体内引用参数 = procedures_2_parameter，fields{param_name}
 *  写错会导致编辑器反序列化崩溃：凡是带参数的函数定义所在文件一律打不开（积木栏消失）。 */
function defParam(name) {
  return { type: "procedures_2_stable_parameter", fields: { param_name: name, param_default_value: "" }, out: true };
}
function retProc(valueExpr) {
  return { type: "procedures_2_return_value", fields: {}, inputs: { VALUE: valueExpr }, body: null, mutation: "" };
}
/** 发射函数定义。body 为语句数组。 */
function defProc(name, params, body, startY) {
  const node = {
    type: "procedures_2_defnoreturn",
    fields: { NAME: name },
    inputs: {},
    body: { STACK: K.chain(...(body || [])) },
    mutation: "",
  };
  params.forEach((p, idx) => { node.inputs["PARAMS" + idx] = defParam(p); });
  const id = K.script(ENGINE, node, startY, false);
  PROCS[name] = { id, params };
  return id;
}
/** 调用（语句） */
function call(name, args) {
  const node = { type: "procedures_2_callnoreturn", fields: { NAME: name }, inputs: {}, mutation: "" };
  (args || []).forEach((a, i) => { node.inputs["ARG" + i] = a; });
  return node;
}
/** 调用（值） */
function callV(name, args) {
  const node = { type: "procedures_2_callreturn", fields: { NAME: name }, inputs: {}, out: true, mutation: "" };
  (args || []).forEach((a, i) => { node.inputs["ARG" + i] = a; });
  return node;
}
const mathNumShadow = () => '<shadow xmlns="http://www.w3.org/1999/xhtml" type="math_number" id="'
  + K.nid() + '" visible="visible"><field constraints="-Infinity,Infinity,0," name="NUM">0</field></shadow>';
const defValShadow = () => '<shadow xmlns="http://www.w3.org/1999/xhtml" type="default_value" id="'
  + K.nid() + '" visible="visible"><field has_been_edited="false" name="TEXT">0</field></shadow>';
const esc = s => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

/** 发射完成后统一补 procedures 块的 shadows/mutation（铁律 5 + 真实作品结构）。 */
function patchProcedures() {
  const bdjs = [];
  for (const a of Object.values(K.state.actors)) bdjs.push(a.block_data_json);
  if (K.state.SCENE_BDJ) bdjs.push(K.state.SCENE_BDJ);
  let nDef = 0, nCall = 0, nRet = 0;
  for (const bdj of bdjs) {
    for (const blk of Object.values(bdj.blocks)) {
      const conns = bdj.connections[blk.id] || {};
      const countPref = pre => Object.values(conns)
        .filter(c => String(c.input_name || "").startsWith(pre)).length;
      if (blk.type === "procedures_2_defnoreturn") {
        const k = countPref("PARAMS");
        const sh = { PROCEDURES_2_DEFNORETURN_DEFINE: "", PROCEDURES_2_DEFNORETURN_MUTATOR: "", STACK: "" };
        for (let n = 0; n < k; n++) sh["PARAMS" + n] = mathNumShadow();
        blk.shadows = sh;
        let mut = '<mutation xmlns="http://www.w3.org/1999/xhtml">';
        for (let n = 0; n < k; n++) mut += '<arg name="PARAMS' + n + '"></arg>';
        blk.mutation = mut + "</mutation>";
        nDef++;
      } else if (blk.type === "procedures_2_return_value") {
        blk.shadows = { PROCEDURES_2_DEFRETURN_RETURN: "", VALUE: mathNumShadow(), PROCEDURES_2_DEFRETURN_MUTATOR: "" };
        blk.mutation = '<mutation xmlns="http://www.w3.org/1999/xhtml" items="1"></mutation>';
        nRet++;
      } else if (blk.type === "procedures_2_callnoreturn" || blk.type === "procedures_2_callreturn") {
        const k = countPref("ARG");
        const def = PROCS[blk.fields.NAME];
        if (!def) throw new Error("call to undefined proc: " + blk.fields.NAME);
        const sh = { NAME: "" };
        for (let n = 0; n < k; n++) {
          const iname = "ARG" + n;
          // 该 ARG 已被真实子块占据时保留 addBlock 写好的 XML：
          //  - 字面量 → default_value 同 id XML（真实作品模式，math_number 不做 ARG 子块）
          //  - 普通 reporter → ""（下面补幻影 default_value 模板）
          // 无子块的 ARG 才用幻影模板（用户点击即可填数）。
          const hasChild = Object.values(conns).some(c => c.input_name === iname);
          sh[iname] = hasChild && blk.shadows[iname] ? blk.shadows[iname] : defValShadow();
        }
        blk.shadows = sh;
        let mut = '<mutation xmlns="http://www.w3.org/1999/xhtml" name="' + esc(blk.fields.NAME)
          + '" def_id="' + def.id + '">';
        for (const p of def.params) mut += '<procedures_2_parameter_shadow name="' + esc(p) + '" value="0"></procedures_2_parameter_shadow>';
        blk.mutation = mut + "</mutation>";
        nCall++;
      }
    }
  }
  return { nDef, nCall, nRet };
}

// ============================================================ 场景 / 角色 / 变量
const bgStyle = K.defStyle("bg", BLANK_BG, BLANK_BG_CDN);
K.defScene("背景", [bgStyle]);
// 角色必须 visible:true —— 不可见角色无法被点击，start_on_click 永远不触发（「不能运行」根因之一）。
const ENGINE = K.defActor("物理", [K.defStyle("dot", DOT_SVG)], { x: 0, y: 0, scale: 100, visible: true });

// 列表（物理状态）
["初X", "初Y", "初VX", "初VY", "初角", "初AV",
 "刚X", "刚Y", "刚VX", "刚VY", "刚角", "刚AV", "刚R", "边数", "刚质量", "刚反质量", "刚反惯量",
 "顶X", "顶Y", "对A", "对B", "对NX", "对NY", "对深"].forEach(n => K.defList(n));

// 标量（帧数/暂停单独声明为可见变量，避免同名双变量）
// ★★★ kitten4 变量是「全局」的，函数没有局部作用域（只有参数是栈帧隔离的）★★★
//    因此每个函数的循环计数器与暂存变量必须用【互不相同】的名字，
//    否则嵌套调用（SAT→投影 / 解算冲量→支撑点）会互相踩踏全局变量。
//    历史事故：SAT 用全局 k 扫边，投影(i) 内部也用全局 k → k 被踩成 边数+2
//    → 边法线(j,k) 算出的槽位越界 → 「列表第51项不存在」崩溃 + SAT 轴全错 → 漏碰撞。
//    命名规范：<用途> + <函数后缀>（SAT/PROJ/EDG/SUP/WV/STEP/RN/IN/RS/NR/RES）。
//    —— 跨函数共享的只有「输出通道」类变量（法线XEDG / 投小PROJ / 支点XSUP / sat深SAT …），
//       它们只被唯一生产者写、唯一消费者读，且生产者在返回前不被打断 → 安全。
["单步", "对数", "抓取", "上鼠标", "上空格", "上S", "上R",
 "鼠X", "鼠Y", "按下", "空现", "S现", "R现",
 // —— 物理步进 ——
 "iSTEP", "jSTEP", "pSTEP", "qSTEP", "距2STEP", "径和STEP", "速率STEP",
 // —— SAT ——
 "kSAT", "暂SAT", "暂2SAT", "重叠SAT", "分离SAT", "最小深SAT", "法XSAT", "法YSAT", "sat深SAT",
 "投小ASAT", "投大ASAT", "投小BSAT", "投大BSAT",
 // —— 投影 ——
 "kPROJ", "槽PROJ", "暂PROJ", "投小PROJ", "投大PROJ",
 // —— 边法线 ——
 "槽EDG", "槽2EDG", "边XEDG", "边YEDG", "边长EDG", "法线XEDG", "法线YEDG",
 // —— 支撑点 ——
 "kSUP", "槽SUP", "暂SUP", "支最佳SUP", "支点XSUP", "支点YSUP",
 // —— 解算冲量 ——
 "甲点X", "甲点Y", "乙点X", "乙点Y", "触X", "触Y",
 "臂AX", "臂AY", "臂BX", "臂BY", "速AX", "速AY", "速BX", "速BY", "相X", "相Y", "法速", "弹性",
 "法臂A", "法臂B", "分母", "冲量", "切X", "切Y", "切臂A", "切臂B",
 "切分母", "切速", "切量", "限量", "冲X", "冲Y", "修正",
 // —— 世界顶点 ——
 "kWV", "槽WV", "步角WV", "当前角WV",
 // —— 渲染 / 初始化 / 重置 / 找最近 ——
 "iRN", "kRN", "iIN", "kIN", "iRS", "iNR", "距2NR", "径和NR", "最佳距NR", "最近NR",
// —— 墙反弹（带旋转的冲量求解）——
  "墙点X", "墙点Y", "墙臂X", "墙臂Y", "墙速X", "墙速Y", "墙法速", "墙法臂", "墙分母",
  "墙冲量", "墙切X", "墙切Y", "墙切臂", "墙切分母", "墙切速", "墙切量", "墙限量",
  "墙冲X", "墙冲Y", "墙弹性", "墙深",
  // —— 墙接触面求解（专用变量，避免与其它函数踩踏）——
  "墙kK", "墙槽C", "墙投C", "墙最佳C", "墙和X", "墙和Y", "墙数C",
  // —— 新增刚体（E 键设置边数 / G 键生成）——
  "新槽", "E现", "G现", "上E", "上G",
].forEach(n => K.defVar(n, 0));
K.defVar("帧数", 0, true, { x: 470, y: 330 });
K.defVar("暂停", 0, true, { x: 470, y: 290 });
// 当前刚体数（运行时可见）：G 键 +1（上限 NB_MAX），R 重置回 NB
K.defVar("体数", NB, true, { x: 470, y: 210 });
// 待生成刚体的边数（运行时可见）：E 键循环 3→4→…→8→3，「输入后保存直到下次修改」
K.defVar("新边数", 6, true, { x: 470, y: 250 });

// ============================================================ 积木片段助手
const N = K.N, V = K.V;
const S = (name, val) => K.setV(name, val);                 // 标量赋值
const LS = (list, idx, val) => K.listSet(list, idx, val);   // 列表赋值
const lg = (list, idx) => K.listGet(list, idx);             // 读列表
const slot = (iNode, kNode) => K.add(K.mul(K.sub(iNode, N(1)), N(MAXV)), kNode); // (i-1)*8+k
const rep = (times, body) => K.repeatN(times, body);

// ============================================================ 世界顶点(i)
// 唯一写 顶X/顶Y 的生产者；内部变量全部带 WV 后缀。
function fWorldVerts() {
  const I = () => param("i");
  const Kc = () => V("kWV");
  defProc("世界顶点", ["i"], [
    S("kWV", N(1)),
    rep(lg("边数", I()), [
      S("槽WV", slot(I(), Kc())),
      S("步角WV", K.div(K.mul(N(360), Kc()), lg("边数", I()))),
      S("当前角WV", K.add(lg("刚角", I()), V("步角WV"))),
      // ★ 世界顶点写入时取整（math_round）：顶点量级 ±600 → 相对误差 ≤0.08%，
      //   SAT/投影/渲染全部改用整数顶点，大幅削减 18 位小数运算量。
      //   顶点是派生量（每帧由 刚X/刚Y/刚角 重算），取整不污染积分状态、不累积误差。
      LS("顶X", V("槽WV"), K.round(K.add(lg("刚X", I()), K.mul(lg("刚R", I()), cosD(V("当前角WV")))))),
      LS("顶Y", V("槽WV"), K.round(K.add(lg("刚Y", I()), K.mul(lg("刚R", I()), sinD(V("当前角WV")))))),
      K.chgV("kWV", N(1)),
    ]),
  ], 60);
}

// ============================================================ 边法线(i, k) → 法线XEDG/法线YEDG
// 输出通道只有 SAT 读；本函数不调用任何其它函数 → 无嵌套踩踏。
function fEdgeNormal() {
  const I = () => param("i");
  const Kc = () => param("k");
  defProc("边法线", ["i", "k"], [
    S("槽EDG", slot(I(), Kc())),
    K.ifChain([
      { cond: K.eq(Kc(), lg("边数", I())), body: [ S("槽2EDG", slot(I(), N(1))) ] },
      { cond: null, body: [ S("槽2EDG", K.add(V("槽EDG"), N(1))) ] },
    ]),
    S("边XEDG", K.sub(lg("顶X", V("槽2EDG")), lg("顶X", V("槽EDG")))),
    S("边YEDG", K.sub(lg("顶Y", V("槽2EDG")), lg("顶Y", V("槽EDG")))),
    S("边长EDG", K.sqrt(K.add(K.mul(V("边XEDG"), V("边XEDG")), K.mul(V("边YEDG"), V("边YEDG"))))),
    // 退化边保护：边长≈0 时不除（避免 0/0 产生 NaN 污染整条 SAT 轴链）
    K.ifChain([
      { cond: K.gt(V("边长EDG"), N("0.000001")), body: [
        S("法线XEDG", K.div(neg(V("边YEDG")), V("边长EDG"))),
        S("法线YEDG", K.div(V("边XEDG"), V("边长EDG"))),
      ] },
      { cond: null, body: [
        S("法线XEDG", N(0)),
        S("法线YEDG", N(0)),
      ] },
    ]),
  ], 260);
}

// ============================================================ 投影(i, 轴x, 轴y) → 投小PROJ/投大PROJ
// ★ 轴通过【参数】传入（参数是栈帧隔离的），彻底摆脱对全局 轴X/轴Y 的依赖。
//   kPROJ 为本函数私有计数器 → 与 SAT 的 kSAT 完全隔离。
function fProject() {
  const I = () => param("i");
  const AX = () => param("轴x");
  const AY = () => param("轴y");
  defProc("投影", ["i", "轴x", "轴y"], [
    S("投小PROJ", N(1000000000)),
    S("投大PROJ", N(-1000000000)),
    S("kPROJ", N(1)),
    rep(lg("边数", I()), [
      S("槽PROJ", slot(I(), V("kPROJ"))),
      S("暂PROJ", K.add(K.mul(lg("顶X", V("槽PROJ")), AX()), K.mul(lg("顶Y", V("槽PROJ")), AY()))),
      K.ifChain([{ cond: K.lt(V("暂PROJ"), V("投小PROJ")), body: [ S("投小PROJ", V("暂PROJ")) ] }]),
      K.ifChain([{ cond: K.gt(V("暂PROJ"), V("投大PROJ")), body: [ S("投大PROJ", V("暂PROJ")) ] }]),
      K.chgV("kPROJ", N(1)),
    ]),
  ], 460);
}

// ============================================================ SAT(i, j) → sat深SAT + 法XSAT/法YSAT
// 窄相位：分别沿两个多边形的每条边法线做投影，取最小重叠轴。
// 投影结果由「投影」函数直接写入 投小PROJ/投大PROJ → SAT 立即拷贝到 投小ASAT…（输出通道）。
function fSAT() {
  const I = () => param("i");
  const J = () => param("j");
  const scanEdges = (bodyExpr) => [
    S("kSAT", N(1)),
    rep(lg("边数", bodyExpr()), [
      call("边法线", [bodyExpr(), V("kSAT")]),
      call("投影", [I(), V("法线XEDG"), V("法线YEDG")]),
      S("投小ASAT", V("投小PROJ")), S("投大ASAT", V("投大PROJ")),
      call("投影", [J(), V("法线XEDG"), V("法线YEDG")]),
      S("投小BSAT", V("投小PROJ")), S("投大BSAT", V("投大PROJ")),
      // 重叠 = min(投大A,投大B) - max(投小A,投小B)（无 min/max 积木，用 ifChain）
      K.ifChain([
        { cond: K.lt(V("投大ASAT"), V("投大BSAT")), body: [ S("暂SAT", V("投大ASAT")) ] },
        { cond: null, body: [ S("暂SAT", V("投大BSAT")) ] },
      ]),
      K.ifChain([
        { cond: K.gt(V("投小ASAT"), V("投小BSAT")), body: [ S("暂2SAT", V("投小ASAT")) ] },
        { cond: null, body: [ S("暂2SAT", V("投小BSAT")) ] },
      ]),
      S("重叠SAT", K.sub(V("暂SAT"), V("暂2SAT"))),
      K.ifChain([{ cond: K.lte(V("重叠SAT"), N(0)), body: [ S("分离SAT", N(1)) ] }]),
      K.ifChain([{
        cond: K.and(K.gt(V("重叠SAT"), N(0)), K.lt(V("重叠SAT"), V("最小深SAT"))),
        body: [ S("最小深SAT", V("重叠SAT")), S("法XSAT", V("法线XEDG")), S("法YSAT", V("法线YEDG")) ],
      }]),
      K.chgV("kSAT", N(1)),
    ]),
  ];
  defProc("SAT", ["i", "j"], [
    S("sat深SAT", N(0)),
    S("最小深SAT", N(1000000000)),
    S("法XSAT", N(0)), S("法YSAT", N(0)),
    S("分离SAT", N(0)),
    ...scanEdges(I),
    ...scanEdges(J),
    // 法线定向：由 i 指向 j
    K.ifChain([{
      cond: K.lt(K.add(K.mul(K.sub(lg("刚X", J()), lg("刚X", I())), V("法XSAT")),
        K.mul(K.sub(lg("刚Y", J()), lg("刚Y", I())), V("法YSAT"))), N(0)),
      body: [ S("法XSAT", neg(V("法XSAT"))), S("法YSAT", neg(V("法YSAT"))) ],
    }]),
    K.ifChain([
      { cond: K.eq(V("分离SAT"), N(1)), body: [ S("sat深SAT", N(0)) ] },
      { cond: null, body: [ S("sat深SAT", V("最小深SAT")) ] },
    ]),
  ], 660);
}

// ============================================================ 支撑点(i, 向x, 向y) → 支点XSUP/支点YSUP
// 方向通过参数传入；输出通道只有 解算冲量 读。
function fSupport() {
  const I = () => param("i");
  const DX = () => param("向x");
  const DY = () => param("向y");
  defProc("支撑点", ["i", "向x", "向y"], [
    S("支最佳SUP", N(-1000000000)),
    S("支点XSUP", N(0)), S("支点YSUP", N(0)),
    S("kSUP", N(1)),
    rep(lg("边数", I()), [
      S("槽SUP", slot(I(), V("kSUP"))),
      S("暂SUP", K.add(K.mul(lg("顶X", V("槽SUP")), DX()), K.mul(lg("顶Y", V("槽SUP")), DY()))),
      K.ifChain([{
        cond: K.gt(V("暂SUP"), V("支最佳SUP")),
        body: [ S("支最佳SUP", V("暂SUP")), S("支点XSUP", lg("顶X", V("槽SUP"))), S("支点YSUP", lg("顶Y", V("槽SUP"))) ],
      }]),
      K.chgV("kSUP", N(1)),
    ]),
  ], 1000);
}

// ============================================================ 解算冲量(a体,b体,nX,nY,深度,模式)
// 模式 1 = Baumgarte 位置修正；模式 0 = 速度求解（法向回弹 + 切向摩擦，带旋转）
//
// ★ 量纲约定：刚AV = 弧度/帧，惯量 I = ½mr²（弧度制）→ 角冲量 Δω = I⁻¹·(r×P) 直接得到弧度/帧。
// ★ 有效质量修正：法向冲量的角耦合项应为 (r×n)²，切向冲量应为 (r×t)²。
//   原实现把两者写反（法向用了 r·n、切向用了 r·t）→ 法向冲量不产生力矩 → 看不到旋转。
function fResolve() {
  const A = () => param("a体"), B = () => param("b体");
  const NX = () => param("nX"), NY = () => param("nY");
  const PEN = () => param("深度");
  const invMa = () => lg("刚反质量", A()), invMb = () => lg("刚反质量", B());
  const invIa = () => lg("刚反惯量", A()), invIb = () => lg("刚反惯量", B());
  defProc("解算冲量", ["a体", "b体", "nX", "nY", "深度", "模式"], [
    K.ifChain([
      { // ---- 位置修正 ----
        cond: K.eq(param("模式"), N(1)),
        body: [
          K.ifChain([{
            cond: K.gt(PEN(), N(SLOP)),
            body: [
              S("修正", K.div(K.mul(K.sub(PEN(), N(SLOP)), N(BETA)), K.add(invMa(), invMb()))),
              LS("刚X", A(), K.sub(lg("刚X", A()), K.mul(K.mul(NX(), V("修正")), invMa()))),
              LS("刚Y", A(), K.sub(lg("刚Y", A()), K.mul(K.mul(NY(), V("修正")), invMa()))),
              LS("刚X", B(), K.add(lg("刚X", B()), K.mul(K.mul(NX(), V("修正")), invMb()))),
              LS("刚Y", B(), K.add(lg("刚Y", B()), K.mul(K.mul(NY(), V("修正")), invMb()))),
            ],
          }]),
        ],
      },
      { // ---- 速度求解 ----
        cond: null,
        body: [
          // 接触点 = 双方「朝向对方」的支撑点中点（贴在刚体表面，防力臂塌缩导致能量爆炸）
          //   甲体取 +n 方向支撑点（离 b 体最近的那一面），乙体取 -n 方向支撑点。
          call("支撑点", [A(), NX(), NY()]),
          S("甲点X", V("支点XSUP")), S("甲点Y", V("支点YSUP")),
          call("支撑点", [B(), neg(NX()), neg(NY())]),
          S("乙点X", V("支点XSUP")), S("乙点Y", V("支点YSUP")),
          S("触X", K.mul(K.add(V("甲点X"), V("乙点X")), N("0.5"))),
          S("触Y", K.mul(K.add(V("甲点Y"), V("乙点Y")), N("0.5"))),
          S("臂AX", K.sub(V("触X"), lg("刚X", A()))),
          S("臂AY", K.sub(V("触Y"), lg("刚Y", A()))),
          S("臂BX", K.sub(V("触X"), lg("刚X", B()))),
          S("臂BY", K.sub(V("触Y"), lg("刚Y", B()))),
          // 接触点速度 = v + ω×r（ω 用弧度/帧）
          S("速AX", K.sub(lg("刚VX", A()), K.mul(lg("刚AV", A()), V("臂AY")))),
          S("速AY", K.add(lg("刚VY", A()), K.mul(lg("刚AV", A()), V("臂AX")))),
          S("速BX", K.sub(lg("刚VX", B()), K.mul(lg("刚AV", B()), V("臂BY")))),
          S("速BY", K.add(lg("刚VY", B()), K.mul(lg("刚AV", B()), V("臂BX")))),
          S("相X", K.sub(V("速BX"), V("速AX"))),
          S("相Y", K.sub(V("速BY"), V("速AY"))),
          S("法速", K.add(K.mul(V("相X"), NX()), K.mul(V("相Y"), NY()))),
          K.ifChain([{
            cond: K.lt(V("法速"), N(0)),
            body: [
              S("弹性", N(E_REST)),
              K.ifChain([{ cond: K.gt(V("法速"), N(-0.5)), body: [ S("弹性", N(0)) ] }]),
              // 法向角耦合 = (r×n)²
              S("法臂A", K.sub(K.mul(V("臂AX"), NY()), K.mul(V("臂AY"), NX()))),
              S("法臂B", K.sub(K.mul(V("臂BX"), NY()), K.mul(V("臂BY"), NX()))),
              S("分母", K.add(K.add(invMa(), invMb()),
                K.add(K.mul(K.mul(V("法臂A"), V("法臂A")), invIa()),
                  K.mul(K.mul(V("法臂B"), V("法臂B")), invIb())))),
              S("冲量", K.div(K.mul(neg(K.add(N(1), V("弹性"))), V("法速")), V("分母"))),
              K.ifChain([{ cond: K.lt(V("冲量"), N(0)), body: [ S("冲量", N(0)) ] }]),
              // 切向：t = (-ny, nx)，角耦合 = (r×t)² = (r·n)²
              S("切X", neg(NY())), S("切Y", NX()),
              S("切臂A", K.add(K.mul(V("臂AX"), NX()), K.mul(V("臂AY"), NY()))),
              S("切臂B", K.add(K.mul(V("臂BX"), NX()), K.mul(V("臂BY"), NY()))),
              S("切分母", K.add(K.add(invMa(), invMb()),
                K.add(K.mul(K.mul(V("切臂A"), V("切臂A")), invIa()),
                  K.mul(K.mul(V("切臂B"), V("切臂B")), invIb())))),
              S("切速", K.add(K.mul(V("相X"), V("切X")), K.mul(V("相Y"), V("切Y")))),
              S("切量", K.div(neg(V("切速")), V("切分母"))),
              S("限量", K.mul(V("冲量"), N(MU))),
              K.ifChain([{ cond: K.gt(V("切量"), V("限量")), body: [ S("切量", V("限量")) ] }]),
              K.ifChain([{ cond: K.lt(V("切量"), neg(V("限量"))), body: [ S("切量", neg(V("限量"))) ] }]),
              S("冲X", K.add(K.mul(V("冲量"), NX()), K.mul(V("切量"), V("切X")))),
              S("冲Y", K.add(K.mul(V("冲量"), NY()), K.mul(V("切量"), V("切Y")))),
              // b 受 +P，a 受 -P（约定：法线由 a 指向 b）
              LS("刚VX", A(), K.sub(lg("刚VX", A()), K.mul(V("冲X"), invMa()))),
              LS("刚VY", A(), K.sub(lg("刚VY", A()), K.mul(V("冲Y"), invMa()))),
              LS("刚VX", B(), K.add(lg("刚VX", B()), K.mul(V("冲X"), invMb()))),
              LS("刚VY", B(), K.add(lg("刚VY", B()), K.mul(V("冲Y"), invMb()))),
              // 角冲量：Δω = I⁻¹·(r×P)，直接得到弧度/帧
              LS("刚AV", A(), K.sub(lg("刚AV", A()),
                K.mul(K.sub(K.mul(V("臂AX"), V("冲Y")), K.mul(V("臂AY"), V("冲X"))), invIa()))),
              LS("刚AV", B(), K.add(lg("刚AV", B()),
                K.mul(K.sub(K.mul(V("臂BX"), V("冲Y")), K.mul(V("臂BY"), V("冲X"))), invIb()))),
            ],
          }]),
        ],
      },
    ]),
  ], 1200);
}

// ============================================================ 墙反弹(i, 法线x, 法线y)
// ★ 把墙当作「无限质量静态体」，用法向冲量 + 切向摩擦冲量求解 → 会产生角冲量。
//   接触点：沿 -n 方向的支撑点（刚体最靠近墙的那一面），力臂 r = 接触点 - 质心。
//   法向：k_n = invM + (r×n)²·invI ，jn = -(1+e)·v_n / k_n （v_n = 接触点法向速度）
//   切向：k_t = invM + (r·n)²·invI （t=(-ny,nx) 时 r×t = r·n），jt = -v_t / k_t，|jt| ≤ μ·jn
//   总冲量 P = jn·n + jt·t ；Δv = P·invM ；Δω = (r×P)·invI
//   （r×P)·invI 直接得到弧度/帧 → 与「刚AV = 弧度/帧」量纲一致。
//   墙体 invM = invI = 0（静态），所以刚体单侧承担全部冲量。
function fWall() {
  const I = () => param("i");
  const NX = () => param("法线x"), NY = () => param("法线y");
  const LIM = () => param("墙距");
  const invM = () => lg("刚反质量", I());
  const invI = () => lg("刚反惯量", I());
  defProc("墙反弹", ["i", "法线x", "法线y", "墙距"], [
    // 接触几何必须用【当前帧最新】的顶点（刚体本帧已积分）→ 先刷新世界顶点
    call("世界顶点", [I()]),
    // 接触点 = 「接触面中点」：沿 -n 方向最深的一批顶点（深度差 ≤0.5px）取平均
    //   · 单点接触（尖角撞墙）→ 该顶点 → 力臂正确 → 撞墙产生自旋
    //   · 面接触（多边形平躺/贴边）→ 面中点 → 法向冲量过质心 → 不产生假扭矩
    S("墙最佳C", N(-1000000000)),
    S("墙kK", N(1)),
    rep(lg("边数", I()), [
      S("墙槽C", slot(I(), V("墙kK"))),
      S("墙投C", K.mul(K.add(K.mul(NX(), lg("顶X", V("墙槽C"))), K.mul(NY(), lg("顶Y", V("墙槽C")))), N(-1))),
      K.ifChain([{
        cond: K.gt(V("墙投C"), V("墙最佳C")),
        body: [ S("墙最佳C", V("墙投C")) ],
      }]),
      K.chgV("墙kK", N(1)),
    ]),
    S("墙和X", N(0)), S("墙和Y", N(0)), S("墙数C", N(0)),
    S("墙kK", N(1)),
    rep(lg("边数", I()), [
      S("墙槽C", slot(I(), V("墙kK"))),
      S("墙投C", K.mul(K.add(K.mul(NX(), lg("顶X", V("墙槽C"))), K.mul(NY(), lg("顶Y", V("墙槽C")))), N(-1))),
      K.ifChain([{
        cond: K.gte(V("墙投C"), K.sub(V("墙最佳C"), N(0.5))),
        body: [
          S("墙和X", K.add(V("墙和X"), lg("顶X", V("墙槽C")))),
          S("墙和Y", K.add(V("墙和Y"), lg("顶Y", V("墙槽C")))),
          S("墙数C", K.add(V("墙数C"), N(1))),
        ],
      }]),
      K.chgV("墙kK", N(1)),
    ]),
    S("墙点X", K.div(V("墙和X"), V("墙数C"))),
    S("墙点Y", K.div(V("墙和Y"), V("墙数C"))),
    // 力臂 r = 接触点 - 质心
    S("墙臂X", K.sub(V("墙点X"), lg("刚X", I()))),
    S("墙臂Y", K.sub(V("墙点Y"), lg("刚Y", I()))),
    // 穿透深度 = -墙距 - (n·接触点)   （>0 表示已穿墙；n 指向房间内部）
    S("墙深", K.sub(neg(LIM()),
      K.add(K.mul(V("墙点X"), NX()), K.mul(V("墙点Y"), NY())))),
    K.ifChain([{
      cond: K.gt(V("墙深"), N(0)),
      body: [
        // —— 位置修正：沿 n 推回房间内 ——
        LS("刚X", I(), K.add(lg("刚X", I()), K.mul(NX(), V("墙深")))),
        LS("刚Y", I(), K.add(lg("刚Y", I()), K.mul(NY(), V("墙深")))),
        // —— 速度求解（仅在冲向墙时）——
        // 接触点速度 = v + ω×r（ω = 刚AV 弧度/帧）
        S("墙速X", K.sub(lg("刚VX", I()), K.mul(lg("刚AV", I()), V("墙臂Y")))),
        S("墙速Y", K.add(lg("刚VY", I()), K.mul(lg("刚AV", I()), V("墙臂X")))),
        // 法向速度 v_n = v·n
        S("墙法速", K.add(K.mul(V("墙速X"), NX()), K.mul(V("墙速Y"), NY()))),
        K.ifChain([{
          cond: K.lt(V("墙法速"), N(0)),
          body: [
            S("墙弹性", N(REST_WALL)),
            // 法向角耦合 (r×n)²
            S("墙法臂", K.sub(K.mul(V("墙臂X"), NY()), K.mul(V("墙臂Y"), NX()))),
            S("墙分母", K.add(invM(),
              K.mul(K.mul(V("墙法臂"), V("墙法臂")), invI()))),
            S("墙冲量", K.div(K.mul(neg(K.add(N(1), V("墙弹性"))), V("墙法速")), V("墙分母"))),
            K.ifChain([{ cond: K.lt(V("墙冲量"), N(0)), body: [ S("墙冲量", N(0)) ] }]),
            // 切向摩擦：t = (-ny, nx)，角耦合 (r×t)² = (r·n)²
            S("墙切X", neg(NY())), S("墙切Y", NX()),
            S("墙切臂", K.add(K.mul(V("墙臂X"), NX()), K.mul(V("墙臂Y"), NY()))),
            S("墙切分母", K.add(invM(),
              K.mul(K.mul(V("墙切臂"), V("墙切臂")), invI()))),
            S("墙切速", K.add(K.mul(V("墙速X"), V("墙切X")), K.mul(V("墙速Y"), V("墙切Y")))),
            S("墙切量", K.div(neg(V("墙切速")), V("墙切分母"))),
            S("墙限量", K.mul(V("墙冲量"), N(MU))),
            K.ifChain([{ cond: K.gt(V("墙切量"), V("墙限量")), body: [ S("墙切量", V("墙限量")) ] }]),
            K.ifChain([{ cond: K.lt(V("墙切量"), neg(V("墙限量"))), body: [ S("墙切量", neg(V("墙限量"))) ] }]),
            S("墙冲X", K.add(K.mul(V("墙冲量"), NX()), K.mul(V("墙切量"), V("墙切X")))),
            S("墙冲Y", K.add(K.mul(V("墙冲量"), NY()), K.mul(V("墙切量"), V("墙切Y")))),
            // 应用冲量：线速度 += P·invM ；角速度 += (r×P)·invI  ← 「边缘反弹处理角速度」
            LS("刚VX", I(), K.add(lg("刚VX", I()), K.mul(V("墙冲X"), invM()))),
            LS("刚VY", I(), K.add(lg("刚VY", I()), K.mul(V("墙冲Y"), invM()))),
            LS("刚AV", I(), K.add(lg("刚AV", I()),
              K.mul(K.sub(K.mul(V("墙臂X"), V("墙冲Y")), K.mul(V("墙臂Y"), V("墙冲X"))), invI()))),
          ],
        }]),
      ],
    }]),
  ], 1400);
}

// ============================================================ 物理步进()
function fStep() {
  defProc("物理步进", [], [
    // 1) 重力（遍历【当前刚体数】，G 键新增的刚体同帧即参与）
    S("iSTEP", N(1)),
    rep(V("体数"), [
      LS("刚VY", V("iSTEP"), K.sub(lg("刚VY", V("iSTEP")), N(GRAV))),
      K.chgV("iSTEP", N(1)),
    ]),
    // 2) 宽相位（外接圆）+ SAT 窄相位 → 对列表
    S("对数", N(0)),
    S("iSTEP", N(1)),
    rep(V("体数"), [
      S("jSTEP", K.add(V("iSTEP"), N(1))),
      rep(K.sub(V("体数"), V("iSTEP")), [
        S("距2STEP", K.add(
          K.mul(K.sub(lg("刚X", V("jSTEP")), lg("刚X", V("iSTEP"))), K.sub(lg("刚X", V("jSTEP")), lg("刚X", V("iSTEP")))),
          K.mul(K.sub(lg("刚Y", V("jSTEP")), lg("刚Y", V("iSTEP"))), K.sub(lg("刚Y", V("jSTEP")), lg("刚Y", V("iSTEP")))))),
        S("径和STEP", K.add(lg("刚R", V("iSTEP")), lg("刚R", V("jSTEP")))),
        K.ifChain([{
          cond: K.lte(V("距2STEP"), K.mul(V("径和STEP"), V("径和STEP"))),
          body: [
            call("SAT", [V("iSTEP"), V("jSTEP")]),
            K.ifChain([{
              cond: K.gt(V("sat深SAT"), N(0)),
              body: [
                K.chgV("对数", N(1)),
                LS("对A", V("对数"), V("iSTEP")),
                LS("对B", V("对数"), V("jSTEP")),
                LS("对NX", V("对数"), V("法XSAT")),
                LS("对NY", V("对数"), V("法YSAT")),
                LS("对深", V("对数"), V("sat深SAT")),
              ],
            }]),
          ],
        }]),
        K.chgV("jSTEP", N(1)),
      ]),
      K.chgV("iSTEP", N(1)),
    ]),
    // 3) 速度求解（ITER 遍顺序冲量）
    S("pSTEP", N(1)),
    rep(N(ITER), [
      S("qSTEP", N(1)),
      rep(V("对数"), [
        call("解算冲量", [lg("对A", V("qSTEP")), lg("对B", V("qSTEP")), lg("对NX", V("qSTEP")),
          lg("对NY", V("qSTEP")), lg("对深", V("qSTEP")), N(0)]),
        K.chgV("qSTEP", N(1)),
      ]),
      K.chgV("pSTEP", N(1)),
    ]),
    // 4) 位置修正（单遍）
    S("qSTEP", N(1)),
    rep(V("对数"), [
      call("解算冲量", [lg("对A", V("qSTEP")), lg("对B", V("qSTEP")), lg("对NX", V("qSTEP")),
        lg("对NY", V("qSTEP")), lg("对深", V("qSTEP")), N(1)]),
      K.chgV("qSTEP", N(1)),
    ]),
    // 5) 积分 + 阻尼 + 墙体 + 安全钳
    S("iSTEP", N(1)),
    rep(V("体数"), [
      LS("刚VX", V("iSTEP"), K.mul(lg("刚VX", V("iSTEP")), N(DAMP_V))),
      LS("刚VY", V("iSTEP"), K.mul(lg("刚VY", V("iSTEP")), N(DAMP_V))),
      LS("刚AV", V("iSTEP"), K.mul(lg("刚AV", V("iSTEP")), N(DAMP_W))),
      // ★ 位置积分输出取整（math_round）：位置量级 ±600 → 相对误差 ≤0.08%，
      //   宽相位/SAT/渲染全部吃到整数坐标。速度/角度/角速度保持全精度（量级小，取整误差过大）。
      //   副作用可控：|v|<0.5px/帧时物体提前静止（肉眼不可见），穿透修正 <0.5px 被容忍（1px 内嵌入无感）。
      LS("刚X", V("iSTEP"), K.round(K.add(lg("刚X", V("iSTEP")), lg("刚VX", V("iSTEP"))))),
      LS("刚Y", V("iSTEP"), K.round(K.add(lg("刚Y", V("iSTEP")), lg("刚VY", V("iSTEP"))))),
      // 刚角（度） += 刚AV（弧度/帧）× RAD2DEG  ★ 量纲换算点
      LS("刚角", V("iSTEP"), K.add(lg("刚角", V("iSTEP")),
        K.mul(lg("刚AV", V("iSTEP")), N(RAD2DEG)))),
      // ---- 边缘反弹：改用「墙反弹」冲量过程（法向冲量 + 切向摩擦 + 角冲量）----
      //   包围圆只做「粗筛」（真正的接触判定与力臂在 墙反弹 内用多边形支撑点精确计算）。
      //   法线 n 指向房间内部；墙距 = 房间半宽/半高。
      K.ifChain([{
        cond: K.lt(K.sub(lg("刚X", V("iSTEP")), lg("刚R", V("iSTEP"))), N(-ROOM_X)),
        body: [ call("墙反弹", [V("iSTEP"), N(1), N(0), N(ROOM_X)]) ],
      }]),
      K.ifChain([{
        cond: K.gt(K.add(lg("刚X", V("iSTEP")), lg("刚R", V("iSTEP"))), N(ROOM_X)),
        body: [ call("墙反弹", [V("iSTEP"), N(-1), N(0), N(ROOM_X)]) ],
      }]),
      K.ifChain([{
        cond: K.lt(K.sub(lg("刚Y", V("iSTEP")), lg("刚R", V("iSTEP"))), N(-ROOM_Y)),
        body: [ call("墙反弹", [V("iSTEP"), N(0), N(1), N(ROOM_Y)]) ],
      }]),
      K.ifChain([{
        cond: K.gt(K.add(lg("刚Y", V("iSTEP")), lg("刚R", V("iSTEP"))), N(ROOM_Y)),
        body: [ call("墙反弹", [V("iSTEP"), N(0), N(-1), N(ROOM_Y)]) ],
      }]),
      S("速率STEP", K.sqrt(K.add(K.mul(lg("刚VX", V("iSTEP")), lg("刚VX", V("iSTEP"))),
        K.mul(lg("刚VY", V("iSTEP")), lg("刚VY", V("iSTEP")))))),
      K.ifChain([{
        cond: K.gt(V("速率STEP"), N(V_MAX)),
        body: [ LS("刚VX", V("iSTEP"), K.div(K.mul(lg("刚VX", V("iSTEP")), N(V_MAX)), V("速率STEP"))),
          LS("刚VY", V("iSTEP"), K.div(K.mul(lg("刚VY", V("iSTEP")), N(V_MAX)), V("速率STEP"))) ],
      }]),
      K.ifChain([{ cond: K.gt(lg("刚AV", V("iSTEP")), N(W_MAX)), body: [ LS("刚AV", V("iSTEP"), N(W_MAX)) ] }]),
      K.ifChain([{ cond: K.lt(lg("刚AV", V("iSTEP")), neg(N(W_MAX))), body: [ LS("刚AV", V("iSTEP"), neg(N(W_MAX))) ] }]),
      K.chgV("iSTEP", N(1)),
    ]),
    // 6) 刷新世界顶点（供渲染与下一帧 SAT）
    S("iSTEP", N(1)),
    rep(V("体数"), [
      call("世界顶点", [V("iSTEP")]),
      K.chgV("iSTEP", N(1)),
    ]),
  ], 1500);
}

// ============================================================ 渲染()
function fRender() {
  const I = () => V("iRN");
  defProc("渲染", [], [
    K.clearDraw(),
    // 房间边框
    penColorHex(COLOR_WALL), K.penSize(3),
    K.penUp(),
    K.moveTo(N(-ROOM_X), N(-ROOM_Y)),
    K.penDown(),
    K.moveTo(N(ROOM_X), N(-ROOM_Y)),
    K.moveTo(N(ROOM_X), N(ROOM_Y)),
    K.moveTo(N(-ROOM_X), N(ROOM_Y)),
    K.moveTo(N(-ROOM_X), N(-ROOM_Y)),
    K.penUp(),
    // 各刚体（多边形路径；圆 = 8 边形近似）
    K.penSize(2),
    S("iRN", N(1)),
    rep(V("体数"), [
      K.ifChain([
        { cond: K.eq(lg("边数", I()), N(MAXV)), body: [ penColorHex(COLOR_CIRCLE) ] },
        { cond: null, body: [ penColorHex(COLOR_POLY) ] },
      ]),
      K.penUp(),
      K.moveTo(lg("顶X", slot(I(), N(1))), lg("顶Y", slot(I(), N(1)))),
      K.penDown(),
      S("kRN", N(2)),
      rep(K.sub(lg("边数", I()), N(1)), [
        K.moveTo(lg("顶X", slot(I(), V("kRN"))), lg("顶Y", slot(I(), V("kRN")))),
        K.chgV("kRN", N(1)),
      ]),
      K.moveTo(lg("顶X", slot(I(), N(1))), lg("顶Y", slot(I(), N(1)))), // 闭合
      K.penUp(),
      K.chgV("iRN", N(1)),
    ]),
  ], 1800);
}

// ============================================================ 找最近(目标X,目标Y,容差) → 刚体序号或 0
function fNearest() {
  const TX = () => param("目标X"), TY = () => param("目标Y"), TOL = () => param("容差");
  defProc("找最近", ["目标X", "目标Y", "容差"], [
    S("最近NR", N(0)),
    S("最佳距NR", N(1000000000)),
    S("iNR", N(1)),
    rep(V("体数"), [
      S("距2NR", K.add(
        K.mul(K.sub(lg("刚X", V("iNR")), TX()), K.sub(lg("刚X", V("iNR")), TX())),
        K.mul(K.sub(lg("刚Y", V("iNR")), TY()), K.sub(lg("刚Y", V("iNR")), TY())))),
      S("径和NR", K.add(lg("刚R", V("iNR")), TOL())),
      K.ifChain([{
        cond: K.and(K.lt(V("距2NR"), K.mul(V("径和NR"), V("径和NR"))), K.lt(V("距2NR"), V("最佳距NR"))),
        body: [ S("最佳距NR", V("距2NR")), S("最近NR", V("iNR")) ],
      }]),
      K.chgV("iNR", N(1)),
    ]),
    retProc(V("最近NR")),
  ], 2100);
}

// ============================================================ 新刚体()
// 「新增刚体」的生成端（G 键触发，在 输入处理 内调用）：于鼠标当前位置追加一个刚体。
// 唯一参数 = 边数（E 键循环设置，存于 新边数，「输入后保存直到下次修改」）；半径固定 SPAWN_R。
// 槽位 = 体数+1（尾部追加），体数+1；满员（体数 ≥ NB_MAX）时整个分支空操作。
// ★ 质量/反质量/反惯量的乘法结合顺序与「初始化」逐字一致（(r*r)*0.01、1/((0.5*m)*(r*r))）——
//   位级对齐，否则 ULP 漂移会在支撑点近平局处翻转比较（参照 VM 位级一致铁律）。
function fSpawn() {
  defProc("新刚体", [], [
    K.ifChain([{
      cond: K.lt(V("体数"), N(NB_MAX)),
      body: [
        S("新槽", K.add(V("体数"), N(1))),
        K.chgV("体数", N(1)),
        // 出生点 = 鼠标位置（取整，与整数位置网格一致；越界时由下一帧墙反弹推回房间）
        LS("刚X", V("新槽"), K.round(V("鼠X"))),
        LS("刚Y", V("新槽"), K.round(V("鼠Y"))),
        LS("刚VX", V("新槽"), N(0)),
        LS("刚VY", V("新槽"), N(0)),
        LS("刚角", V("新槽"), N(0)),
        LS("刚AV", V("新槽"), N(0)),
        LS("刚R", V("新槽"), N(SPAWN_R)),
        LS("边数", V("新槽"), V("新边数")),
        // 派生：质量 = r²*0.01；反质量 = 1/m；反惯量 = 1/((0.5*m)*(r*r))
        LS("刚质量", V("新槽"), K.mul(K.mul(N(SPAWN_R), N(SPAWN_R)), N("0.01"))),
        LS("刚反质量", V("新槽"), K.div(N(1), lg("刚质量", V("新槽")))),
        LS("刚反惯量", V("新槽"), K.div(N(1), K.mul(K.mul(N("0.5"), lg("刚质量", V("新槽"))),
          K.mul(N(SPAWN_R), N(SPAWN_R))))),
        call("世界顶点", [V("新槽")]),
      ],
    }]),
  ], 3300);
}

// ============================================================ 初始化()
function fInit() {
  const copyInit = [
    LS("刚X", V("iIN"), lg("初X", V("iIN"))),
    LS("刚Y", V("iIN"), lg("初Y", V("iIN"))),
    LS("刚VX", V("iIN"), lg("初VX", V("iIN"))),
    LS("刚VY", V("iIN"), lg("初VY", V("iIN"))),
    LS("刚角", V("iIN"), lg("初角", V("iIN"))),
    // 初AV 以「度/帧」存放（人读得懂），载入时换算成「弧度/帧」（刚AV 的内部单位）
    LS("刚AV", V("iIN"), K.mul(lg("初AV", V("iIN")), N(DEG2RAD))),
  ];
  const specs = [];
  for (const b of BODIES) {
    specs.push(K.listAdd("初X", N(b[0])), K.listAdd("初Y", N(b[1])),
      K.listAdd("初VX", N(b[6])), K.listAdd("初VY", N(b[7])),
      K.listAdd("初角", N(b[4])), K.listAdd("初AV", N(b[5])),
      K.listAdd("刚R", N(b[2])), K.listAdd("边数", N(b[3])));
  }
  // 派生：质量 = r²*0.01；反质量 = 1/m；反惯量 = 1/(0.5*m*r²)
  // （只读 刚R——已由上方 BODIES 的 listAdd 填好，故可与「载入初值」合并进同一个循环）
  const derive = [
    LS("刚质量", V("iIN"), K.mul(K.mul(lg("刚R", V("iIN")), lg("刚R", V("iIN"))), N("0.01"))),
    LS("刚反质量", V("iIN"), K.div(N(1), lg("刚质量", V("iIN")))),
    LS("刚反惯量", V("iIN"), K.div(N(1), K.mul(K.mul(N("0.5"), lg("刚质量", V("iIN"))),
      K.mul(lg("刚R", V("iIN")), lg("刚R", V("iIN")))))),
  ];
  defProc("初始化", [], [
    ...specs,
    // 刚体状态列表预扩展：lists_replace 越界是空操作（kitten4/Scratch 均静默跳过），
    // 必须先 append 到位——与下方顶X/对* 预扩展同一范式（修复「刚X 恒为空、物理不运行」）。
    // ★ 容量按 NB_MAX 预留：G 键生成的刚体占 NB+1..NB_MAX 槽位，不预扩展则 listSet 静默丢失
    //   （lists_replace 越界 = 空操作，铁律 11）→ 新刚体半径/边数恒 0 → 世界顶点读 边数[7] 直接崩。
    // ★ 循环打包：一个 rep(NB_MAX) 代替 NB_MAX×9=144 个 listAdd（初始化积木数 249→~100）。
    rep(N(NB_MAX), [
      K.listAdd("刚X", N(0)), K.listAdd("刚Y", N(0)), K.listAdd("刚VX", N(0)), K.listAdd("刚VY", N(0)),
      K.listAdd("刚角", N(0)), K.listAdd("刚AV", N(0)), K.listAdd("刚质量", N(0)),
      K.listAdd("刚反质量", N(0)), K.listAdd("刚反惯量", N(0)),
    ]),
    // 边数/刚R 只随 BODIES 生成了 NB 条 → 循环补足到 NB_MAX（补的是 0，由 BODIES 值占据前 NB 条）
    rep(N(NB_MAX - NB), [K.listAdd("边数", N(0)), K.listAdd("刚R", N(0))]),
    // 载入初值 + 派生质量/惯量（合并循环：派生只读 刚R，与初值拷贝无依赖）
    S("iIN", N(1)),
    rep(N(NB), [...copyInit, ...derive, K.chgV("iIN", N(1))]),
    // 顶点/对列表预扩展（replace 越界是空操作，必须先 append 到位；按 NB_MAX 容量）
    S("kIN", N(1)),
    rep(N(NB_MAX * MAXV), [K.listAdd("顶X", N(0)), K.listAdd("顶Y", N(0)), K.chgV("kIN", N(1))]),
    S("kIN", N(1)),
    rep(N(MAX_PAIRS), [
      K.listAdd("对A", N(0)), K.listAdd("对B", N(0)), K.listAdd("对NX", N(0)),
      K.listAdd("对NY", N(0)), K.listAdd("对深", N(0)), K.chgV("kIN", N(1)),
    ]),
    // 顶点刷新
    S("iIN", N(1)),
    rep(N(NB), [call("世界顶点", [V("iIN")]), K.chgV("iIN", N(1))]),
    S("对数", N(0)), S("暂停", N(0)), S("帧数", N(0)), S("体数", N(NB)),
  ], 2400);
}

// ============================================================ 重置()
function fReset() {
  const copyInit = [
    LS("刚X", V("iRS"), lg("初X", V("iRS"))),
    LS("刚Y", V("iRS"), lg("初Y", V("iRS"))),
    LS("刚VX", V("iRS"), lg("初VX", V("iRS"))),
    LS("刚VY", V("iRS"), lg("初VY", V("iRS"))),
    LS("刚角", V("iRS"), lg("初角", V("iRS"))),
    LS("刚AV", V("iRS"), K.mul(lg("初AV", V("iRS")), N(DEG2RAD))),
  ];
  defProc("重置", [], [
    S("iRS", N(1)),
    rep(N(NB), [...copyInit, K.chgV("iRS", N(1))]),
    S("iRS", N(1)),
    rep(N(NB), [call("世界顶点", [V("iRS")]), K.chgV("iRS", N(1))]),
    // 重置回初始 NB 个刚体（G 生成的刚体撤掉）；「新边数」参数保留——保存直到下次修改
    S("对数", N(0)), S("暂停", N(0)), S("帧数", N(0)), S("体数", N(NB)),
  ], 2800);
}

// ============================================================ 输入处理()
function fInput() {
  defProc("输入处理", [], [
    // 鼠标位置 + 按下边沿 → 抓取
    S("鼠X", K.mouseX()),
    S("鼠Y", K.mouseY()),
    // —— 布尔语义：mouse_down/check_key 输出 true/false，编辑器里 true≠1、false≠0 ——
    //    因此边沿检测一律「布尔直用 + 取反」，不做数字比较。
    S("按下", K.mDown()),
    K.ifChain([{
      cond: K.and(V("按下"), K.not(V("上鼠标"))),
      body: [ S("抓取", callV("找最近", [V("鼠X"), V("鼠Y"), N(25)])) ],
    }]),
    K.ifChain([{ cond: K.not(V("按下")), body: [ S("抓取", N(0)) ] }]),
    S("上鼠标", V("按下")),
    // 抓取中：刚体跟随鼠标（运动学驱动）
    K.ifChain([{
      cond: K.gt(V("抓取"), N(0)),
      body: [
        // 抓取目标同样取整：让被抓刚体与积分后的整数位置网格一致（偏移 ≤0.5px，无感）
        LS("刚X", V("抓取"), K.round(V("鼠X"))),
        LS("刚Y", V("抓取"), K.round(V("鼠Y"))),
        LS("刚VX", V("抓取"), N(0)),
        LS("刚VY", V("抓取"), N(0)),
        LS("刚AV", V("抓取"), K.mul(lg("刚AV", V("抓取")), N("0.9"))),
      ],
    }]),
    // 键盘（均为边沿检测）：空格(32) 暂停 / S(83) 单步 / R(82) 重置
    //   / E(69) 循环设置新刚体边数（3..8，保存直到下次修改）/ G(71) 在鼠标处生成新刚体
    S("空现", keyDown(32)),
    K.ifChain([{
      cond: K.and(V("空现"), K.not(V("上空格"))),
      body: [ S("暂停", K.sub(N(1), V("暂停"))) ],
    }]),
    S("上空格", V("空现")),
    S("S现", keyDown(83)),
    K.ifChain([{
      cond: K.and(V("S现"), K.not(V("上S"))),
      body: [ S("单步", N(1)) ],
    }]),
    S("上S", V("S现")),
    S("R现", keyDown(82)),
    K.ifChain([{
      cond: K.and(V("R现"), K.not(V("上R"))),
      body: [ call("重置", []) ],
    }]),
    S("上R", V("R现")),
    // —— E(69)：循环设置「新边数」参数 3→4→5→6→7→8→3（边沿检测；值保存直到下次修改）——
    //    边数上限 EDGE_MAX=8=MAXV：超过会写到邻体顶点槽（slot=(i-1)*8+k），故 8 即圆。
    S("E现", keyDown(69)),
    K.ifChain([{
      cond: K.and(V("E现"), K.not(V("上E"))),
      body: [
        S("新边数", K.add(V("新边数"), N(1))),
        K.ifChain([{ cond: K.gt(V("新边数"), N(EDGE_MAX)), body: [ S("新边数", N(EDGE_MIN)) ] }]),
      ],
    }]),
    S("上E", V("E现")),
    // —— G(71)：在鼠标当前位置生成新刚体（边数 = 新边数；满员 NB_MAX 时空操作）——
    S("G现", keyDown(71)),
    K.ifChain([{
      cond: K.and(V("G现"), K.not(V("上G"))),
      body: [ call("新刚体", []) ],
    }]),
    S("上G", V("G现")),
  ], 3100);
}

// ============================================================ 发射所有函数 + 主脚本
fWorldVerts();
fEdgeNormal();
fProject();
fSAT();
fSupport();
fResolve();
fWall();
fStep();
fRender();
fNearest();
fInit();
fReset();
fInput();
fSpawn();

K.script(ENGINE, K.onStart(
  // 「一步执行」(warp)：初始化内部的多层循环在同一帧内一次跑完，不再逐层等一帧
  K.warp([ call("初始化", []) ]),
  K.forever([
    // 主循环体同样放进「一步执行」：物理步进/渲染里的所有循环本帧内完成
    K.warp([
      call("输入处理", []),
      K.ifChain([{
        cond: K.or(K.eq(V("暂停"), N(0)), K.eq(V("单步"), N(1))),
        body: [
          call("物理步进", []),
          S("单步", N(0)),
          K.chgV("帧数", N(1)),
        ],
      }]),
      call("渲染", []),
    ]),
  ])
), 3600);

  // ============================================================ 补 shadows/mutation + 自检
  const stats = patchProcedures();

  // 自检：每个输入连接都必须有 shadows 条目（铁律 5）
  let missing = 0;
  for (const a of Object.values(K.state.actors)) {
    const bdj = a.block_data_json;
    for (const [bid, blk] of Object.entries(bdj.blocks)) {
      for (const meta of Object.values(bdj.connections[bid] || {})) {
        if (meta.type === "input" && !(meta.input_name in (blk.shadows || {}))) missing++;
      }
    }
  }
  if (missing) throw new Error("shadow coverage: " + missing + " input connections missing shadows");
  return stats;
};
