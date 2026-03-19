#!/bin/bash
set -e

# 将当前环境变量导出到 /etc/environment，让 cron 作业能读到
printenv | grep -v "no_proxy" >> /etc/environment

# 创建 cron 作业
echo "${CRAWLER_CRON} root /app/run_pipeline.sh >> /app/data/cron.log 2>&1" > /etc/cron.d/crawler-cron
chmod 0644 /etc/cron.d/crawler-cron
crontab /etc/cron.d/crawler-cron

echo "[$(date)] Crawler 容器已启动"
echo "[$(date)] Cron 表达式: ${CRAWLER_CRON}"
echo "[$(date)] wewe-rss 地址: ${WEWE_RSS_URL}"
echo "[$(date)] 数据目录: ${DATA_DIR}"
echo "[$(date)] 输出目录: ${OUTPUT_DIR}"

# 前台运行 cron
exec cron -f
