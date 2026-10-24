#!/usr/bin/env node
/**
 * Simulate the kitten4 editor's json_to_workspace_headless load logic
 * against a .bcm4 file: verify every connection can actually be made.
 * Uses block_struct.json (reporter/command classification from kitten.js)
 * and block_defs.json (input names from define_block_xml).
 */
"use strict";
const fs = require("fs");
const path = require("path");

const work = JSON.parse(fs.readFileSync(process.argv[2] || "MagicCatAcademy.bcm4", "utf8"));
const DATA = path.join(__dirname, "..", "data");
const struct = JSON.parse(fs.readFileSync(path.join(DATA, "block_struct.json"), "utf8"));
const defs = JSON.parse(fs.readFileSync(path.join(DATA, "block_defs.json"), "utf8"));

// statement input names per type (block_defs.json only captures <value> inputs;
// these names verified against the user's real works: repeat_*/forever use DO,
// start_as_a_mirror uses DO)
const STMT_INPUTS = {
  repeat_n_times: ["DO"],
  repeat_forever: ["DO"],
  repeat_forever_until: ["DO"],
  start_as_a_mirror: ["DO"],
};

// input names per type from the XML defs (inner XML)
function xmlInputs(type) {
  const xml = defs[type];
  const names = [];
  if (xml) {
    for (const m of xml.matchAll(/<(value|statement)\s+name="([^"]+)"/g)) {
      names.push(m[2]);
    }
  }
  if (STMT_INPUTS[type]) names.push(...STMT_INPUTS[type]);
  return names.length ? names : null;
}

function ifInputs(mutation) {
  const inputs = ["IF0", "DO0"];
  if (mutation) {
    const em = mutation.match(/elseif="(\d+)"/);
    const gm = mutation.match(/else="(\d+)"/);
    const n = em ? parseInt(em[1]) : 0;
    const hasElse = gm ? parseInt(gm[1]) === 1 : false;
    for (let i = 1; i <= n; i++) inputs.push("IF" + i, "DO" + i);
    if (hasElse) inputs.push("ELSE");
  }
  return inputs;
}

// text_join 的槽位数由 mutation items 决定（默认 XML 只有 ADD0/ADD1，
// 真实作品 items=3/4 常见；旧版不读 mutation → 对 ADD2+ 误报）
function textJoinInputs(mutation) {
  const inputs = ["TITLE_HEAD", "TITLE_TAIL", "MUTATE_BUTTON"];
  const im = (mutation || "").match(/items="(\d+)"/);
  const n = im ? parseInt(im[1]) : 2;
  for (let i = 0; i < n; i++) inputs.push("ADD" + i);
  return inputs;
}

let problems = 0;
const th = work.theatre;
for (const a of Object.values(th.actors)) {
  const bd = a.block_data_json;
  if (!bd) continue;
  const blocks = bd.blocks, conns = bd.connections;
  const name = a.name;
  for (const [pid, m] of Object.entries(conns)) {
    const parent = blocks[pid];
    if (!parent) { console.log(`[${name}] conn source ${pid} missing`); problems++; continue; }
    let avail;
    if (parent.type === "controls_if") avail = ifInputs(parent.mutation || "");
    else if (parent.type === "text_join") avail = textJoinInputs(parent.mutation || "");
    else avail = xmlInputs(parent.type); // null if unknown
    for (const [cid, meta] of Object.entries(m || {})) {
      const child = blocks[cid];
      if (!child) { console.log(`[${name}] conn target ${cid} missing (parent ${parent.type})`); problems++; continue; }
      const cs = struct[child.type];
      const isShadow = !!child.is_shadow;
      if (meta.type === "next") {
        if (cs && !cs.prev) {
          console.log(`[${name}] NEXT: child ${child.type} has no previous_connection (parent ${parent.type})`);
          problems++;
        }
      } else if (meta.input_type === "value") {
        if (avail && !avail.includes(meta.input_name)) {
          console.log(`[${name}] VALUE input "${meta.input_name}" not found on ${parent.type} (child ${child.type})`);
          problems++;
        }
        if (cs && !cs.output && !isShadow) {
          console.log(`[${name}] VALUE: child ${child.type} is not a reporter (parent ${parent.type}.${meta.input_name})`);
          problems++;
        }
      } else if (meta.input_type === "statement") {
        if (avail && !avail.includes(meta.input_name)) {
          console.log(`[${name}] STATEMENT input "${meta.input_name}" not found on ${parent.type} (child ${child.type})`);
          problems++;
        }
        if (cs && !cs.prev && !isShadow) {
          console.log(`[${name}] STATEMENT: child ${child.type} is not a command block (parent ${parent.type}.${meta.input_name})`);
          problems++;
        }
      }
    }
  }
}
console.log(problems === 0 ? "ALL CONNECTIONS OK" : `${problems} connection problems`);
