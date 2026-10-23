#!/usr/bin/env node
"use strict";
/**
 * gen_mount.js — 通用「信封挂载」库：把内容模块挂到已验证的信封 .bcm4 上。
 * ==================================================================
 * 为什么用挂载而不是从零搭信封（bcm4gen.build）：
 *   从零搭信封易引入细微差异（编辑器加载场景失败 → 背景显示但积木栏消失、
 *   一动就报错）。以已知能在 kitten4 编辑器正常打开/运行的作品（默认
 *   envelopes/球体物理.bcm4）为基底，逐字节复用其 theatre/toolbox/painter/
 *   scene/actor 外壳，只替换「积木 + 变量 + 造型」，可保证编辑器一定认得。
 *
 * 用法（每个项目的 gen.js 都是这样一个薄包装）：
 *   const { mount } = require("../../tools/gen_mount.js");
 *   const { build }  = require("./content.js");      // 你的内容模块
 *   mount({
 *     build,                                          // function(K) -> stats
 *     defsPath:  path.join(__dirname, "../../data/block_defs.json"),
 *     envelope:  "",                                  // 空 = 默认 envelopes/球体物理.bcm4
 *     projectName: "我的作品",
 *     outPath:   process.argv[3] || path.join(__dirname, "out.bcm4"),
 *   });
 *
 * 约定（内容模块 content.js）：
 *   module.exports.build = function (K) { ...; return stats; }
 *   在 build 里用 K.defActor/defVar/defList/script/defScene 描述作品；
 *   返回 { nDef, nCall, nRet }（过程统计，可省）。
 */
const path = require("path");
const fs = require("fs");
const K = require("./bcm4gen.js");

const ENVELOPE_DEFAULT = path.join(__dirname, "..", "envelopes", "球体物理.bcm4");

function mount(opts) {
  const envelope = opts.envelope || ENVELOPE_DEFAULT;
  if (!fs.existsSync(envelope)) {
    throw new Error("找不到信封模板: " + envelope + "（放进 envelopes/ 或用 opts.envelope 指定）");
  }

  // 1) 构建内容（积木 + 变量 + 函数）
  K.loadDefs(opts.defsPath || path.join(__dirname, "..", "data", "block_defs.json"));
  const stats = opts.build(K) || {};

  // 2) 深拷贝已验证信封
  const out = JSON.parse(JSON.stringify(JSON.parse(fs.readFileSync(envelope, "utf8"))));

  // 3) 取出内容模块生成的唯一 actor（多角色作品需自行扩展：保留多个外壳）
  const actors = Object.values(K.state.actors);
  if (!actors.length) throw new Error("内容模块未生成任何 actor（build(K) 里至少 K.defActor 一次）");
  const poorActor = actors[0];
  const { variables, variable_order } = K.gatherVariables();

  // 4) 选出信封中的「引擎」角色（积木最多的那个），其余角色删除
  const actorEntries = Object.entries(out.theatre.actors);
  let engineId = null, engineBlocks = -1;
  for (const [aid, a] of actorEntries) {
    const nb = Object.keys(a.block_data_json.blocks).length;
    if (nb > engineBlocks) { engineBlocks = nb; engineId = aid; }
  }
  const dropIds = actorEntries.map(e => e[0]).filter(id => id !== engineId);
  for (const id of dropIds) delete out.theatre.actors[id];

  // 5) 清理 group：删除引用被删角色的 group，保留引擎 group 且只指向引擎
  for (const [gid, g] of Object.entries(out.theatre.groups)) {
    if (g.actors.some(a => dropIds.includes(a))) delete out.theatre.groups[gid];
    else g.actors = g.actors.filter(a => a === engineId);
  }

  // 5b) 关键修复：删 group 后必须同步清理所有指向已删实体的交叉引用，
  //     否则编辑器加载场景时解析到悬空 group/actor → 场景初始化失败 →
  //     退化状态（背景显示但积木栏消失、舞台仅 2 变量、不能运行、一动就报错）。
  for (const sc of Object.values(out.theatre.scenes)) {
    if (sc.group_order) sc.group_order = sc.group_order.filter(g => out.theatre.groups[g]);
    if (sc.actors) sc.actors = sc.actors.filter(a => out.theatre.actors[a]);
  }
  // current_entity/scene 在可用信封里根本不存在（key 缺失），必须 DELETE 而非置 null
  // （null 仍会被校验器视为 forbidden key）。
  delete out.theatre.current_entity;
  delete out.theatre.current_scene;

  // 6) 引擎角色：替换脚本区 + 造型 + 设为可见（start_on_click 帽子需可点击）
  const eng = out.theatre.actors[engineId];
  eng.block_data_json = poorActor.block_data_json;
  eng.name = poorActor.name;
  eng.styles = (poorActor.styles || []).slice();
  eng.current_style_id = poorActor.current_style_id;
  eng.visible = true;

  // 7) 场景：保留外壳与背景造型，但清空其积木（信封场景脚本引用它自己的变量，会悬空）
  for (const sc of Object.values(out.theatre.scenes)) {
    sc.block_data_json = { blocks: {}, connections: {}, comments: {} };
    sc.actors = [];
  }

  // 8) 替换变量
  out.variables = variables;
  out.variable_order = variable_order;

  // 9) 合并样式：保留信封背景/造型（已知渲染正常）+ 追加内容模块的造型（已被角色引用）
  Object.assign(out.theatre.styles, K.state.styles);

  // 10) 绝不写顶层 compile_result
  if ("compile_result" in out) delete out.compile_result;

  // 11) 作品标识。codemao_value 是云端 id（编辑器保存时不写它，由服务器分配），
  //     沿用信封原值——用同一个值已验证可正常打开，不要擅改成字符串。
  out.project_name = opts.projectName || "未命名作品";
  out.sample_id = "";

  const OUT = opts.outPath || path.join(process.cwd(), "out.bcm4");
  fs.mkdirSync(path.dirname(OUT), { recursive: true });
  fs.writeFileSync(OUT, JSON.stringify(out), "utf8");

  const size = (fs.statSync(OUT).size / 1024).toFixed(1);
  const totalBlocks = Object.values(out.theatre.actors)
    .reduce((s, a) => s + Object.keys(a.block_data_json.blocks).length, 0);
  console.log(`Wrote ${OUT} (${size} KB)`);
  console.log(`  actors: ${Object.keys(out.theatre.actors).length}, styles: ${Object.keys(out.theatre.styles).length}, variables: ${Object.keys(out.variables).length}, blocks: ${totalBlocks}`);
  console.log(`  engine actor: ${eng.name} visible=${eng.visible}`);
  console.log("procedures: defs=%d calls=%d returns=%d", stats.nDef || 0, stats.nCall || 0, stats.nRet || 0);
  console.log("mount build: OK");
  return OUT;
}

module.exports = { mount, ENVELOPE_DEFAULT };
