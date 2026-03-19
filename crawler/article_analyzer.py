"""
文章分析器：读取 wechat_data_archive.json，用 LLM 分析每篇文章，
分类为 GitHub 项目 / 论文 / 其他，提取结构化数据，
追加到 daily-ai-trending 的 JSONL 文件中。

用法：
    python article_analyzer.py

环境变量：
    OUTPUT_DIR  — 输出根目录（默认当前目录，Docker 中挂载为 /app/output）
"""

import json
import logging
import os
import re
from datetime import datetime, timedelta

from github_enricher import enrich_github_record
from llm_client import get_openai_client, resolve_model_name

# ================= 配置 =================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("DATA_DIR", SCRIPT_DIR)
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", SCRIPT_DIR)

ARCHIVE_FILE = os.path.join(DATA_DIR, "wechat_data_archive.json")
PROCESSED_FILE = os.path.join(DATA_DIR, "processed_urls.json")
LOG_FILE = os.path.join(DATA_DIR, "analyzer.log")
# ========================================

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是一个专业的技术文章分析助手。你的任务是分析微信公众号文章，判断其主要介绍的内容类型，并提取结构化信息。

请判断文章属于以下三类之一：
1. **github_project** — 文章主要介绍一个 GitHub 开源项目
2. **paper** — 文章主要介绍一篇学术论文或技术报告
3. **other** — 都不是

注意：一篇文章可能同时提到多个项目或论文，请提取文章**最核心/最主要介绍**的那一个。

请严格按照以下 JSON 格式返回结果，不要输出其他任何内容：

如果是 github_project：
```json
{
  "type": "github_project",
  "data": {
    "repo_name": "仓库名",
    "repo_owner": "仓库所有者",
    "repo_path": "owner/repo",
    "repo_url": "https://github.com/owner/repo",
    "description": "用几百字详细总结该项目是做什么的，有什么特点和亮点，适合什么场景使用。要求内容详实、有信息量，能让读者快速了解项目全貌。",
    "language": "主要编程语言（文中未提及则留空字符串）",
    "stars": 0,
    "forks": 0,
    "stars_today": 0,
    "readme": "从文章内容中提取的项目核心介绍文本，尽量还原项目的主要功能说明",
    "topics": ["相关标签1", "相关标签2"],
    "last_updated": "",
    "license": null
  }
}
```

如果是 paper：
```json
{
  "type": "paper",
  "data": {
    "paper_id": "论文编号（如 arxiv ID 2401.12345，文中未提及则留空字符串）",
    "detail_url": "论文详情页链接（如 huggingface papers 链接，文中未提及则留空字符串）",
    "submitter": "",
    "title": "论文标题",
    "authors": "作者列表，逗号分隔",
    "abstract": "用几百字详细总结论文的核心贡献、方法、实验结论和亮点。要求内容详实、有信息量。",
    "paper_url": "论文链接（arxiv 等，文中未提及则留空字符串）",
    "github_url": "代码仓库链接（文中未提及则留空字符串）",
    "upvotes": 0,
    "ai_summary": "用一句话总结论文核心贡献"
  }
}
```

如果是 other：
```json
{
  "type": "other",
  "data": {}
}
```

