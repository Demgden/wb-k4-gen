#!/usr/bin/env node
"use strict";
/**
 * kitten4_root.js — 定位 kitten4 工具链根目录（可被复制到任意项目里单独使用）。
 *
 * 为什么需要它：
 *   项目通常用 `require("../../tools/bcm4gen.js")` 这类相对路径引用工具链。
 *   一旦项目被移出仓库（换机器、单独 clone、挪到别的目录），相对路径立刻失效，
 *   报错是 "Cannot find module '../../tools/bcm4gen.js'" —— 新接手的人（尤其是 AI agent）
 *   要花很长时间才能定位到「工具链搬家了」这个根因。
 *
 * 本模块按优先级依次尝试：
 *   1. 环境变量 TOOLS4K4_HOME（显式指定，最高优先级）
 *   2. 从本文件所在目录向上逐级查找：
 *        - 某一级本身就是工具链根（含 tools/bcm4gen.js）→ 用它
 *        - 某一级下有 tools4k4/ 子目录 → 用它
 *   3. 常见兄弟目录（<上级>/tools4k4、<上级>/kitten4、~/Desktop/kitten4作品 ...）
 *   4. 都找不到 → 抛出带排查建议的错误（而不是让 require 报一句天书）
 *
 * 用法：
 *   const { root, requireTool } = require("./kitten4_root.js");
 *   const K = requireTool("bcm4gen.js");            // 自动解析 tools/<name>
 *   const defs = root + "/data/block_defs.json";
 */
const fs = require("fs");
const path = require("path");

const MARKER = path.join("tools", "bcm4gen.js");   // 工具链根的判据文件
const REPO_DIR_NAME = "tools4k4";                   // 工具链根的目录名

function isRoot(dir) {
  try {
    return fs.existsSync(path.join(dir, MARKER));
  } catch (e) {
    return false;
  }
}

function findRoot(startDir) {
  // 1) 环境变量
  const env = process.env.TOOLS4K4_HOME;
  if (env && isRoot(env)) return path.resolve(env);

  const start = path.resolve(startDir || __dirname);

  // 2) 从 start 向上逐级：既看「这一级本身是根」，也看「这一级下有 tools4k4/」
  let cur = start;
  for (;;) {
    if (isRoot(cur)) return cur;
    const child = path.join(cur, REPO_DIR_NAME);
    if (isRoot(child)) return child;
    const parent = path.dirname(cur);
    if (parent === cur) break;
    cur = parent;
  }

  // 3) 常见兄弟目录
  const sibs = [];
  const base = path.dirname(start);
  for (const d of [base, path.dirname(base), process.cwd(), path.join(process.cwd(), "..")]) {
    for (const name of [REPO_DIR_NAME, "kitten4", "kitten4作品", "模板"]) {
      sibs.push(path.join(d, name));
    }
  }
  for (const s of sibs) {
    if (isRoot(s)) return path.resolve(s);
  }
  return null;
}

const root = findRoot(__dirname);

function fail() {
  const tried = [];
  if (process.env.TOOLS4K4_HOME) tried.push("  环境变量 TOOLS4K4_HOME=" + process.env.TOOLS4K4_HOME);
  tried.push("  从 " + __dirname + " 向上逐级查找 " + REPO_DIR_NAME + "/ 或含 tools/bcm4gen.js 的目录");
  tried.push("  常见兄弟目录：" + path.dirname(path.resolve(__dirname)));
  const e = new Error(
    "找不到 kitten4 工具链（tools/bcm4gen.js）。\n已尝试：\n" + tried.join("\n") +
    "\n解决：设置环境变量指向工具链根目录，例如\n" +
    '  export TOOLS4K4_HOME=/path/to/tools4k4\n' +
    "或把 tools4k4 放在本项目的上级/同级目录。"
  );
  e.code = "KITTEN4_ROOT_NOT_FOUND";
  throw e;
}

if (!root) fail();

/** require 工具链里的某个工具文件（相对 tools/ 目录） */
function requireTool(name) {
  return require(path.join(root, "tools", name));
}

/** 工具链的某个数据文件绝对路径（相对 data/ 目录） */
function dataPath(name) {
  return path.join(root, "data", name);
}

module.exports = { root, requireTool, dataPath, findRoot };
