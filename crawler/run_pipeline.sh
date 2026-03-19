#!/bin/bash
set -e

# 加载环境变量（cron 环境下需要）
source /etc/environment 2>/dev/null || true

echo "========================================"
echo "[$(date)] 开始执行爬虫管线"
echo "========================================"

# 第一步：从 wewe-rss 拉取文章
echo "[$(date)] 步骤 1/2: 拉取微信文章..."
python /app/scraper.py

# 第二步：用 LLM 分析文章
echo "[$(date)] 步骤 2/2: LLM 分析文章..."
python /app/article_analyzer.py

echo "========================================"
echo "[$(date)] 管线执行完成"
echo "========================================"
