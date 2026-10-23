#!/usr/bin/env bash
# PoorPhy 示例一键全流程：生成 → 信封校验 → 连接校验 → VM 闭环测试
set -e
cd "$(dirname "$0")"
node gen.js
bash ../../tools/check_all.sh PoorPhy.bcm4 vm_test_poorphy.py
