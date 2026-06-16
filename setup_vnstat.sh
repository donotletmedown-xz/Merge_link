#!/bin/bash
#
# vnstat 每小时流量统计 - 一键部署脚本
# 功能：自动安装 vnstat，配置每小时流量统计，写入 crontab
#

set -e

LOG="/var/log/traffic_hourly.log"
SCRIPT="/usr/local/bin/traffic_hourly.sh"
CRONJOB="0 * * * * $SCRIPT >> $LOG 2>&1"

echo "=========================================="
echo "  vnstat 每小时流量统计 - 一键部署"
echo "=========================================="

# 检查是否为 root
if [ "$(id -u)" -ne 0 ]; then
    echo "❌ 请使用 root 或 sudo 运行此脚本"
    exit 1
fi

# 1. 检测并安装 vnstat
echo ""
echo "[1/4] 检测 vnstat..."

if command -v vnstat &>/dev/null; then
    echo "  ✅ vnstat 已安装: $(vnstat --version | head -1)"
else
    echo "  ⏳ vnstat 未安装，正在安装..."

    if command -v apt-get &>/dev/null; then
        apt-get update -qq && apt-get install -y -qq vnstat
    elif command -v yum &>/dev/null; then
        yum install -y -q vnstat
    elif command -v dnf &>/dev/null; then
        dnf install -y -q vnstat
    elif command -v pacman &>/dev/null; then
        pacman -S --noconfirm vnstat
    else
        echo "  ❌ 无法识别包管理器，请手动安装 vnstat"
        exit 1
    fi

    echo "  ✅ vnstat 安装完成"
fi

# 2. 启动 vnstat 服务
echo ""
echo "[2/4] 启动 vnstat 服务..."

# 检测网络接口
INTERFACE=$(ip route show default 2>/dev/null | awk '/default/{print $5}' | head -1)
if [ -z "$INTERFACE" ]; then
    INTERFACE="eth0"
    echo "  ⚠️  未检测到默认接口，使用默认: $INTERFACE"
else
    echo "  检测到网络接口: $INTERFACE"
fi

# 启动服务
if command -v systemctl &>/dev/null; then
    systemctl enable vnstat 2>/dev/null || true
    systemctl restart vnstat 2>/dev/null || true
    echo "  ✅ vnstat 服务已启动"
else
    # 非 systemd 系统
    if [ -f /etc/init.d/vnstat ]; then
        /etc/init.d/vnstat restart 2>/dev/null || true
    else
        vnstatd -d 2>/dev/null || true
    fi
    echo "  ✅ vnstat 守护进程已启动"
fi

# 等待 vnstat 初始化数据库
echo "  等待 vnstat 初始化数据库..."
sleep 3

# 3. 创建流量统计脚本
echo ""
echo "[3/4] 创建流量统计脚本..."

cat > "$SCRIPT" << 'SCRIPT_EOF'
#!/bin/bash
#
# 每小时流量统计脚本
# 由 setup_vnstat.sh 自动生成
#

LOG="/var/log/traffic_hourly.log"
INTERFACE=$(ip route show default 2>/dev/null | awk '/default/{print $5}' | head -1)
[ -z "$INTERFACE" ] && INTERFACE="eth0"

DATE=$(date +%Y-%m-%d)
HOUR=$(date +%H:%M)

# 使用 vnstat 获取当天流量统计
# --json 输出便于解析
VNSTAT_JSON=$(vnstat --json d 2>/dev/null)