要求：
- stars、forks、upvotes 仅在文章中明确提到具体数字时填写，否则填 0
- description 和 abstract 字段需要几百字的详细总结，不能只是一句话
- 从文章中尽量提取 arxiv ID（如 2401.12345 格式），如果找到请填入 paper_id
- topics 从文章关键词中提取，没有则留空数组
- 只返回 JSON，不要有其他文字"""


def _load_processed_urls() -> set:
    if os.path.exists(PROCESSED_FILE):
        try:
            with open(PROCESSED_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except Exception:
            pass
    return set()


def _save_processed_urls(urls: set):
    with open(PROCESSED_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(urls), f, ensure_ascii=False, indent=2)


def _get_github_output_path(today: str) -> str:
    """返回 github JSONL 输出路径，格式: github_data/github_daily_YYYY-MM-DD.jsonl"""
    dirpath = os.path.join(OUTPUT_DIR, "github_data")
    os.makedirs(dirpath, exist_ok=True)
    return os.path.join(dirpath, f"github_daily_{today}.jsonl")


def _get_paper_output_path(today: str) -> str:
    """返回 paper JSONL 输出路径。
    命名规则与 daily-ai-trending 一致：arXiv_daily_昨天_今天.jsonl
    例如 3月19日运行 → arXiv_daily_2026-03-18_2026-03-19.jsonl
    """
    dirpath = os.path.join(OUTPUT_DIR, "huggingface_data")
    os.makedirs(dirpath, exist_ok=True)
    yesterday = (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
    return os.path.join(dirpath, f"arXiv_daily_{yesterday}_{today}.jsonl")


def _append_jsonl(filepath: str, record: dict):
    with open(filepath, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _load_existing_jsonl_keys(filepath: str, record_type: str) -> set[str]:
    keys: set[str] = set()
    if not os.path.exists(filepath):
        return keys

    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue

            key = _record_dedupe_key(record_type, record)
            if key:
                keys.add(key)

    return keys


def _record_dedupe_key(record_type: str, record: dict) -> str:
    if record_type == "github":
        for value in (
            (record.get("repo_path") or "").strip().lower(),
            (record.get("repo_url") or "").strip().lower(),
            (record.get("source_url") or "").strip().lower(),
        ):
            if value:
                return value
        return ""

    if record_type == "paper":
        for value in (
            (record.get("paper_id") or "").strip().lower(),
            (record.get("paper_url") or "").strip().lower(),
            (record.get("detail_url") or "").strip().lower(),
            (record.get("source_url") or "").strip().lower(),
        ):
            if value:
                return value

        title = (record.get("title") or "").strip().lower()
        authors = (record.get("authors") or "").strip().lower()
        if title:
            return f"{title}::{authors}"

    return ""


def _extract_json_from_response(text: str) -> dict | None:
    """从 LLM 回复中提取 JSON，兼容 markdown 代码块和裸 JSON。"""
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    if match:
        text = match.group(1)
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        return None


def _extract_github_repo_urls(text: str) -> list[str]:
    """Extract full GitHub repository URLs found in article content."""
    if not text:
        return []

    matches = re.findall(
        r"https?://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)(?:\.git)?(?:[/?#][^\s\"'<>]*)?",
        text,
        flags=re.IGNORECASE,
    )

    urls: list[str] = []
    seen: set[str] = set()
    for owner, repo in matches:
        normalized = f"https://github.com/{owner}/{repo.removesuffix('.git')}"
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        urls.append(normalized)
    return urls


def _parse_github_repo_url(repo_url: str) -> tuple[str, str] | None:
    if not repo_url:
        return None

    match = re.match(
        r"https?://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)",
        repo_url.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None

    owner = match.group(1)
    repo = match.group(2).removesuffix(".git")
    return owner, repo


def _normalize_github_project_data(data: dict, article: dict) -> dict:
    """Prefer repository metadata that can be verified from article content."""
    normalized = dict(data or {})
    repo_url = (normalized.get("repo_url") or "").strip()
    repo_path = (normalized.get("repo_path") or "").strip().strip("/")
    repo_name = (normalized.get("repo_name") or "").strip()
    content = article.get("content_text", "")

    repo_urls = _extract_github_repo_urls(content)
    parsed_repo_url = _parse_github_repo_url(repo_url)

    selected_url = ""
    if parsed_repo_url:
        normalized_repo_url = f"https://github.com/{parsed_repo_url[0]}/{parsed_repo_url[1]}"
        extracted_lookup = {url.lower(): url for url in repo_urls}
        selected_url = extracted_lookup.get(normalized_repo_url.lower(), normalized_repo_url)
    else:
        repo_path_match = None
        if re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo_path):
            repo_path_match = next(
                (url for url in repo_urls if url.lower().endswith(f"/{repo_path.lower()}")),
                None,
            )

        repo_name_match = None
        if repo_name:
            repo_name_match = next(
                (url for url in repo_urls if url.rsplit("/", 1)[-1].lower() == repo_name.lower()),
                None,
            )

        if repo_path_match:
            selected_url = repo_path_match
        elif repo_name_match:
            selected_url = repo_name_match
        elif len(repo_urls) == 1:
            selected_url = repo_urls[0]

    if selected_url:
        owner, repo = _parse_github_repo_url(selected_url)
        normalized["repo_url"] = selected_url
        normalized["repo_owner"] = owner
        normalized["repo_name"] = repo
        normalized["repo_path"] = f"{owner}/{repo}"
    elif repo_path and re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo_path):
        owner, repo = repo_path.split("/", 1)
        normalized["repo_url"] = f"https://github.com/{owner}/{repo}"
        normalized["repo_owner"] = normalized.get("repo_owner") or owner
        normalized["repo_name"] = normalized.get("repo_name") or repo
        normalized["repo_path"] = f"{owner}/{repo}"

    return normalized


def _has_valid_github_repo(data: dict) -> bool:
    """Return True when repo metadata resolves to a concrete owner/repo."""
    repo_path = (data.get("repo_path") or "").strip().strip("/")
    if re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo_path):
        return True

    return _parse_github_repo_url((data.get("repo_url") or "").strip()) is not None


def _build_github_record(data: dict, today: str, source_url: str) -> dict:
    """构建与 daily-ai-trending GitHub 格式完全一致的记录。"""
    return {
        "repo_name": data.get("repo_name", ""),
        "repo_owner": data.get("repo_owner", ""),
        "repo_path": data.get("repo_path", ""),
        "repo_url": data.get("repo_url", ""),
        "description": data.get("description", ""),
        "language": data.get("language", ""),
        "stars": data.get("stars", 0),
        "forks": data.get("forks", 0),
        "stars_today": data.get("stars_today", 0),
        "scrape_date": today,
        "time_range": "daily",
        "readme": data.get("readme", ""),
        "topics": data.get("topics", []),
        "last_updated": data.get("last_updated", ""),
        "license": data.get("license"),
        "source_url": source_url,  # 额外字段：标记来源为微信文章
    }


def _build_paper_record(data: dict, source_url: str) -> dict:
    """构建与 daily-ai-trending 论文格式完全一致的记录。"""
    return {
        "paper_id": data.get("paper_id", ""),
        "detail_url": data.get("detail_url", ""),
        "submitter": data.get("submitter", ""),
        "title": data.get("title", ""),
        "authors": data.get("authors", ""),
        "abstract": data.get("abstract", ""),
        "paper_url": data.get("paper_url", ""),
        "github_url": data.get("github_url", ""),
        "upvotes": data.get("upvotes", 0),
        "ai_summary": data.get("ai_summary", ""),
        "source_url": source_url,  # 额外字段：标记来源为微信文章
    }


def analyze_article(client, model: str, article: dict) -> dict | None:
    """调用 LLM 分析单篇文章，返回解析后的 JSON dict，失败返回 None。"""
    title = article.get("title", "")
    content = article.get("content_text", "")

    user_message = f"文章标题：{title}\n\n文章内容：\n{content}"

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            temperature=0.1,
        )
        reply = response.choices[0].message.content
        if not reply:
            logger.warning("LLM 返回空内容: %s", title)
            return None

        result = _extract_json_from_response(reply)
        if result is None:
            logger.warning("无法解析 LLM 返回的 JSON: %s | 原文: %s", title, reply[:200])
            return None

        if result.get("type") == "github_project" and isinstance(result.get("data"), dict):
            result["data"] = _normalize_github_project_data(result["data"], article)

        return result
    except Exception as e:
        logger.error("LLM 调用失败 [%s]: %s", title, e)
        return None


def run():
    # 读取存档
    if not os.path.exists(ARCHIVE_FILE):
        logger.error("存档文件不存在: %s", ARCHIVE_FILE)
        return

    with open(ARCHIVE_FILE, "r", encoding="utf-8") as f:
        articles = json.load(f)

    logger.info("读取 %d 篇文章", len(articles))

    # 加载已处理记录
    processed_urls = _load_processed_urls()
    pending = [a for a in articles if a.get("url") and a["url"] not in processed_urls]
    logger.info("待处理 %d 篇（已跳过 %d 篇）", len(pending), len(articles) - len(pending))

    if not pending:
        logger.info("没有新文章需要处理")
        return

    # 初始化 LLM 客户端
    client, endpoint = get_openai_client()
    model = resolve_model_name()
    logger.info("使用模型: %s，端点: %s", model, endpoint)

    today = datetime.now().strftime("%Y-%m-%d")
    github_output = _get_github_output_path(today)
    paper_output = _get_paper_output_path(today)
    existing_github_keys = _load_existing_jsonl_keys(github_output, "github")
    existing_paper_keys = _load_existing_jsonl_keys(paper_output, "paper")

    github_count = 0
    paper_count = 0
    other_count = 0

    for i, article in enumerate(pending, 1):
        url = article["url"]
        title = article.get("title", "无标题")
        logger.info("[%d/%d] 分析: %s", i, len(pending), title)

        result = analyze_article(client, model, article)
        if result is None:
            logger.warning("跳过: %s", title)
            continue

        article_type = result.get("type", "other")
        data = result.get("data", {})

        if article_type == "github_project" and data:
            record = _build_github_record(data, today, url)
            # 调用 GitHub API 补全真实数据（stars/forks/readme/topics/license 等）
            record = enrich_github_record(record)
            if not _has_valid_github_repo(record):
                logger.warning(
                    "Skip invalid GitHub project output: %s | repo_url=%s | repo_path=%s",
                    title, record.get("repo_url", ""), record.get("repo_path", "")
                )
                other_count += 1
                processed_urls.add(url)
                continue
            else:
                dedupe_key = _record_dedupe_key("github", record)
                if dedupe_key and dedupe_key in existing_github_keys:
                    logger.info("  ↳ GitHub 项目重复，跳过追加: %s", record.get("repo_path", "") or record.get("repo_url", ""))
                    processed_urls.add(url)
                    continue
                else:
                    _append_jsonl(github_output, record)
                    if dedupe_key:
                        existing_github_keys.add(dedupe_key)
                    github_count += 1
            logger.info("  → GitHub 项目: %s → %s", record.get("repo_path", ""), github_output)

        elif article_type == "paper" and data:
            record = _build_paper_record(data, url)
            dedupe_key = _record_dedupe_key("paper", record)
            if dedupe_key and dedupe_key in existing_paper_keys:
                logger.info("  ↳ 论文重复，跳过追加: %s", record.get("paper_id", "") or record.get("title", ""))
                processed_urls.add(url)
                continue
            else:
                _append_jsonl(paper_output, record)
                if dedupe_key:
                    existing_paper_keys.add(dedupe_key)
                paper_count += 1
            logger.info("  → 论文: %s → %s", data.get("title", ""), paper_output)

        else:
            other_count += 1
            logger.info("  → 其他类型，跳过")

        # 标记为已处理
        processed_urls.add(url)

    # 保存处理记录
    _save_processed_urls(processed_urls)
    logger.info(
        "处理完成！GitHub 项目: %d 篇, 论文: %d 篇, 其他: %d 篇",
        github_count, paper_count, other_count,
    )
    logger.info("GitHub 输出: %s", github_output)
    logger.info("论文输出: %s", paper_output)


if __name__ == "__main__":
    run()
