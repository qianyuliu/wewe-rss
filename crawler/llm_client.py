"""
内部网关大模型客户端。
通过以下环境变量进行配置：

  OPENAI_API_ID       内部网关 API ID（必填）
  OPENAI_API_SECRET   内部网关 API Secret（必填）
  OPENAI_API_BASE     内部网关请求地址（必填）
  MODEL_ID            模型 ID（必填）
  MODELSOURCE         模型来源（必填）
  TRACE_ID            追踪 ID（可选）
  LLM_MODEL_NAME      调用时使用的模型名（可选，默认 gpt-4o-mini）
  LLM_REQUEST_TIMEOUT 请求超时秒数（可选，默认 120）

用法示例：
    from llm_client import get_openai_client, resolve_model_name

    client, endpoint = get_openai_client()
    model = resolve_model_name()
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": "你好"}],
    )
    print(resp.choices[0].message.content)
"""

import base64
import hashlib
import hmac
import os
from datetime import datetime, timezone
from urllib.parse import urlparse

import openai


def _clean(value) -> str:
    return (value or "").strip()


def resolve_model_name(preferred: str | None = None) -> str:
    """返回要使用的模型名。可通过 preferred 参数临时覆盖。"""
    for candidate in (
        preferred,
        os.getenv("LLM_MODEL_NAME"),
        os.getenv("MODEL_NAME"),
        os.getenv("OPENAI_MODEL"),
    ):
        name = _clean(candidate)
        if name:
            return name
    return "gpt-4o-mini"


def _get_signature(host: str, date_str: str, request_line: str, api_secret: str) -> str:
    signing_str = f"host: {host}\ndate: {date_str}\n{request_line}"
    digest = hmac.new(
        api_secret.encode("utf-8"),
        signing_str.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return base64.b64encode(digest).decode("utf-8")


def _build_api_key(
    request_url: str,
    api_key: str,
    api_secret: str,
    model_id: str,
    model_source: str,
    trace_id: str,
) -> str:
    http_method = "POST"
    http_request_url = request_url.replace("ws://", "http://").replace("wss://", "https://")
    parsed_url = urlparse(http_request_url)
    host = parsed_url.hostname or ""
    path = parsed_url.path or "/"
    request_line = f"{http_method} {path} HTTP/1.1"
    date_str = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")
    signature = _get_signature(host, date_str, request_line, api_secret)
    auth_string = (
        f'hmac api_key="{api_key}", algorithm="hmac-sha256", '
        f'headers="host date request-line", signature="{signature}", '
        f'modelId="{model_id}", modelSource="{model_source}", '
        f'traceId="{trace_id}", host="{host}", '
        f'date="{date_str}", request-line="{request_line}"'
    )
    return base64.b64encode(auth_string.encode("utf-8")).decode("utf-8")


def get_openai_client() -> tuple[openai.OpenAI, str]:
    """
    创建并返回 (openai.OpenAI 实例, endpoint 地址)。
    所有配置项均从环境变量读取。
    """
    api_id = _clean(os.getenv("OPENAI_API_ID"))
    api_secret = _clean(os.getenv("OPENAI_API_SECRET"))
    base_url = _clean(os.getenv("OPENAI_API_BASE"))
    model_id = _clean(os.getenv("MODEL_ID"))
    model_source = _clean(os.getenv("MODELSOURCE"))
    trace_id = _clean(os.getenv("TRACE_ID", ""))

    missing = [
        name
        for name, val in {
            "OPENAI_API_ID": api_id,
            "OPENAI_API_SECRET": api_secret,
            "OPENAI_API_BASE": base_url,
            "MODEL_ID": model_id,
            "MODELSOURCE": model_source,
        }.items()
        if not val
    ]
    if missing:
        raise EnvironmentError(
            f"以下环境变量未配置，无法初始化内部网关客户端：{', '.join(missing)}"
        )

    api_key = _build_api_key(
        request_url=base_url,
        api_key=api_id,
        api_secret=api_secret,
        model_id=model_id,
        model_source=model_source,
        trace_id=trace_id,
    )

    timeout = float(os.getenv("LLM_REQUEST_TIMEOUT", "120"))
    client = openai.OpenAI(
        api_key=api_key,
        base_url=base_url,
        timeout=timeout,
    )
    return client, base_url
