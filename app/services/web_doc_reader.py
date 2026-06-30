from __future__ import annotations

import ipaddress
import json
import os
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any
from urllib.parse import unquote, urldefrag, urljoin, urlparse

import httpx
from dotenv import load_dotenv


load_dotenv()


URL_PATTERN = re.compile(r"https?://[^\s<>'\"\]]+")
SKIPPED_DOMAINS = ("feishu.cn", "larksuite.com")
DEFAULT_MAX_LINKS = 5
DEFAULT_MAX_PAGES = 8
DEFAULT_MAX_BYTES = 2 * 1024 * 1024
DEFAULT_MAX_CONTEXT_CHARS = 24000
DEFAULT_TIMEOUT_SECONDS = 20.0
ALLOWED_CONTENT_TYPES = (
    "text/html",
    "application/xhtml+xml",
    "text/plain",
    "application/json",
    "application/xml",
    "text/xml",
)
SKIP_PATH_EXTENSIONS = (
    ".apk",
    ".bmp",
    ".css",
    ".doc",
    ".docx",
    ".gif",
    ".ico",
    ".jpeg",
    ".jpg",
    ".js",
    ".mp3",
    ".mp4",
    ".pdf",
    ".png",
    ".rar",
    ".svg",
    ".webp",
    ".xls",
    ".xlsx",
    ".zip",
)


@dataclass
class WebDocLink:
    url: str
    text: str = ""


@dataclass
class WebDocReadResult:
    url: str
    title: str = ""
    content: str = ""
    status: str = "skipped"
    message: str = ""
    discovered_links: list[WebDocLink] | None = None

    @property
    def ok(self) -> bool:
        return self.status == "success" and bool(self.content.strip())

    def to_status_text(self) -> str:
        if self.ok:
            title = self.title or self.url
            return f"网页文档已读取：{title}（约 {len(self.content)} 字）。"
        return f"网页文档未读取：{self.message or self.url}"


