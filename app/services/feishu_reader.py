# 这个模块负责把飞书 / Lark 文档链接转换为可用于生成用例的正文上下文。
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, unquote, urlparse

import httpx
from dotenv import load_dotenv


load_dotenv()


MAX_FEISHU_LINKS = 5
DEFAULT_MAX_CONTENT_CHARS = 12000
FEISHU_DOMAINS = ("feishu.cn", "larksuite.com")
URL_PATTERN = re.compile(r"https?://[^\s<>'\"]+")


@dataclass
class FeishuLink:
    url: str
    resource_type: str
    token: str
    api_base_url: str


@dataclass
class FeishuReadResult:
    url: str
    resource_type: str = ""
    token: str = ""
    title: str = ""
    content: str = ""
    status: str = "skipped"
    message: str = ""

    @property
    def ok(self) -> bool:
        return self.status == "success" and bool(self.content.strip())

    def to_status_text(self) -> str:
        if self.ok:
            title = self.title or self.token or "未命名文档"
            return f"飞书链接已读取：{title}（约 {len(self.content)} 字）。"
        return f"飞书链接未读取：{self.message or self.url}"


async def fetch_feishu_references(references: str) -> list[FeishuReadResult]:
    links = extract_feishu_links(references)
    if not links:
        return []

    app_id = os.getenv("FEISHU_APP_ID", "").strip()
    app_secret = os.getenv("FEISHU_APP_SECRET", "").strip()
    if not app_id or not app_secret:
        return [
            FeishuReadResult(
                url=link.url,
                resource_type=link.resource_type,
                token=link.token,
                status="missing_config",
                message="检测到飞书链接，但未配置 FEISHU_APP_ID / FEISHU_APP_SECRET，已仅作为链接线索使用。",
            )
            for link in links
        ]

    timeout_seconds = _env_float("FEISHU_READ_TIMEOUT_SECONDS", 20.0)
    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
        tokens: dict[str, str] = {}
        results: list[FeishuReadResult] = []
        for link in links:
            try:
                tenant_token = tokens.get(link.api_base_url)
                if not tenant_token:
                    tenant_token = await _get_tenant_access_token(client, link.api_base_url, app_id, app_secret)
                    tokens[link.api_base_url] = tenant_token
                results.append(await _read_link(client, link, tenant_token))
            except Exception as exc:
                results.append(
                    FeishuReadResult(
                        url=link.url,
                        resource_type=link.resource_type,
                        token=link.token,
                        status="error",
                        message=f"{link.url} 读取失败：{exc}",
                    )
                )
        return results


def extract_feishu_links(references: str) -> list[FeishuLink]:
    custom_base = os.getenv("FEISHU_API_BASE_URL", "").strip()
    links: list[FeishuLink] = []
    seen: set[tuple[str, str]] = set()

    for raw_url in URL_PATTERN.findall(references or ""):
        url = _clean_url(raw_url)
        parsed = urlparse(url)
        host = parsed.netloc.lower()
        if not any(domain in host for domain in FEISHU_DOMAINS):
            continue

        resource_type, token = _parse_resource(parsed.path)
        if not token:
            links.append(
                FeishuLink(
                    url=url,
                    resource_type="unsupported",
                    token="",
                    api_base_url=_api_base_for_host(host, custom_base),
                )
            )
            continue

        key = (resource_type, token)
        if key in seen:
            continue
        seen.add(key)
        links.append(
            FeishuLink(
                url=url,
                resource_type=resource_type,
                token=token,
                api_base_url=_api_base_for_host(host, custom_base),
            )
        )
        if len(links) >= MAX_FEISHU_LINKS:
            break
    return links


def build_feishu_context(results: list[FeishuReadResult]) -> str:
    if not results:
        return ""

    max_chars = _env_int("FEISHU_MAX_CONTENT_CHARS", DEFAULT_MAX_CONTENT_CHARS)
    lines = ["飞书链接读取结果："]
    for result in results:
        if result.ok:
            title = result.title or result.token or "未命名文档"
            lines.extend(
                [
                    f"\n【飞书文档：{title}】",
                    f"来源：{result.url}",
                    _limit_text(result.content, max_chars),
                ]
            )
        else:
            lines.append(f"- {result.url}：{result.message or '未读取正文'}")
    return "\n".join(lines).strip()


async def _read_link(client: httpx.AsyncClient, link: FeishuLink, tenant_token: str) -> FeishuReadResult:
    if link.resource_type == "unsupported":
        return FeishuReadResult(
            url=link.url,
            resource_type=link.resource_type,
            status="unsupported",
            message="当前仅支持 docx、旧版 docs/doc 和 wiki 文档链接。",
        )

    if link.resource_type == "wiki":
        obj_type, obj_token, title = await _resolve_wiki_node(client, link, tenant_token)
        if obj_type not in {"docx", "doc"}:
            return FeishuReadResult(
                url=link.url,
                resource_type=obj_type,
                token=obj_token,
                title=title,
                status="unsupported",
                message=f"Wiki 节点类型 {obj_type or '未知'} 暂不支持读取正文。",
            )
        content, content_title = await _read_document_content(client, link.api_base_url, obj_type, obj_token, tenant_token)
        return FeishuReadResult(
            url=link.url,
            resource_type=obj_type,
            token=obj_token,
            title=content_title or title,
            content=content,
            status="success",
            message="已通过 Wiki 节点解析读取正文。",
        )

    content, title = await _read_document_content(
        client,
        link.api_base_url,
        link.resource_type,
        link.token,
        tenant_token,
    )
    return FeishuReadResult(
        url=link.url,
        resource_type=link.resource_type,
        token=link.token,
        title=title,
        content=content,
        status="success",
        message="已读取正文。",
    )


