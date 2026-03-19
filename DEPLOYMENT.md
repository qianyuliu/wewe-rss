# WeChat-Crawler 部署指南

## 项目概述

本项目通过 Docker Compose 部署三个服务，实现**微信公众号文章自动采集 → LLM 智能分析 → 结构化数据输出**的完整流水线。

### 架构图

```
┌─────────────────────────── Docker Compose ───────────────────────────┐
│                                                                      │
│  ┌──────────┐    ┌──────────────────┐    ┌────────────────────────┐  │
│  │  db       │◄──►│  app              │◄──►│  crawler              │  │
│  │  MySQL    │    │  wewe-rss :4000   │    │  Python + Cron        │  │
│  │  8.3.0    │    │  每天 01:00 刷新   │    │  每天 02:00 执行      │  │
│  └──────────┘    └──────────────────┘    └──────────┬─────────────┘  │
│                                                      │               │
└──────────────────────────────────────────────────────┼───────────────┘
                                                       │ 追加写入
                                              ┌────────▼────────┐
                                              │ daily-ai-trending │
                                              │ github_data/      │
                                              │ huggingface_data/  │
                                              └─────────────────┘
```

### 执行时序

| 时间 | 服务 | 动作 |
|------|------|------|
| 每天 01:00 | app (wewe-rss) | 自动刷新公众号，拉取最新文章元数据 |
| 每天 02:00 | crawler | **步骤1**: `scraper.py` 从 wewe-rss API 拉取过去 48 小时文章内容 |
| | | **步骤2**: `article_analyzer.py` 调用 LLM 分析每篇文章 |
| | | 输出 GitHub 项目 → `github_data/github_daily_YYYY-MM-DD.jsonl` |
| | | 输出论文 → `huggingface_data/arXiv_daily_YYYY-MM-DD_YYYY-MM-DD.jsonl` |

---

## 前置要求

- **Docker** 和 **Docker Compose** 已安装
- 内部网关大模型 API 凭证（`OPENAI_API_ID`、`OPENAI_API_SECRET` 等）

---

## 1. 目录结构准备

将两个项目放在**同一级目录**下：

```
C:\projects\                    # (或任意目录)
├── wewe-rss/                   # 本项目
│   ├── docker-compose.yml
│   ├── .env                    # 环境变量配置（需创建）
│   └── crawler/
│       ├── Dockerfile
│       ├── entrypoint.sh
│       ├── run_pipeline.sh
│       ├── scraper.py
│       ├── llm_client.py
│       └── article_analyzer.py
│
└── daily-ai-trending/          # AI 趋势数据项目
    ├── github_data/            # ← crawler 追加写入
    └── huggingface_data/       # ← crawler 追加写入
```

---

## 2. 配置环境变量

在 `wewe-rss/` 目录下创建 `.env` 文件：

```env
# ========================================
#  内部网关大模型配置（必填）
# ========================================
OPENAI_API_ID=your_api_id
OPENAI_API_SECRET=your_api_secret
OPENAI_API_BASE=https://your-internal-gateway/v1
MODEL_ID=your_model_id
MODELSOURCE=your_model_source

# ========================================
#  可选配置
# ========================================
# LLM_MODEL_NAME=gpt-4o-mini          # 模型名称，默认 gpt-4o-mini
# LLM_REQUEST_TIMEOUT=120             # 请求超时，默认 120 秒
```

---

## 3. 自定义配置（可选）

### docker-compose.yml 中可调整的参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `MYSQL_ROOT_PASSWORD` | `123456` | MySQL 数据库密码 |
| `AUTH_CODE` | `123567` | wewe-rss API 授权码 |
| `CRON_EXPRESSION` | `0 0 1 * * *` | wewe-rss 刷新 cron（NestJS 6位格式） |
| `CRAWLER_CRON` | `0 2 * * *` | 爬虫执行 cron（标准5位格式） |
| `FETCH_SINCE_HOURS` | `48` | 拉取最近多少小时的文章 |
| `WEWE_RSS_URL` | `http://app:4000` | wewe-rss 服务地址（容器间通信） |

### 修改 daily-ai-trending 数据目录路径

如果 `daily-ai-trending` 不在 `wewe-rss` 的上级目录，需修改 `docker-compose.yml` 中的卷挂载路径：

```yaml
volumes:
  - /your/actual/path/daily-ai-trending/github_data:/app/output/github_data
  - /your/actual/path/daily-ai-trending/huggingface_data:/app/output/huggingface_data
```