if [ -n "$VNSTAT_JSON" ] && command -v python3 &>/dev/null; then
    # 使用 python3 解析 JSON
    STATS=$(python3 -c "
import json, sys
try:
    data = json.loads('''$VNSTAT_JSON''')
    # 获取今天的流量
    today = data.get('vnstat', {}).get('interfaces', [{}])[0].get('traffic', {}).get('day', [{}])
    if today:
        latest = today[-1]
        rx = latest.get('rx', 0)
        tx = latest.get('tx', 0)
        # vnstat 返回的是 KB，转换为 MB 和 GB
        rx_mb = rx / 1024
        tx_mb = tx / 1024
        rx_gb = rx / 1024 / 1024
        tx_gb = tx / 1024 / 1024
        print(f'RX: {rx_mb:.2f} MB ({rx_gb:.2f} GB) | TX: {tx_mb:.2f} MB ({tx_gb:.2f} GB)')
    else:
        print('RX: 0.00 MB (0.00 GB) | TX: 0.00 MB (0.00 GB)')
except:
    print('RX: N/A | TX: N/A')
" 2>/dev/null)
else
    # 降级方案：直接解析 vnstat 文本输出
    VNSTAT_TEXT=$(vnstat -h 2>/dev/null | tail -5)
    STATS="详见 vnstat -h"
fi

# 获取当前小时的增量（从 /proc/net/dev）
STATE_FILE="/var/log/traffic_state_${INTERFACE}.dat"
RX_CURRENT=$(cat /sys/class/net/$INTERFACE/statistics/rx_bytes 2>/dev/null || echo 0)
TX_CURRENT=$(cat /sys/class/net/$INTERFACE/statistics/tx_bytes 2>/dev/null || echo 0)

if [ -f "$STATE_FILE" ]; then
    source "$STATE_FILE"
    RX_LAST=${RX_LAST:-$RX_CURRENT}
    TX_LAST=${TX_LAST:-$TX_CURRENT}
else
    RX_LAST=$RX_CURRENT
    TX_LAST=$TX_CURRENT
fi

RX_DIFF=$((RX_CURRENT - RX_LAST))
TX_DIFF=$((TX_CURRENT - TX_LAST))

# 防止负数（计数器溢出）
[ $RX_DIFF -lt 0 ] && RX_DIFF=0
[ $TX_DIFF -lt 0 ] && TX_DIFF=0

RX_INC_MB=$(awk "BEGIN {printf \"%.2f\", $RX_DIFF / 1024 / 1024}")
TX_INC_MB=$(awk "BEGIN {printf \"%.2f\", $TX_DIFF / 1024 / 1024}")
RX_INC_GB=$(awk "BEGIN {printf \"%.2f\", $RX_DIFF / 1024 / 1024 / 1024}")
TX_INC_GB=$(awk "BEGIN {printf \"%.2f\", $TX_DIFF / 1024 / 1024 / 1024}")

echo "$DATE $HOUR | 本小时增量: RX +${RX_INC_MB}MB / TX +${TX_INC_MB}MB | 当日累计: $STATS"

# 保存状态
echo "RX_LAST=$RX_CURRENT" > "$STATE_FILE"
echo "TX_LAST=$TX_CURRENT" >> "$STATE_FILE"

SCRIPT_EOF

chmod +x "$SCRIPT"
echo "  ✅ 脚本已创建: $SCRIPT"

# 4. 写入 crontab
echo ""
echo "[4/4] 配置定时任务..."

# 检查是否已存在
if crontab -l 2>/dev/null | grep -qF "traffic_hourly.sh"; then
    echo "  ⚠️  定时任务已存在，跳过添加"
else
    (crontab -l 2>/dev/null; echo "$CRONJOB") | crontab -
    echo "  ✅ 定时任务已添加（每小时整点运行）"
fi

# 创建日志文件
touch "$LOG"
chmod 644 "$LOG"

# 首次运行测试
echo ""
echo "=========================================="
echo "  ✅ 部署完成！"
echo "=========================================="
echo ""
echo "📊 配置信息："
echo "  - 网络接口: $INTERFACE"
echo "  - 统计脚本: $SCRIPT"
echo "  - 日志文件: $LOG"
echo "  - 定时任务: 每小时整点运行"
echo ""
echo "📋 常用命令："
echo "  - 查看实时统计: vnstat -l"
echo "  - 查看今日统计: vnstat -d"
echo "  - 查看本月统计: vnstat -m"
echo "  - 查看小时统计: vnstat -h"
echo "  - 查看日志:     tail -f $LOG"
echo ""

# 首次运行脚本测试
echo "🔄 首次运行测试..."
$SCRIPT
echo ""
echo "Done!"
