#!/bin/bash
# 在 Debian VPS 上每 2 小时触发 GitHub Actions workflow_dispatch
#
# 用法:
#   bash trigger_actions.sh              # 手动触发一次
#   bash trigger_actions.sh --install    # 安装 crontab 定时任务
#   bash trigger_actions.sh --uninstall  # 移除 crontab 定时任务
#   bash trigger_actions.sh --status     # 查看定时任务状态

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_FILE="$SCRIPT_DIR/trigger_actions.log"
REPO="donotletmedown-xz/Merge_link"
WORKFLOW="update-config.yml"
# Token: 优先从环境变量读取，否则从 .github_token 文件读取
if [ -n "$GITHUB_TOKEN" ]; then
    TOKEN="$GITHUB_TOKEN"
elif [ -f "$SCRIPT_DIR/.github_token" ]; then
    TOKEN="$(cat "$SCRIPT_DIR/.github_token")"
else
    echo "错误: 未找到 token。请设置 GITHUB_TOKEN 环境变量或创建 .github_token 文件"
    exit 1
fi

# 检查 curl
if ! command -v curl &>/dev/null; then
    echo "正在安装 curl..."
    apt-get update -qq && apt-get install -y -qq curl
fi

# --install
if [ "${1:-}" = "--install" ]; then
    chmod +x "$0"
    CRON_CMD="0 */2 * * * $SCRIPT_DIR/$(basename "$0") >> $LOG_FILE 2>&1"
    (crontab -l 2>/dev/null | grep -v "trigger_actions.sh"; echo "$CRON_CMD") | crontab -
    echo "定时任务已安装: 每 2 小时触发 Actions"
    echo "日志: $LOG_FILE"
    exit 0
fi

# --uninstall
if [ "${1:-}" = "--uninstall" ]; then
    crontab -l 2>/dev/null | grep -v "trigger_actions.sh" | crontab -
    echo "定时任务已移除"
    exit 0
fi

# --status
if [ "${1:-}" = "--status" ]; then
    echo "=== 定时任务 ==="
    crontab -l 2>/dev/null | grep "trigger_actions" || echo "(未安装)"
    echo "=== 最近日志 ==="
    tail -5 "$LOG_FILE" 2>/dev/null || echo "(无日志)"
    exit 0
fi

# 触发 Actions
echo "[$(date '+%Y-%m-%d %H:%M:%S')] 正在触发 Actions..."

RESPONSE=$(curl -s -w "\n%{http_code}" -X POST \
    -H "Accept: application/vnd.github+json" \
    -H "Authorization: token $TOKEN" \
    "https://api.github.com/repos/$REPO/actions/workflows/$WORKFLOW/dispatches" \
    -d '{"ref":"main"}')

HTTP_CODE=$(echo "$RESPONSE" | tail -1)
BODY=$(echo "$RESPONSE" | sed '$d')

if [ "$HTTP_CODE" = "204" ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 触发成功"
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 触发失败 (HTTP $HTTP_CODE)"
    echo "  $BODY"
    exit 1
fi
