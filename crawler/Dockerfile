FROM python:3.12-slim

# 安装 cron
RUN apt-get update && apt-get install -y --no-install-recommends cron && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 安装 Python 依赖
RUN pip install --no-cache-dir openai requests

# 复制爬虫脚本
COPY scraper.py llm_client.py article_analyzer.py archive_info.py /app/

# 复制启动和流水线脚本
COPY entrypoint.sh run_pipeline.sh /app/
RUN chmod +x /app/entrypoint.sh /app/run_pipeline.sh

# 创建数据和输出目录
RUN mkdir -p /app/data /app/output/github_data /app/output/huggingface_data

# 环境变量默认值
ENV DATA_DIR=/app/data
ENV OUTPUT_DIR=/app/output
ENV WEWE_RSS_URL=http://app:4000
ENV CRAWLER_CRON="0 2 * * *"
ENV TZ=Asia/Shanghai

ENTRYPOINT ["/app/entrypoint.sh"]
