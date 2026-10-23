#!/usr/bin/env node
"use strict";
/**
 * gen.js — PoorPhy 示例的生成器（薄包装：内容在 poorphy_content.js，挂载逻辑在 tools/gen_mount.js）
 * 用法：
 *   node gen.js                 → 重新生成 examples/poorphy/PoorPhy.bcm4
 *   node gen.js <信封> <输出>   → 自选信封模板与输出路径
 */
const path = require("path");
const { mount } = require("../../tools/gen_mount.js");
const { build } = require("./poorphy_content.js");

mount({
  build,
  defsPath: path.join(__dirname, "../../data/block_defs.json"),
  envelope: process.argv[2] || "",   // 空 = 默认 envelopes/球体物理.bcm4
  projectName: "PoorPhy 刚体物理沙盒",
  outPath: process.argv[3] || path.join(__dirname, "PoorPhy.bcm4"),
});
