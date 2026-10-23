#!/usr/bin/env node
"use strict";
/**
 * gen_basic.js — 生成一个「绝对能打开」的最小 .bcm4。
 * 以已知可用作品 球体物理.bcm4 的信封为基底（逐字节复用 theatre / toolbox / painter
 * 等全部信封结构），只保留：
 *   - 1 张背景（scene）命名为「新建对话框Hi」，复用其已验证可渲染的背景造型；
 *   - 1 个可见角色（actor），清空脚本、复用已验证可渲染的造型；
 *   - 1 个 group 把角色挂到场景里；
 *   - 变量 / 广播 / 脚本 全部清空（basics）。
 * 严格做交叉引用清理（scene.group_order / group.actors / styles），并绝不写
 * current_entity / current_scene / compile_result 等非法键。
 *
 * 用法：node gen_basic.js [信封.bcm4] [输出.bcm4]  →  默认 out/基础.bcm4
 */
const fs = require("fs");
const path = require("path");

const TEMPLATE = process.argv[2] || path.join(__dirname, "..", "envelopes", "球体物理.bcm4");
const KEEP_ACTOR = "8cfc4432-dafd-4406-bf77-c9fbe543a03d"; // 原「生物数」可见角色
const DROP_ACTOR = "950db17d-83cc-4646-bb12-405547b1e35b"; // 原「计算器」不可见引擎
const KEEP_GROUP = "6f8df52a-08a7-4f1d-acd5-3462c6ae42d5"; // 指向可见角色的 group
const DROP_GROUP = "c8bf592f-51e5-4eb6-889a-abd690dcb699"; // 指向引擎的 group
const DROP_STYLE = "88456637-051c-4c2b-8037-7fb123b18e54";  // 引擎造型（已无引用）

const tmpl = JSON.parse(fs.readFileSync(TEMPLATE, "utf8"));
const out = JSON.parse(JSON.stringify(tmpl));
const EMPTY = { blocks: {}, connections: {}, comments: {} };

// 1) 场景：改名 + 清空脚本
const scene = Object.values(out.theatre.scenes)[0];
scene.name = "新建对话框Hi";
scene.block_data_json = JSON.parse(JSON.stringify(EMPTY));

// 2) 角色：只保留可见角色，清空脚本、改名
for (const id of [DROP_ACTOR]) delete out.theatre.actors[id];
const actor = out.theatre.actors[KEEP_ACTOR];
actor.name = "角色";
actor.block_data_json = JSON.parse(JSON.stringify(EMPTY));

// 3) group：只保留指向可见角色的 group
for (const id of [DROP_GROUP]) delete out.theatre.groups[id];
// 4) 交叉引用清理：scene.group_order 只留现存 group；scene.actors 维持 []
scene.group_order = (scene.group_order || []).filter(g => out.theatre.groups[g]);
scene.actors = [];

// 5) 造型：删除已被删角色的造型（其余保留，含背景造型与角色造型）
if (DROP_STYLE in out.theatre.styles) delete out.theatre.styles[DROP_STYLE];

// 6) 变量 / 广播 / 顶层脚本：全部清空（basics）
out.variables = {};
out.variable_order = [];
out.broadcasts = {};

// 7) 绝不写非法的 theatre 键 / 顶层 compile_result
delete out.theatre.current_entity;
delete out.theatre.current_scene;
delete out.compile_result;

// 8) 工程名
out.project_name = "基础示例";

const OUT = process.argv[3] || path.join(__dirname, "..", "out", "基础.bcm4");
fs.mkdirSync(path.dirname(OUT), { recursive: true });
fs.writeFileSync(OUT, JSON.stringify(out), "utf8");

const size = (fs.statSync(OUT).size / 1024).toFixed(1);
const actors = Object.keys(out.theatre.actors).length;
const groups = Object.keys(out.theatre.groups).length;
const styles = Object.keys(out.theatre.styles).length;
const blocks = Object.values(out.theatre.actors).reduce((s, a) => s + Object.keys(a.block_data_json.blocks).length, 0);
console.log(`Wrote ${OUT} (${size} KB)`);
console.log(`  scenes: ${Object.keys(out.theatre.scenes).length} ("${scene.name}")  actors: ${actors}  groups: ${groups}  styles: ${styles}`);
console.log(`  scene.group_order: ${JSON.stringify(scene.group_order)}`);
console.log(`  blocks total: ${blocks}  variables: ${Object.keys(out.variables).length}  broadcasts: ${Object.keys(out.broadcasts).length}`);
console.log("basic build: OK");
