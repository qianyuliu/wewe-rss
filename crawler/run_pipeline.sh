#!/bin/bash
set -e

# 加载环境变量（cron 环境下需要）
source /etc/environment 2>/dev/null || true

APP_WAIT_TIMEOUT="${APP_WAIT_TIMEOUT:-180}"
APP_WAIT_INTERVAL="${APP_WAIT_INTERVAL:-5}"
WEWE_RSS_URL="${WEWE_RSS_URL:-http://app:4000}"

wait_for_app() {
  local deadline=$(( $(date +%s) + APP_WAIT_TIMEOUT ))
  echo "[$(date)] 等待 wewe-rss 服务就绪: ${WEWE_RSS_URL}"

  while [ "$(date +%s)" -lt "${deadline}" ]; do
    if python - <<'PY'
import os
import sys
import requests

base_url = os.environ["WEWE_RSS_URL"].rstrip("/")
url = f"{base_url}/feeds/all.json?limit=1"

try:
    response = requests.get(url, timeout=10)
    response.raise_for_status()
except Exception:
    sys.exit(1)

sys.exit(0)
PY
    then
      echo "[$(date)] wewe-rss 服务已就绪"
      return 0
    fi

    echo "[$(date)] 服务尚未就绪，${APP_WAIT_INTERVAL} 秒后重试..."
    sleep "${APP_WAIT_INTERVAL}"
  done

  echo "[$(date)] 错误: 等待 wewe-rss 服务超时 (${APP_WAIT_TIMEOUT}s)"
  return 1
}

echo "========================================"
echo "[$(date)] 开始执行爬虫管线"
echo "========================================"

wait_for_app

# 第一步：从 wewe-rss 拉取文章
echo "[$(date)] 步骤 1/2: 拉取微信文章..."
python /app/scraper.py

# 第二步：用 LLM 分析文章
echo "[$(date)] 步骤 2/2: LLM 分析文章..."
python /app/article_analyzer.py

echo "========================================"
echo "[$(date)] 管线执行完成"
echo "========================================"
