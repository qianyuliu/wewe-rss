#!/bin/bash

# 获取当前脚本所在目录的绝对路径
SCRIPT_PATH=$(cd "$(dirname "$0")"; pwd)
SCRAPER_SCRIPT="$SCRIPT_PATH/crawler/scraper.py"
LOG_FILE="$SCRIPT_PATH/crawler/cron.log"

if [ ! -f "$SCRAPER_SCRIPT" ]; then
    echo "错误: 找不到 crawler/scraper.py，请确保脚本路径正确。"
    exit 1
fi

# 定义定时任务 (每天 10:00 和 18:00 运行)
# 注意：macOS crontab 运行时可能找不到 python3，因此建议使用绝对路径
PYTHON_PATH=$(which python3)

if [ -z "$PYTHON_PATH" ]; then
    echo "错误: 找不到 python3，请手动指定 Python 路径。"
    exit 1
fi

CRON_JOB_1="0 10 * * * $PYTHON_PATH $SCRAPER_SCRIPT >> $LOG_FILE 2>&1"
CRON_JOB_2="0 18 * * * $PYTHON_PATH $SCRAPER_SCRIPT >> $LOG_FILE 2>&1"

# 检查是否已经存在
(crontab -l 2>/dev/null | grep -q "$SCRAPER_SCRIPT") && {
    echo "提示: 定时任务已经存在，无需重复添加。"
} || {
    # 添加到 crontab
    (crontab -l 2>/dev/null; echo "$CRON_JOB_1") | crontab -
    (crontab -l 2>/dev/null; echo "$CRON_JOB_2") | crontab -
    echo "成功: 已添加定时任务 (10:00 & 18:00)。"
}

echo "查看当前定时任务:"
crontab -l | grep "$SCRAPER_SCRIPT"