async def _get_tenant_access_token(
    client: httpx.AsyncClient,
    api_base_url: str,
    app_id: str,
    app_secret: str,
) -> str:
    response = await client.post(
        f"{api_base_url}/auth/v3/tenant_access_token/internal",
        json={"app_id": app_id, "app_secret": app_secret},
    )
    payload = _response_json(response)
    if payload.get("code") != 0:
        raise ValueError(f"获取 tenant_access_token 失败：{payload.get('msg') or payload.get('message') or payload.get('code')}")
    token = payload.get("tenant_access_token") or payload.get("tenant_accessToken")
    if not token:
        raise ValueError("获取 tenant_access_token 失败：响应中没有 token。")
    return str(token)


async def _resolve_wiki_node(
    client: httpx.AsyncClient,
    link: FeishuLink,
    tenant_token: str,
) -> tuple[str, str, str]:
    response = await client.get(
        f"{link.api_base_url}/wiki/v2/spaces/get_node",
        headers=_auth_headers(tenant_token),
        params={"token": link.token},
    )
    data = _feishu_data(response, "解析 Wiki 节点失败")
    node = data.get("node") if isinstance(data.get("node"), dict) else data
    obj_type = str(node.get("obj_type") or node.get("objType") or "")
    obj_token = str(node.get("obj_token") or node.get("objToken") or "")
    title = str(node.get("title") or "")
    if not obj_token:
        raise ValueError("解析 Wiki 节点失败：响应中没有 obj_token。")
    return obj_type, obj_token, title


async def _read_document_content(
    client: httpx.AsyncClient,
    api_base_url: str,
    resource_type: str,
    token: str,
    tenant_token: str,
) -> tuple[str, str]:
    if resource_type == "docx":
        return await _read_docx_content(client, api_base_url, token, tenant_token)
    if resource_type == "doc":
        return await _read_legacy_doc_content(client, api_base_url, token, tenant_token)
    raise ValueError(f"文档类型 {resource_type} 暂不支持读取正文。")


async def _read_docx_content(
    client: httpx.AsyncClient,
    api_base_url: str,
    document_id: str,
    tenant_token: str,
) -> tuple[str, str]:
    response = await client.get(
        f"{api_base_url}/docx/v1/documents/{quote(document_id, safe='')}/raw_content",
        headers=_auth_headers(tenant_token),
    )
    data = _feishu_data(response, "读取新版飞书文档失败")
    content = _pick_content(data)
    title = _pick_title(data)
    if not content:
        raise ValueError("读取新版飞书文档失败：响应中没有正文 content。")
    return content, title


async def _read_legacy_doc_content(
    client: httpx.AsyncClient,
    api_base_url: str,
    doc_token: str,
    tenant_token: str,
) -> tuple[str, str]:
    response = await client.get(
        f"{api_base_url}/doc/v2/{quote(doc_token, safe='')}/content",
        headers=_auth_headers(tenant_token),
    )
    data = _feishu_data(response, "读取旧版飞书文档失败")
    content = _pick_content(data)
    title = _pick_title(data)
    if not content:
        raise ValueError("读取旧版飞书文档失败：响应中没有正文 content。")
    return content, title


def _feishu_data(response: httpx.Response, action: str) -> dict[str, Any]:
    payload = _response_json(response)
    if payload.get("code") != 0:
        raise ValueError(f"{action}：{payload.get('msg') or payload.get('message') or payload.get('code')}")
    data = payload.get("data")
    return data if isinstance(data, dict) else {}


def _response_json(response: httpx.Response) -> dict[str, Any]:
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("飞书接口响应不是 JSON 对象。")
    return payload


def _auth_headers(tenant_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {tenant_token}"}


def _pick_content(data: dict[str, Any]) -> str:
    for key in ("content", "raw_content", "text"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    document = data.get("document")
    if isinstance(document, dict):
        return _pick_content(document)
    return ""


def _pick_title(data: dict[str, Any]) -> str:
    for key in ("title", "name"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    document = data.get("document")
    if isinstance(document, dict):
        return _pick_title(document)
    return ""


def _parse_resource(path: str) -> tuple[str, str]:
    segments = [unquote(item) for item in path.split("/") if item]
    for index, segment in enumerate(segments):
        name = segment.lower()
        if name == "wiki" and index + 1 < len(segments):
            return "wiki", segments[index + 1]
        if name == "docx" and index + 1 < len(segments):
            return "docx", segments[index + 1]
        if name in {"docs", "doc"} and index + 1 < len(segments):
            return "doc", segments[index + 1]
    return "", ""


def _api_base_for_host(host: str, custom_base: str) -> str:
    if custom_base:
        return _normalize_api_base(custom_base)
    if "larksuite.com" in host:
        return "https://open.larksuite.com/open-apis"
    return "https://open.feishu.cn/open-apis"


def _normalize_api_base(base_url: str) -> str:
    base_url = base_url.rstrip("/")
    if base_url.endswith("/open-apis"):
        return base_url
    return f"{base_url}/open-apis"


def _clean_url(url: str) -> str:
    return url.rstrip(").,;，。；、]】")


def _limit_text(text: str, limit: int) -> str:
    text = re.sub(r"\n{4,}", "\n\n\n", text.strip())
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "\n... 飞书正文已截断"


def _env_float(name: str, fallback: float) -> float:
    try:
        return float(os.getenv(name, "").strip() or fallback)
    except ValueError:
        return fallback


def _env_int(name: str, fallback: int) -> int:
    try:
        return int(os.getenv(name, "").strip() or fallback)
    except ValueError:
        return fallback
