"""
GitHub API 数据补全模块：
从 GitHub API 拉取仓库的真实元数据（stars/forks/readme/topics/license 等），
补全 LLM 从文章中提取的不完整数据。

GitHub API 免费额度：
  - 无 Token: 60 次/小时
  - 有 Token: 5000 次/小时
每个仓库需要 2 次请求（仓库信息 + README），每天处理几篇文章完全够用。
"""

import base64
import logging
import os
import re

import requests

logger = logging.getLogger(__name__)

# 可选：通过环境变量配置 GitHub Token 提高速率限制
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_API_TIMEOUT = 15  # 秒


def _github_headers() -> dict:
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "WeChat-Crawler-Bot",
    }
    if GITHUB_TOKEN:
        headers["Authorization"] = f"token {GITHUB_TOKEN}"
    return headers


def _parse_repo_path(repo_url: str) -> tuple[str, str] | None:
    """从 GitHub URL 中提取 owner 和 repo 名称。"""
    # 支持多种格式：
    #   https://github.com/owner/repo
    #   https://github.com/owner/repo.git
    #   https://github.com/owner/repo/tree/main
    match = re.match(r"https?://github\.com/([^/]+)/([^/?.#]+)", repo_url)
    if match:
        owner = match.group(1)
        repo = match.group(2).removesuffix(".git")
        return owner, repo
    return None


def _normalize_repo_url(record: dict) -> str:
    """Return a usable repository URL from repo_url or repo_path."""
    repo_url = (record.get("repo_url") or "").strip()
    if _parse_repo_path(repo_url):
        return repo_url

    repo_path = (record.get("repo_path") or "").strip().strip("/")
    if re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo_path):
        normalized = f"https://github.com/{repo_path}"
        logger.info("  ↳ repo_url invalid, fallback to repo_path: %s", normalized)
        return normalized

    return repo_url


def fetch_repo_info(repo_url: str) -> dict | None:
    """调用 GitHub API 获取仓库元数据，失败返回 None。"""
    parsed = _parse_repo_path(repo_url)
    if not parsed:
        logger.warning("无法解析 GitHub URL: %s", repo_url)
        return None

    owner, repo = parsed
    api_url = f"https://api.github.com/repos/{owner}/{repo}"

    try:
        resp = requests.get(api_url, headers=_github_headers(), timeout=GITHUB_API_TIMEOUT)
        if resp.status_code == 404:
            logger.warning("仓库不存在: %s/%s", owner, repo)
            return None
        if resp.status_code == 403:
            logger.warning("GitHub API 速率限制，跳过补全: %s/%s", owner, repo)
            return None
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error("GitHub API 请求失败 [%s/%s]: %s", owner, repo, e)
        return None


def fetch_readme(repo_url: str) -> str:
    """获取仓库 README 内容（纯文本），失败返回空字符串。"""
    parsed = _parse_repo_path(repo_url)
    if not parsed:
        return ""

    owner, repo = parsed
    api_url = f"https://api.github.com/repos/{owner}/{repo}/readme"

    try:
        resp = requests.get(api_url, headers=_github_headers(), timeout=GITHUB_API_TIMEOUT)
        if resp.status_code != 200:
            return ""

        data = resp.json()
        # README 内容是 base64 编码的
        content = data.get("content", "")
        encoding = data.get("encoding", "")

        if encoding == "base64" and content:
            try:
                return base64.b64decode(content).decode("utf-8", errors="replace")
            except Exception:
                return ""
        return ""
    except Exception as e:
        logger.error("获取 README 失败 [%s/%s]: %s", owner, repo, e)
        return ""


def enrich_github_record(record: dict) -> dict:
    """用 GitHub API 数据补全 LLM 提取的 GitHub 项目记录。
    
    补全策略：API 数据覆盖 LLM 提取的数值型字段（stars/forks 等），
    但 description 保留 LLM 的详细总结（比 GitHub 原始描述更有价值）。
    """
    repo_url = _normalize_repo_url(record)
    if not repo_url:
        logger.warning("缺少 repo_url，跳过 GitHub API 补全")
        return record

    logger.info("  ↳ GitHub API 补全: %s", repo_url)

    # 1. 获取仓库信息
    record["repo_url"] = repo_url
    repo_info = fetch_repo_info(repo_url)
    if repo_info:
        # 精确数据覆盖 LLM 猜测值
        record["repo_name"] = repo_info.get("name", record.get("repo_name", ""))
        record["repo_owner"] = repo_info.get("owner", {}).get("login", record.get("repo_owner", ""))
        record["repo_path"] = repo_info.get("full_name", record.get("repo_path", ""))
        record["repo_url"] = repo_info.get("html_url", record.get("repo_url", ""))
        record["language"] = repo_info.get("language", "") or ""
        record["stars"] = repo_info.get("stargazers_count", 0)
        record["forks"] = repo_info.get("forks_count", 0)
        record["topics"] = repo_info.get("topics", [])
        record["last_updated"] = repo_info.get("pushed_at", "")
        record["license"] = (repo_info.get("license") or {}).get("spdx_id") if repo_info.get("license") else None

        # description 保留 LLM 的详细总结，不用 GitHub 的短描述覆盖
        # 如果 LLM 没有生成 description，才用 GitHub 的
        if not record.get("description"):
            record["description"] = repo_info.get("description", "") or ""

        logger.info("    ✓ stars=%d, forks=%d, language=%s, topics=%s",
                     record["stars"], record["forks"], record["language"], record["topics"])
    else:
        logger.warning("    ✗ 仓库信息获取失败，使用 LLM 提取值")

    # 2. 获取 README
    readme = fetch_readme(repo_url)
    if readme:
        record["readme"] = readme
        logger.info("    ✓ README 已获取 (%d 字符)", len(readme))
    else:
        logger.info("    ✗ README 获取失败，使用 LLM 提取值")

    return record
