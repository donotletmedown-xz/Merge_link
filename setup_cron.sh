#!/bin/bash
# 在 Debian 服务器上部署 merge_clash.py 并设置每 2 小时定时运行

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON_SCRIPT="$SCRIPT_DIR/merge_clash.py"
LOG_FILE="$SCRIPT_DIR/merge_clash.log"

# 1. 安装依赖
echo "[1/3] 检查并安装依赖..."
apt-get update -qq
apt-get install -y -qq python3 python3-pip python3-venv > /dev/null 2>&1

# 创建虚拟环境（如果不存在）
VENV_DIR="$SCRIPT_DIR/venv"
if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
    echo "  已创建虚拟环境"
fi

# 在虚拟环境中安装 pyyaml
"$VENV_DIR/bin/pip" install --quiet pyyaml
echo "  依赖已就绪"

# 2. 测试运行一次
echo "[2/3] 测试运行脚本..."
cd "$SCRIPT_DIR"
"$VENV_DIR/bin/python3" "$PYTHON_SCRIPT" 2>&1 | tee -a "$LOG_FILE"
echo ""

# 3. 添加定时任务（每 2 小时）
echo "[3/3] 设置定时任务（每 2 小时运行一次）..."
CRON_CMD="0 */2 * * * cd $SCRIPT_DIR && $VENV_DIR/bin/python3 $PYTHON_SCRIPT >> $LOG_FILE 2>&1"

# 检查是否已存在相同任务，避免重复添加
(crontab -l 2>/dev/null | grep -v "merge_clash.py"; echo "$CRON_CMD") | crontab -
echo "  定时任务已添加"
echo ""

# 显示当前 crontab
echo "当前定时任务:"
crontab -l | grep "merge_clash"
echo ""

echo "========================================"
echo "部署完成！"
echo "  脚本路径: $PYTHON_SCRIPT"
echo "  日志文件: $LOG_FILE"
echo "  运行周期: 每 2 小时"
echo "  查看日志: tail -f $LOG_FILE"
echo "  查看任务: crontab -l"
echo "  删除任务: crontab -l | grep -v merge_clash | crontab -"
echo "========================================"
