#!/usr/bin/env bash
# check_all.sh — 通用发布门禁：信封校验 + 连接完整性（+ 可选 VM 闭环测试）
# 用法：
#   bash tools/check_all.sh <作品.bcm4>              # 只做结构与连接校验
#   bash tools/check_all.sh <作品.bcm4> <vm测试.py>  # 追加 VM 闭环测试
# 相对路径按调用者当前目录解析；任何一步失败即整体失败（set -e）。
set -e
HERE="$(cd "$(dirname "$0")" && pwd -W)"   # -W = Windows 风格绝对路径（pwd 默认返回 /g/... ，传给原生 python/node 会变 G://g//...）
WORK="${1:?用法: bash tools/check_all.sh <作品.bcm4> [vm测试.py]}"

echo "== 1) 信封校验 ====================================================="
python "$HERE/validate_bcm4.py" "$WORK"

echo "== 2) 连接完整性 ===================================================="
node "$HERE/check_connections.js" "$WORK"

if [ -n "${2:-}" ]; then
  echo "== 3) VM 闭环测试 ==================================================="
  python "$2" "$WORK"
fi

echo "== ALL PASS: $WORK ===================================================="