---

## 4. 构建和启动

```bash
cd wewe-rss

# 构建并启动所有服务
docker compose up -d --build

# 查看服务状态
docker compose ps
```

预期输出：
```
NAME              STATUS    PORTS
db                running   3306/tcp
app               running   0.0.0.0:4000->4000/tcp
wewe-crawler      running
```

---

## 5. 添加微信公众号

服务启动后，打开浏览器访问 `http://localhost:4000`（如需授权码则输入上面配置的 `AUTH_CODE`），在管理界面添加需要关注的微信公众号。

---

## 6. 验证部署

### 手动触发一次测试

```bash
# 手动执行爬虫管线
docker compose exec crawler /app/run_pipeline.sh

# 或分步执行
docker compose exec crawler python /app/scraper.py           # 拉取文章
docker compose exec crawler python /app/article_analyzer.py   # LLM 分析
```

### 查看日志

```bash
# 查看 crawler 容器日志
docker compose logs -f crawler

# 查看容器内部详细日志
docker compose exec crawler cat /app/data/analyzer.log
docker compose exec crawler cat /app/data/scraper.log
docker compose exec crawler cat /app/data/cron.log
```

### 验证输出文件

```bash
# 查看 GitHub 项目输出
docker compose exec crawler ls -la /app/output/github_data/

# 查看论文输出
docker compose exec crawler ls -la /app/output/huggingface_data/

# 查看具体内容
docker compose exec crawler cat /app/output/github_data/github_daily_$(date +%Y-%m-%d).jsonl
```

---

## 7. 运维操作

### 查看和管理服务

```bash
docker compose ps          # 查看状态
docker compose logs -f     # 实时日志
docker compose restart crawler    # 重启 crawler
docker compose stop        # 停止所有
docker compose down        # 停止并删除容器
docker compose down -v     # 停止、删除容器和数据卷（⚠️会丢失数据）
```

### 修改定时任务时间

修改 `docker-compose.yml` 中的 `CRAWLER_CRON`，然后重启 crawler：

```bash
docker compose up -d crawler
```

### 清除已处理记录（重新分析）

```bash
docker compose exec crawler rm /app/data/processed_urls.json
docker compose exec crawler python /app/article_analyzer.py
```

---

## 数据说明

### 输出格式

**GitHub 项目**（`github_data/github_daily_YYYY-MM-DD.jsonl`）：

```json
{
  "repo_name": "example",
  "repo_owner": "owner",
  "repo_path": "owner/example",
  "repo_url": "https://github.com/owner/example",
  "description": "几百字的项目详细介绍...",
  "language": "Python",
  "stars": 0,
  "forks": 0,
  "stars_today": 0,
  "scrape_date": "2026-03-19",
  "time_range": "daily",
  "readme": "项目核心介绍文本...",
  "topics": ["ai", "llm"],
  "last_updated": "",
  "license": null,
  "source_url": "https://mp.weixin.qq.com/s/..."
}
```

**论文**（`huggingface_data/arXiv_daily_YYYY-MM-DD_YYYY-MM-DD.jsonl`）：

```json
{
  "paper_id": "2401.12345",
  "detail_url": "",
  "submitter": "",
  "title": "论文标题",
  "authors": "Author1, Author2",
  "abstract": "几百字的论文详细摘要...",
  "paper_url": "https://arxiv.org/abs/2401.12345",
  "github_url": "https://github.com/...",
  "upvotes": 0,
  "ai_summary": "一句话核心总结",
  "source_url": "https://mp.weixin.qq.com/s/..."
}
```

> **注意**：从微信文章提取的记录会多一个 `source_url` 字段标记来源，`stars`/`forks`/`upvotes` 等数值仅在文章中明确提到时才会有值。

---

## 常见问题

### Q: crawler 无法连接 wewe-rss？

确认 `app` 和 `crawler` 在同一个 Docker 网络中。查看网络：
```bash
docker network ls
docker compose exec crawler ping app
```

### Q: LLM 调用失败？

检查环境变量是否正确配置：
```bash
docker compose exec crawler env | grep OPENAI
```

查看详细错误：
```bash
docker compose exec crawler cat /app/data/analyzer.log
```

### Q: 如何更改拉取文章的时间范围？

修改 `docker-compose.yml` 中的 `FETCH_SINCE_HOURS`（单位：小时）：
```yaml
- FETCH_SINCE_HOURS=72    # 拉取最近 72 小时的文章
```
