# 这个模块负责通过 Playwright 执行受控的 Web UI 自动化步骤，并输出截图、trace 和断言结果。
from __future__ import annotations

import asyncio
import ipaddress
import os
import re
import socket
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse


BASE_DIR = Path(__file__).resolve().parent.parent.parent
UI_ARTIFACTS_DIR = BASE_DIR / "generated" / "ui-runs"

MAX_UI_STEPS = 30
MAX_TIMEOUT_SECONDS = 120.0
MAX_STEP_TIMEOUT_MS = 30_000
MAX_WAIT_TIMEOUT_MS = 10_000
MAX_ARTIFACT_RUNS = 200
VARIABLE_PATTERN = re.compile(r"\{\{\s*([a-zA-Z_][\w.-]*)\s*\}\}")
ROLE_PATTERN = re.compile(r"^(?:getByRole:|role=)([a-zA-Z0-9_-]+)(?:\[name=(.+)\])?$")

ALLOWED_BROWSERS = {"chromium", "firefox", "webkit"}
BLOCK_PRIVATE_NETWORK = os.getenv("UI_RUNNER_BLOCK_PRIVATE_NETWORK", "").strip().lower() in {"1", "true", "yes", "on"}
ALLOW_LOCALHOST = os.getenv("UI_RUNNER_ALLOW_LOCALHOST", "true").strip().lower() in {"1", "true", "yes", "on"}
ALLOWED_HOSTS = {
    item.strip().lower()
    for item in os.getenv("UI_RUNNER_ALLOWED_HOSTS", "").split(",")
    if item.strip()
}


