#!/usr/bin/env node
"use strict";
/**
 * template_work.js — 最小可运行示例（生成 .bcm4 的骨架）
 * ==================================================================
 * 这是「提示词 → 一键生成 .bcm4」模式的起点：直接改这个文件（或让 AI 写一个新文件）
 * 来描述你的作品，然后：
 *     node template_work.js
 * 即可在同级目录得到 out.bcm4，用 kitten4 编辑器打开即可编辑/运行。
 *
 * 约定（详见 references/kitten4_rules.md 七条铁律）：
 *   - 不要写顶层 compile_result（否则脚本区空白）。
 *   - 角色脚本首行会自动插 set_layer_with_pen(below)（避免挡住画笔）；背景是 scene，不插。
 *   - 索引 1 基（costume(1) = 第 1 个造型；setScene(1) = 第 1 张背景）。
 *   - controls_if 是 if/else-if，阈值分支高阈值排前面（铁律 7）。
 *   - warp 只能包「有界」循环。
 *
 * 素材：默认用 28px 蓝点 SVG（真实 dataURI，可见可点击）。
 *       真正做作品时，把 defStyle 的 url 换成你的图片 dataURI / http(s) URL。
 */
const path = require("path");
const K = require("./bcm4gen.js");

K.loadDefs(path.join(__dirname, "../data/block_defs.json"));

// 28px 蓝点 SVG。注意：1x1 透明 PNG 占位会被 kitten4 编辑器判「造型损坏」，
// 运行出来看不见角色（start_on_click 也点不到）——必须用真实 SVG/PNG dataURI。
const BLANK = "data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyOCIgaGVpZ2h0PSIyOCIgdmlld0JveD0iMCAwIDI4IDI4Ij48Y2lyY2xlIGN4PSIxNCIgY3k9IjE0IiByPSIxMSIgZmlsbD0iIzRGQzNGNyIgZmlsbC1vcGFjaXR5PSIwLjg1IiBzdHJva2U9IiMwMjg4RDEiIHN0cm9rZS13aWR0aD0iMi41Ii8+PC9zdmc+";

// ---- 背景（scene）：第 1 张造型作为标题画面
const bg = K.defStyle("bg_title", BLANK);
K.defScene("背景", [bg]);

// ---- 变量
K.defVar("得分", 0, true, { x: 500, y: 300 });

// ---- 角色：小猫（用两张占位造型演示造型切换）
const catIdle = K.defStyle("cat_idle", BLANK);
const catCast = K.defStyle("cat_cast", BLANK);
const CAT = K.defActor("小猫", [catIdle, catCast], { x: 0, y: -200, scale: 100 });

// ---- 脚本：当角色被点击，来回走 + 切换造型
K.script(CAT, K.onStart(
  K.repeatN(K.N(10), [
    K.move(20),
    K.costume(2),     // 第 2 个造型
    K.wait(0.2),
    K.move(-20),
    K.costume(1),     // 第 1 个造型
    K.wait(0.2),
  ]),
  // 计分演示：每次点击 +1
  K.chgV("得分", K.N(1))
));

// ---- 脚本：永久循环，根据得分改变透明度（演示变量读取 + 运算符）
K.script(CAT, K.onStart(
  K.forever([
    K.ifChain([
      { cond: K.gt(K.V("得分"), K.N(5)), body: [ K.fade(K.N(0.5)) ] },
      { cond: null, body: [ K.appear() ] },
    ]),
    K.wait(0.1),
  ])
));

console.log("示例生成完毕。请改用你自己的逻辑替换上面的脚本。");

// ---- 写出
K.write(path.join(__dirname, "..", "out", "我的作品(模板).bcm4"), "我的作品(模板)");
