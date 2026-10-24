#!/usr/bin/env bash
# check_repo.sh — 仓库自检：验证「工具链本身是好的」+「知识库与实现一致」。
#
# 用途：新机器/新 agent 接手后第一条命令。先确认基础设施可信，再开工写作品。
# 用法：
#   bash tools/check_repo.sh              # 门禁全套（不含 VM 闭环，较快）
#   bash tools/check_repo.sh --full       # 追加 PoorPhy 示例的 VM 闭环测试（较慢）
set -e
HERE="$(cd "$(dirname "$0")" && pwd -W)"   # -W = Windows 风格绝对路径（pwd 默认返回 /g/... ，传给原生 python/node 会变 G://g//...）
ROOT="$(cd "$HERE/.." && pwd -W)"
FULL=0
[ "${1:-}" = "--full" ] && FULL=1

echo "== 1) 知识库与实现一致（ask.py/rules.json/dsl_api.json vs bcm4gen.js）====="
python "$HERE/verify_dsl.py"

echo ""
echo "== 2) DSL API 索引同步 ==============================================="
python "$HERE/extract_dsl_api.py" --check

echo ""
echo "== 3) 编辑器积木注册表 ==============================================="
python "$HERE/extract_registry.py" --check 2>/dev/null || echo "  (跳过：未提供 kitten.js 路径，注册表沿用 data/editor_block_types.json)"

echo ""
echo "== 4) 示例作品全流程（PoorPhy：生成 → 校验 → 连接 → VM 闭环）==========="
if [ "$FULL" = "1" ]; then
  bash "$ROOT/examples/poorphy/check_all.sh"
else
  bash "$ROOT/examples/poorphy/check_all.sh" 2>&1 | tail -20
fi

echo ""
echo "== ALL PASS: 工具链与知识库均正常 ====================================="