async def run_ui_test(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise ValueError("Playwright 未安装。请先执行 pip install -r requirements.txt，并运行 python -m playwright install chromium。") from exc

    prepared = _prepare_payload(payload)
    run_id = _make_run_id("UI")
    run_dir = UI_ARTIFACTS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    _cleanup_old_artifacts()

    started_at = datetime.utcnow().isoformat() + "Z"
    started = time.perf_counter()
    step_results: list[dict[str, Any]] = []
    assertions: list[dict[str, Any]] = []
    console_messages: list[dict[str, str]] = []
    network_errors: list[dict[str, str]] = []
    artifacts: dict[str, str] = {}
    error = ""
    playwright_manager = None
    browser_instance = None
    context = None
    page = None
    tracing_started = False

    try:
        playwright_manager = async_playwright()
        playwright = await playwright_manager.start()
        launcher = getattr(playwright, prepared["browser"])
        try:
            browser_instance = await launcher.launch(headless=prepared["headless"])
        except Exception as exc:
            raise ValueError(
                "Playwright 浏览器启动失败。请确认已执行 python -m playwright install chromium，且当前环境允许启动浏览器。"
            ) from exc

        context = await browser_instance.new_context(
            viewport=prepared["viewport"],
            ignore_https_errors=prepared["ignoreHttpsErrors"],
        )
        if prepared["captureTrace"]:
            await context.tracing.start(screenshots=True, snapshots=True, sources=False)
            tracing_started = True

        page = await context.new_page()
        page.set_default_timeout(prepared["stepTimeoutMs"])
        page.on("console", lambda message: _append_console_message(console_messages, message))
        page.on("pageerror", lambda exception: _append_page_error(console_messages, exception))
        page.on("requestfailed", lambda request: _append_network_error(network_errors, request))

        for index, raw_step in enumerate(prepared["steps"], start=1):
            step = _render_value(raw_step, prepared["variables"])
            result = await _run_step(
                page=page,
                step=step,
                index=index,
                base_url=prepared["baseUrl"],
                variables=prepared["variables"],
                run_dir=run_dir,
                step_timeout_ms=prepared["stepTimeoutMs"],
            )
            step_results.append(result)
            if result.get("assertion"):
                assertions.append(_step_assertion(result))
            if not result.get("passed") and not prepared["continueOnFailure"]:
                break
    except ValueError:
        raise
    except Exception as exc:
        error = _compact_error(exc)
        step_results.append(
            {
                "index": len(step_results) + 1,
                "name": "执行异常",
                "action": "runtime",
                "passed": False,
                "durationMs": 0,
                "message": error,
            }
        )
    finally:
        failed = any(item.get("passed") is False for item in step_results) or bool(error)
        if page and failed and prepared["captureScreenshot"]:
            screenshot_path = run_dir / "failure.png"
            try:
                await page.screenshot(path=str(screenshot_path), full_page=True)
                artifacts["screenshot"] = f"/api/ui-tests/artifacts/{run_id}/failure.png"
            except Exception:
                pass
        if context and tracing_started:
            trace_path = run_dir / "trace.zip"
            try:
                await context.tracing.stop(path=str(trace_path))
                artifacts["trace"] = f"/api/ui-tests/artifacts/{run_id}/trace.zip"
            except Exception:
                pass
        if context:
            try:
                await context.close()
            except Exception:
                pass
        if browser_instance:
            try:
                await browser_instance.close()
            except Exception:
                pass
        if playwright_manager:
            try:
                await playwright_manager.stop()
            except Exception:
                pass
        await asyncio.sleep(0.05)

    duration_ms = int((time.perf_counter() - started) * 1000)
    passed = bool(step_results) and all(item.get("passed") for item in step_results)
    if not error and not passed:
        failed_step = next((item for item in step_results if item.get("passed") is False), {})
        error = str(failed_step.get("message") or "UI 自动化步骤失败。")

    return {
        "runId": run_id,
        "createdAt": started_at,
        "name": prepared["name"],
        "runType": "ui",
        "request": {
            "method": "UI",
            "url": prepared["baseUrl"] or _first_goto_url(prepared["steps"]) or "",
            "browser": prepared["browser"],
            "headless": prepared["headless"],
            "viewport": prepared["viewport"],
            "stepCount": len(prepared["steps"]),
        },
        "expected": {
            "status": "page assertions",
            "contains": "",
            "maxResponseMs": None,
        },
        "response": {
            "statusCode": None,
            "durationMs": duration_ms,
            "headers": {
                "browser": prepared["browser"],
                "steps": str(len(step_results)),
            },
            "bodyPreview": _build_body_preview(step_results, console_messages, network_errors, error),
        },
        "steps": step_results,
        "assertions": assertions,
        "consoleMessages": console_messages[-20:],
        "networkErrors": network_errors[-20:],
        "artifacts": artifacts,
        "summary": {
            "totalSteps": len(prepared["steps"]),
            "executedSteps": len(step_results),
            "passedSteps": sum(1 for item in step_results if item.get("passed")),
            "failedSteps": sum(1 for item in step_results if item.get("passed") is False),
            "assertionCount": len(assertions),
            "passedAssertions": sum(1 for item in assertions if item.get("passed")),
            "failedAssertions": sum(1 for item in assertions if item.get("passed") is False),
            "durationMs": duration_ms,
        },
        "failureAnalysis": _analyze_ui_failure(step_results, error, console_messages, network_errors) if not passed else None,
        "passed": passed,
        "error": "" if passed else error,
    }


def _prepare_payload(payload: dict[str, Any]) -> dict[str, Any]:
    variables = _as_dict(payload.get("variables"))
    base_url = str(_render_value(payload.get("baseUrl") or payload.get("base_url") or "", variables)).strip()
    if base_url:
        _validate_url(base_url)

    browser = str(payload.get("browser") or "chromium").strip().lower()
    if browser not in ALLOWED_BROWSERS:
        raise ValueError("browser 仅支持 chromium、firefox、webkit。")

    steps = payload.get("steps") or []
    if not isinstance(steps, list) or not steps:
        raise ValueError("UI 自动化至少需要 1 个步骤。")
    if len(steps) > MAX_UI_STEPS:
        raise ValueError(f"UI 自动化最多支持 {MAX_UI_STEPS} 个步骤。")
    if any(not isinstance(step, dict) for step in steps):
        raise ValueError("UI 自动化 steps 必须是对象数组。")

    timeout_seconds = _bounded_float(payload.get("timeoutSeconds") or payload.get("timeout_seconds"), 30.0, 1.0, MAX_TIMEOUT_SECONDS)
    step_timeout_ms = int(_bounded_float(payload.get("stepTimeoutMs") or payload.get("step_timeout_ms"), 8_000, 500, MAX_STEP_TIMEOUT_MS))
    viewport = _prepare_viewport(payload.get("viewport"))
    return {
        "name": str(payload.get("name") or "Web UI 自动化用例").strip()[:255],
        "baseUrl": base_url,
        "browser": browser,
        "headless": _as_bool(payload.get("headless"), True),
        "ignoreHttpsErrors": _as_bool(_first_present(payload, "ignoreHttpsErrors", "ignore_https_errors"), False),
        "captureTrace": _as_bool(_first_present(payload, "captureTrace", "capture_trace"), True),
        "captureScreenshot": _as_bool(_first_present(payload, "captureScreenshot", "capture_screenshot"), True),
        "continueOnFailure": _as_bool(_first_present(payload, "continueOnFailure", "continue_on_failure"), False),
        "timeoutSeconds": timeout_seconds,
        "stepTimeoutMs": step_timeout_ms,
        "viewport": viewport,
        "variables": variables,
        "steps": steps,
    }


async def _run_step(
    *,
    page: Any,
    step: dict[str, Any],
    index: int,
    base_url: str,
    variables: dict[str, Any],
    run_dir: Path,
    step_timeout_ms: int,
) -> dict[str, Any]:
    started = time.perf_counter()
    action = str(step.get("action") or "").strip()
    assertion = str(step.get("assertion") or "").strip()
    name = str(step.get("name") or _step_name(index, action, assertion)).strip()
    result = {
        "index": index,
        "name": name,
        "action": action or "",
        "assertion": assertion or "",
        "locator": str(step.get("locator") or ""),
        "passed": False,
        "durationMs": 0,
        "message": "",
    }

    try:
        if assertion:
            message = await _execute_assertion(page, assertion, step, step_timeout_ms)
            result["passed"] = True
            result["message"] = message
        else:
            message = await _execute_action(page, action, step, base_url, variables, run_dir, step_timeout_ms)
            result["passed"] = True
            result["message"] = message
    except Exception as exc:
        result["message"] = _compact_error(exc)
    finally:
        result["durationMs"] = int((time.perf_counter() - started) * 1000)
        result["url"] = getattr(page, "url", "")
    return result


async def _execute_action(
    page: Any,
    action: str,
    step: dict[str, Any],
    base_url: str,
    variables: dict[str, Any],
    run_dir: Path,
    step_timeout_ms: int,
) -> str:
    action_key = action.strip()
    if action_key == "goto":
        target_url = _resolve_step_url(step.get("url") or step.get("target") or "", base_url)
        wait_until = str(step.get("waitUntil") or step.get("wait_until") or "domcontentloaded")
        response = await page.goto(target_url, wait_until=wait_until, timeout=step_timeout_ms)
        status = response.status if response else None
        if status is not None and status >= 400 and not _as_bool(step.get("allowHttpErrors"), False):
            raise ValueError(f"页面返回 HTTP {status}。")
        return f"已打开 {target_url}" + (f"，HTTP {status}" if status else "")

    locator_text = str(step.get("locator") or step.get("selector") or "").strip()
    if action_key in {"click", "fill", "type", "press", "select", "check", "uncheck", "waitForSelector", "screenshot"} and not locator_text and action_key != "screenshot":
        raise ValueError(f"{action_key} 步骤需要 locator。")

    if action_key == "click":
        await _locator(page, locator_text).click(timeout=step_timeout_ms)
        return f"已点击 {locator_text}"
    if action_key == "fill":
        await _locator(page, locator_text).fill(str(step.get("value") or ""), timeout=step_timeout_ms)
        return f"已填写 {locator_text}"
    if action_key == "type":
        await _locator(page, locator_text).type(str(step.get("value") or ""), timeout=step_timeout_ms)
        return f"已输入 {locator_text}"
    if action_key == "press":
        await _locator(page, locator_text).press(str(step.get("key") or "Enter"), timeout=step_timeout_ms)
        return f"已按键 {step.get('key') or 'Enter'}"
    if action_key == "select":
        value = step.get("value")
        await _locator(page, locator_text).select_option(value, timeout=step_timeout_ms)
        return f"已选择 {locator_text}"
    if action_key == "check":
        await _locator(page, locator_text).check(timeout=step_timeout_ms)
        return f"已勾选 {locator_text}"
    if action_key == "uncheck":
        await _locator(page, locator_text).uncheck(timeout=step_timeout_ms)
        return f"已取消勾选 {locator_text}"
    if action_key == "waitForSelector":
        state = str(step.get("state") or "visible")
        await _locator(page, locator_text).wait_for(state=state, timeout=step_timeout_ms)
        return f"已等待 {locator_text} 进入 {state} 状态"
    if action_key in {"wait", "waitForTimeout"}:
        timeout_ms = int(_bounded_float(step.get("ms") or step.get("timeoutMs"), 1000, 100, MAX_WAIT_TIMEOUT_MS))
        await page.wait_for_timeout(timeout_ms)
        return f"已等待 {timeout_ms} ms"
    if action_key == "screenshot":
        filename = f"step-{int(step.get('index') or 0):02d}-{uuid.uuid4().hex[:6]}.png"
        await page.screenshot(path=str(run_dir / filename), full_page=_as_bool(step.get("fullPage") or step.get("full_page"), True))
        return f"已截图 {filename}"

    raise ValueError(f"不支持的 UI 动作：{action or '-'}。")


async def _execute_assertion(page: Any, assertion: str, step: dict[str, Any], step_timeout_ms: int) -> str:
    key = assertion.strip()
    expected = str(step.get("expected") or "")
    locator_text = str(step.get("locator") or step.get("selector") or "").strip()

    if key in {"visible", "textVisible"}:
        if not locator_text:
            raise ValueError(f"{key} 断言需要 locator。")
        await _locator(page, locator_text).wait_for(state="visible", timeout=step_timeout_ms)
        return f"{locator_text} 可见"
    if key == "hidden":
        if not locator_text:
            raise ValueError("hidden 断言需要 locator。")
        await _locator(page, locator_text).wait_for(state="hidden", timeout=step_timeout_ms)
        return f"{locator_text} 已隐藏"
    if key == "urlContains":
        if expected not in page.url:
            raise ValueError(f"当前 URL 为 {page.url}，未包含 {expected}。")
        return f"URL 包含 {expected}"
    if key == "urlEquals":
        if page.url != expected:
            raise ValueError(f"当前 URL 为 {page.url}，不等于 {expected}。")
        return f"URL 等于 {expected}"
    if key == "titleContains":
        title = await page.title()
        if expected not in title:
            raise ValueError(f"当前标题为 {title}，未包含 {expected}。")
        return f"标题包含 {expected}"
    if key == "textContains":
        if not locator_text:
            raise ValueError("textContains 断言需要 locator。")
        text = await _locator(page, locator_text).text_content(timeout=step_timeout_ms)
        if expected not in str(text or ""):
            raise ValueError(f"{locator_text} 文本未包含 {expected}。")
        return f"{locator_text} 文本包含 {expected}"

    raise ValueError(f"不支持的 UI 断言：{assertion or '-'}。")


def _locator(page: Any, locator_text: str) -> Any:
    text = locator_text.strip()
    if not text:
        raise ValueError("locator 不能为空。")

    role_match = ROLE_PATTERN.match(text)
    if role_match:
        role = role_match.group(1)
        name = _strip_quotes(role_match.group(2) or "")
        return page.get_by_role(role, name=name) if name else page.get_by_role(role)

    prefixes = {
        "getByLabel:": page.get_by_label,
        "label=": page.get_by_label,
        "getByPlaceholder:": page.get_by_placeholder,
        "placeholder=": page.get_by_placeholder,
        "getByText:": page.get_by_text,
        "text=": page.get_by_text,
        "testId=": page.get_by_test_id,
        "data-testid=": page.get_by_test_id,
    }
    for prefix, factory in prefixes.items():
        if text.startswith(prefix):
            return factory(text[len(prefix) :].strip())

    if text.startswith("css="):
        return page.locator(text[4:].strip())
    if text.startswith("xpath="):
        return page.locator(text)
    if text.startswith("//") or text.startswith("(//"):
        return page.locator(f"xpath={text}")
    return page.locator(text)


def _resolve_step_url(value: Any, base_url: str) -> str:
    url = str(value or "").strip()
    if not url:
        raise ValueError("goto 步骤需要 url。")
    if urlparse(url).scheme:
        final_url = url
    else:
        if not base_url:
            raise ValueError("相对路径需要先配置 baseUrl。")
        final_url = urljoin(base_url.rstrip("/") + "/", url.lstrip("/"))
    _validate_url(final_url)
    return final_url


def _validate_url(value: str) -> None:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("UI 自动化只允许访问 http 或 https 页面。")
    hostname = parsed.hostname.lower()
    if ALLOWED_HOSTS and hostname not in ALLOWED_HOSTS:
        raise ValueError(f"当前环境只允许访问 UI_RUNNER_ALLOWED_HOSTS 中配置的域名，已拒绝 {hostname}。")
    if _is_localhost(hostname) and ALLOW_LOCALHOST:
        return
    if BLOCK_PRIVATE_NETWORK and _host_resolves_private(hostname):
        raise ValueError("当前环境已启用 UI_RUNNER_BLOCK_PRIVATE_NETWORK，禁止访问内网地址。")


def _host_resolves_private(hostname: str) -> bool:
    try:
        ipaddress.ip_address(hostname)
        addresses = [hostname]
    except ValueError:
        try:
            addresses = [item[4][0] for item in socket.getaddrinfo(hostname, None)]
        except socket.gaierror:
            return False
    for address in addresses:
        try:
            ip = ipaddress.ip_address(address)
            if ip.is_private or ip.is_loopback or ip.is_link_local:
                return True
        except ValueError:
            continue
    return False


def _is_localhost(hostname: str) -> bool:
    return hostname in {"localhost", "127.0.0.1", "::1"} or hostname.endswith(".localhost")


def _prepare_viewport(value: Any) -> dict[str, int]:
    data = _as_dict(value)
    width = int(_bounded_float(data.get("width"), 1280, 320, 3840))
    height = int(_bounded_float(data.get("height"), 720, 320, 2160))
    return {"width": width, "height": height}


def _step_assertion(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": result.get("name") or f"Step {result.get('index')}",
        "passed": bool(result.get("passed")),
        "message": result.get("message") or "",
        "category": "ui",
        "actual": result.get("url") or "",
    }


def _analyze_ui_failure(
    steps: list[dict[str, Any]],
    error: str,
    console_messages: list[dict[str, str]],
    network_errors: list[dict[str, str]],
) -> dict[str, Any]:
    failed = next((item for item in steps if item.get("passed") is False), {})
    message = str(failed.get("message") or error or "")
    lower = message.lower()
    if "timeout" in lower or "超时" in message:
        category = "ui_timeout"
        summary = "页面元素或页面加载超时。"
    elif "locator" in lower or "strict mode" in lower or "not found" in lower:
        category = "ui_locator"
        summary = "页面定位器未命中或匹配不稳定。"
    elif str(failed.get("assertion") or ""):
        category = "ui_assertion"
        summary = "页面断言未通过。"
    elif str(failed.get("action") or "") == "goto":
        category = "ui_navigation"
        summary = "页面打开失败或返回异常状态。"
    elif network_errors:
        category = "ui_network"
        summary = "页面执行期间存在网络请求失败。"
    else:
        category = "ui_runtime"
        summary = "UI 自动化执行失败。"

    evidence = []
    if failed:
        evidence.append(f"失败步骤：{failed.get('index')}. {failed.get('name')}")
    if message:
        evidence.append(f"错误信息：{message[:240]}")
    if failed.get("url"):
        evidence.append(f"当前页面：{failed.get('url')}")
    if console_messages:
        evidence.append(f"控制台最近消息：{console_messages[-1].get('text', '')[:160]}")
    if network_errors:
        evidence.append(f"网络失败：{network_errors[-1].get('url', '')[:160]}")

    return {
        "category": category,
        "summary": summary,
        "confidence": 0.78,
        "shouldCreateDefect": category in {"ui_assertion", "ui_navigation", "ui_network", "ui_runtime"},
        "shouldUpdateCase": category in {"ui_locator", "ui_timeout"},
        "evidence": evidence,
        "nextSteps": _ui_next_steps(category),
    }


def _ui_next_steps(category: str) -> list[str]:
    mapping = {
        "ui_timeout": ["确认测试环境响应是否正常。", "检查等待条件是否过短，必要时补充稳定的可见性断言。"],
        "ui_locator": ["优先改用 role、label、placeholder 或 data-testid 定位。", "避免使用易变的层级 CSS 选择器。"],
        "ui_assertion": ["核对页面实际文案、跳转地址和业务状态。", "确认测试数据是否满足断言前置条件。"],
        "ui_navigation": ["确认 baseUrl 与页面路径是否正确。", "检查登录态、网关和环境可访问性。"],
        "ui_network": ["查看 trace 中失败请求，判断是前端资源、接口还是网关问题。"],
    }
    return mapping.get(category, ["查看失败截图和 trace，定位失败步骤对应的页面状态。"])


def _build_body_preview(
    steps: list[dict[str, Any]],
    console_messages: list[dict[str, str]],
    network_errors: list[dict[str, str]],
    error: str,
) -> str:
    failed = next((item for item in steps if item.get("passed") is False), None)
    parts = [
        f"执行步骤：{sum(1 for item in steps if item.get('passed'))}/{len(steps)}",
    ]
    if failed:
        parts.append(f"失败步骤：{failed.get('index')}. {failed.get('name')}")
        parts.append(str(failed.get("message") or ""))
    if error and not failed:
        parts.append(error)
    if network_errors:
        parts.append(f"网络失败：{len(network_errors)}")
    if console_messages:
        parts.append(f"控制台消息：{len(console_messages)}")
    return "\n".join(part for part in parts if part)[:4000]


def _append_console_message(items: list[dict[str, str]], message: Any) -> None:
    items.append({"type": str(getattr(message, "type", "")), "text": str(getattr(message, "text", ""))[:500]})
    del items[:-50]


def _append_page_error(items: list[dict[str, str]], exception: Any) -> None:
    items.append({"type": "pageerror", "text": str(exception)[:500]})
    del items[:-50]


def _append_network_error(items: list[dict[str, str]], request: Any) -> None:
    failure = getattr(request, "failure", None)
    items.append(
        {
            "url": str(getattr(request, "url", ""))[:500],
            "method": str(getattr(request, "method", "")),
            "error": str(failure or "")[:500],
        }
    )
    del items[:-50]


def _render_value(value: Any, variables: dict[str, Any]) -> Any:
    if isinstance(value, str):
        return VARIABLE_PATTERN.sub(lambda match: str(variables.get(match.group(1), match.group(0))), value)
    if isinstance(value, list):
        return [_render_value(item, variables) for item in value]
    if isinstance(value, dict):
        return {key: _render_value(item, variables) for key, item in value.items()}
    return value


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_bool(value: Any, default: bool) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _first_present(payload: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in payload:
            return payload.get(key)
    return None


def _bounded_float(value: Any, default: float, minimum: float, maximum: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    return max(minimum, min(maximum, number))


def _strip_quotes(value: str) -> str:
    text = value.strip()
    if len(text) >= 2 and text[0] in {'"', "'"} and text[-1] == text[0]:
        return text[1:-1]
    return text


def _step_name(index: int, action: str, assertion: str) -> str:
    if assertion:
        return f"断言 {index}: {assertion}"
    if action:
        return f"步骤 {index}: {action}"
    return f"步骤 {index}"


def _first_goto_url(steps: list[dict[str, Any]]) -> str:
    for step in steps:
        if isinstance(step, dict) and step.get("action") == "goto":
            return str(step.get("url") or "")
    return ""


def _compact_error(exc: Exception) -> str:
    text = str(exc).strip() or type(exc).__name__
    return text.replace("\r", " ").strip()[:1000]


def _make_run_id(prefix: str) -> str:
    return f"{prefix}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"


def _cleanup_old_artifacts() -> None:
    try:
        runs = sorted(
            [path for path in UI_ARTIFACTS_DIR.iterdir() if path.is_dir()],
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
    except OSError:
        return
    for path in runs[MAX_ARTIFACT_RUNS:]:
        try:
            for child in path.iterdir():
                child.unlink(missing_ok=True)
            path.rmdir()
        except OSError:
            continue