async def fetch_web_references(references: str, focus_text: str = "") -> list[WebDocReadResult]:
    links = extract_web_doc_links(references)
    if not links:
        return []

    max_pages = _env_int("WEB_DOC_MAX_PAGES", DEFAULT_MAX_PAGES)
    timeout_seconds = _env_float("WEB_DOC_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS)
    queue = links[:]
    seen: set[str] = set()
    results: list[WebDocReadResult] = []

    async with httpx.AsyncClient(
        timeout=timeout_seconds,
        follow_redirects=True,
        max_redirects=5,
        headers={"User-Agent": "AI-Test-Doc-Reader/1.0"},
    ) as client:
        while queue and len(results) < max_pages:
            url = queue.pop(0)
            if url in seen:
                continue
            seen.add(url)
            result = await _fetch_one_page(client, url)
            results.append(result)
            if not result.ok:
                continue
            for child_url in _same_site_doc_links(result.url, result.discovered_links or [], focus_text):
                if child_url not in seen and child_url not in queue:
                    queue.append(child_url)
                if len(queue) + len(results) >= max_pages:
                    break

    return results


def extract_web_doc_links(references: str) -> list[str]:
    max_links = _env_int("WEB_DOC_MAX_LINKS", DEFAULT_MAX_LINKS)
    links: list[str] = []
    seen: set[str] = set()
    for raw_url in URL_PATTERN.findall(references or ""):
        url = _clean_url(raw_url)
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        if parsed.scheme not in {"http", "https"} or not host:
            continue
        if any(domain in host for domain in SKIPPED_DOMAINS):
            continue
        if _is_private_or_local_host(host) and not _env_bool("WEB_DOC_ALLOW_PRIVATE", False):
            continue
        if _should_skip_path(parsed.path):
            continue
        normalized = _normalize_url(url)
        if normalized in seen:
            continue
        seen.add(normalized)
        links.append(normalized)
        if len(links) >= max_links:
            break
    return links


def build_web_doc_context(results: list[WebDocReadResult]) -> str:
    if not results:
        return ""

    max_chars = _env_int("WEB_DOC_MAX_CONTENT_CHARS", DEFAULT_MAX_CONTEXT_CHARS)
    lines = ["普通网页接口文档读取结果："]
    remaining = max_chars

    for result in results:
        if result.ok:
            title = result.title or result.url
            header = f"\n【网页文档：{title}】\n来源：{result.url}"
            content = _limit_text(result.content, max(0, remaining))
            if not content:
                lines.append(f"- {result.url}：内容已因上下文长度限制被截断。")
                continue
            lines.extend([header, content])
            remaining -= len(content)
        else:
            lines.append(f"- {result.url}：{result.message or '未读取正文'}")
        if remaining <= 0:
            lines.append("... 网页文档内容已达到上下文长度限制")
            break

    return "\n".join(lines).strip()


async def _fetch_one_page(client: httpx.AsyncClient, url: str) -> WebDocReadResult:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if _is_private_or_local_host(host) and not _env_bool("WEB_DOC_ALLOW_PRIVATE", False):
        return WebDocReadResult(url=url, status="blocked", message="默认不读取本机、内网或私有地址。")

    try:
        response = await client.get(url)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        return WebDocReadResult(url=url, status="error", message=f"{url} 请求失败：{exc}")

    final_url = str(response.url)
    content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
    if content_type and content_type not in ALLOWED_CONTENT_TYPES:
        return WebDocReadResult(
            url=final_url,
            status="unsupported",
            message=f"{final_url} 内容类型 {content_type} 暂不支持读取。",
        )

    max_bytes = _env_int("WEB_DOC_MAX_BYTES", DEFAULT_MAX_BYTES)
    data = response.content[:max_bytes]
    text = _decode_bytes(data, response.encoding)
    title = ""
    discovered_links: list[WebDocLink] = []

    if "html" in content_type or _looks_like_html(text):
        parser = _ReadableHTMLParser()
        parser.feed(text)
        parser.close()
        title = parser.title
        content = parser.text()
        discovered_links = parser.links
    elif "json" in content_type:
        title = "JSON 文档"
        content = _pretty_json(text)
    else:
        title = "文本网页文档"
        content = text

    if len(response.content) > max_bytes:
        content = f"{content}\n... 网页内容已按 {max_bytes} 字节上限截断"

    content = _clean_extracted_text(content)
    if not content:
        return WebDocReadResult(url=final_url, status="empty", message=f"{final_url} 未提取到可用正文。")

    return WebDocReadResult(
        url=final_url,
        title=title,
        content=content,
        status="success",
        message="已读取网页正文。",
        discovered_links=discovered_links,
    )


def _same_site_doc_links(base_url: str, links: list[WebDocLink], focus_text: str = "") -> list[str]:
    base = urlparse(base_url)
    base_host = (base.hostname or "").lower()
    if not base_host:
        return []
    if not _should_crawl_same_site(base.path):
        return []
    collection_prefix = _doc_collection_prefix(base.path)

    focus_terms = _focus_terms(focus_text)
    candidates: list[tuple[str, int, int]] = []
    seen: set[str] = set()
    for index, link in enumerate(links):
        absolute = _normalize_url(urljoin(base_url, link.url))
        parsed = urlparse(absolute)
        host = (parsed.hostname or "").lower()
        if parsed.scheme not in {"http", "https"} or host != base_host:
            continue
        if _should_skip_path(parsed.path):
            continue
        if _is_low_value_link(parsed.path):
            continue
        if collection_prefix and not unquote(parsed.path).lower().startswith(collection_prefix):
            continue
        if absolute == _normalize_url(base_url) or absolute in seen:
            continue
        seen.add(absolute)
        searchable = f"{link.text} {absolute}".lower()
        score = sum(1 for term in focus_terms if term in searchable)
        candidates.append((absolute, score, index))
    candidates.sort(key=lambda item: (-item[1], item[2]))
    return [url for url, _score, _index in candidates]


def _focus_terms(text: str) -> list[str]:
    raw = (text or "").lower()
    terms: set[str] = set()
    stop_words = {
        "接口",
        "测试",
        "用例",
        "功能",
        "覆盖",
        "全面",
        "网站",
        "页面",
        "设计",
        "生成",
        "自动化",
        "场景",
    }
    for word in re.findall(r"[a-z0-9_/-]{3,}", raw):
        terms.add(word)
    for phrase in re.findall(r"[\u4e00-\u9fff]{2,}", raw):
        if phrase not in stop_words:
            terms.add(phrase)
        for size in (2, 3, 4):
            if len(phrase) < size:
                continue
            for index in range(0, len(phrase) - size + 1):
                term = phrase[index : index + size]
                if term not in stop_words:
                    terms.add(term)
    return sorted(terms, key=len, reverse=True)[:24]


def _doc_collection_prefix(path: str) -> str:
    lower = unquote(path or "").lower()
    article_match = re.match(r"^/article/(\d+)(?:\.html|/)", lower)
    if article_match:
        return f"/article/{article_match.group(1)}/"
    return ""


def _should_crawl_same_site(path: str) -> bool:
    lower = unquote(path or "").lower()
    if re.match(r"^/article/\d+\.html$", lower):
        return True
    return lower.endswith("/") or lower in {"", "/"}


def _pretty_json(text: str) -> str:
    try:
        parsed: Any = json.loads(text)
        return json.dumps(parsed, ensure_ascii=False, indent=2)
    except json.JSONDecodeError:
        return text


def _decode_bytes(data: bytes, response_encoding: str | None = None) -> str:
    encodings = [response_encoding, "utf-8-sig", "utf-8", "gb18030", "gbk", "latin-1"]
    for encoding in [item for item in encodings if item]:
        try:
            return data.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            continue
    return data.decode("utf-8", errors="replace")


def _clean_extracted_text(text: str) -> str:
    lines: list[str] = []
    previous = ""
    for raw_line in text.splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip()
        if not line or line == previous:
            continue
        lines.append(line)
        previous = line
    return "\n".join(lines).strip()


def _limit_text(text: str, limit: int) -> str:
    if limit <= 0:
        return ""
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "\n... 网页文档正文已截断"


def _looks_like_html(text: str) -> bool:
    sample = text[:500].lower()
    return "<html" in sample or "<body" in sample or "<!doctype html" in sample


def _normalize_url(url: str) -> str:
    clean_url, _fragment = urldefrag(url.strip())
    return clean_url.rstrip("/")


def _clean_url(url: str) -> str:
    return url.rstrip(").,;，。；、]")


def _should_skip_path(path: str) -> bool:
    lower = unquote(path or "").lower()
    return lower.endswith(SKIP_PATH_EXTENSIONS)


def _is_low_value_link(path: str) -> bool:
    lower = unquote(path or "").lower()
    low_value_parts = ("login", "logout", "register", "download", "uploads", "static", "assets")
    return any(part in lower for part in low_value_parts)


def _is_private_or_local_host(host: str) -> bool:
    if host in {"localhost", "127.0.0.1", "::1"} or host.endswith(".local"):
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return address.is_private or address.is_loopback or address.is_link_local or address.is_multicast


def _env_bool(name: str, fallback: bool) -> bool:
    value = os.getenv(name, "").strip().lower()
    if not value:
        return fallback
    return value in {"1", "true", "yes", "on"}


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


class _ReadableHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.links: list[WebDocLink] = []
        self._title_parts: list[str] = []
        self._parts: list[str] = []
        self._line_parts: list[str] = []
        self._skip_depth = 0
        self._in_title = False
        self._row_depth = 0
        self._cell_depth = 0
        self._row_cells: list[str] = []
        self._cell_parts: list[str] = []
        self._link_stack: list[tuple[str, list[str]]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "noscript", "svg", "canvas"}:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if tag == "title":
            self._in_title = True
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self._link_stack.append((href.strip(), []))
        if tag == "br":
            self._flush_line()
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6", "p", "div", "section", "article", "li", "table", "ul", "ol"}:
            self._flush_line()
        if tag == "tr":
            self._flush_line()
            self._row_depth += 1
            self._row_cells = []
        if tag in {"td", "th"} and self._row_depth:
            self._cell_depth += 1
            self._cell_parts = []

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "noscript", "svg", "canvas"} and self._skip_depth:
            self._skip_depth -= 1
            return
        if self._skip_depth:
            return
        if tag == "title":
            self._in_title = False
            self.title = _clean_extracted_text(" ".join(self._title_parts))
        if tag == "a" and self._link_stack:
            href, parts = self._link_stack.pop()
            self.links.append(WebDocLink(url=href, text=_clean_extracted_text(" ".join(parts))))
        if tag in {"td", "th"} and self._cell_depth:
            cell = _clean_extracted_text(" ".join(self._cell_parts))
            if cell:
                self._row_cells.append(cell)
            self._cell_parts = []
            self._cell_depth -= 1
        if tag == "tr" and self._row_depth:
            if self._row_cells:
                self._parts.append(" | ".join(self._row_cells))
            self._row_depth -= 1
            self._row_cells = []
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6", "p", "div", "section", "article", "li", "table", "ul", "ol"}:
            self._flush_line()

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        text = re.sub(r"\s+", " ", data).strip()
        if not text:
            return
        if self._in_title:
            self._title_parts.append(text)
            return
        if self._link_stack:
            self._link_stack[-1][1].append(text)
        if self._cell_depth:
            self._cell_parts.append(text)
            return
        self._line_parts.append(text)

    def text(self) -> str:
        self._flush_line()
        return "\n".join(self._parts)

    def _flush_line(self) -> None:
        if not self._line_parts:
            return
        line = _clean_extracted_text(" ".join(self._line_parts))
        if line:
            self._parts.append(line)
        self._line_parts = []
