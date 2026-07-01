# 这个模块负责调用多模态模型或本地演示生成器，并流式产出结构化测试用例事件。
from __future__ import annotations

import asyncio
import json
import os
import re
from dataclasses import dataclass
from typing import Any, AsyncIterator

import httpx
from dotenv import load_dotenv

from app.schemas import UploadedMaterial
from app.services.api_doc_parser import (
    build_api_doc_cases,
    describe_api_doc_facts,
    extract_api_doc_facts,
    facts_to_prompt_context,
    select_api_doc_facts,
)
from app.services.case_validator import (
    summarize_validation_issues,
    validate_cases_against_api_facts,
)

load_dotenv()


@dataclass
class GenerationEvent:
    kind: str
    payload: dict[str, Any]


@dataclass
class ApiDocEndpoint:
    title: str
    method: str
    path: str
    source_url: str
    description: str
    request_sample: dict[str, Any]
    params: list[str]
    content: str


async def generate_test_cases(
    requirements: str,
    context: str,
    references: str,
    materials: list[UploadedMaterial],
    material_context: str,
) -> AsyncIterator[GenerationEvent]:
    api_facts = select_api_doc_facts(
        extract_api_doc_facts(material_context),
        requirements,
        context,
    )
    if api_facts:
        yield GenerationEvent("thought", {"text": describe_api_doc_facts(api_facts)})
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        fact_context = facts_to_prompt_context(api_facts)

        if api_key and _api_doc_llm_enhance_enabled():
            try:
                events = await _collect_openai_events(
                    requirements,
                    context,
                    references,
                    materials,
                    material_context,
                    api_key,
                    api_fact_context=fact_context,
                )
                cases = _case_payloads(events)
                validation = validate_cases_against_api_facts(cases, api_facts)
                if validation.passed:
                    yield GenerationEvent(
                        "thought",
                        {
                            "text": (
                                f"大模型已基于接口事实扩展 {len(cases)} 条用例，"
                                f"{validation.matched_cases} 条可执行接口配置通过事实校验。"
                            )
                        },
                    )
                    async for event in _stream_collected_events(events):
                        yield event
                    return

                yield GenerationEvent(
                    "thought",
                    {
                        "text": (
                            "模型生成结果未通过接口事实校验："
                            f"{summarize_validation_issues(validation)}；正在按真实接口配置修复一次。"
                        )
                    },
                )
                repair_events = await _collect_openai_events(
                    requirements,
                    context,
                    references,
                    materials,
                    material_context,
                    api_key,
                    api_fact_context=fact_context,
                    repair_feedback=_repair_feedback_text(validation.issues),
                )
                repair_cases = _case_payloads(repair_events)
                repair_validation = validate_cases_against_api_facts(repair_cases, api_facts)
                if repair_validation.passed:
                    yield GenerationEvent(
                        "thought",
                        {
                            "text": (
                                f"修复后的模型结果已通过接口事实校验，"
                                f"将输出 {len(repair_cases)} 条增强用例。"
                            )
                        },
                    )
                    async for event in _stream_collected_events(repair_events):
                        yield event
                    return

                yield GenerationEvent(
                    "thought",
                    {
                        "text": (
                            "模型修复结果仍未满足真实接口配置要求："
                            f"{summarize_validation_issues(repair_validation)}；"
                            "已切换为平台确定性接口用例生成。"
                        )
                    },
                )
            except Exception as exc:
                yield GenerationEvent(
                    "thought",
                    {"text": f"模型增强接口用例暂不可用，已切换确定性接口生成：{type(exc).__name__}"},
                )

        doc_cases = build_api_doc_cases(requirements, context, material_context)
        if doc_cases:
            yield GenerationEvent(
                "thought",
                {
                    "text": (
                        f"已使用接口事实解析器生成 {len(doc_cases)} 条可执行接口用例；"
                        "每条用例均绑定真实请求方法、接口路径、参数样例和响应断言。"
                    )
                },
            )
            for index, case in enumerate(doc_cases, 1):
                await asyncio.sleep(0.04)
                case["id"] = f"TC-{index:03d}"
                yield GenerationEvent("case", case)
            return

    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if api_key:
        emitted_cases = 0
        try:
            async for event in _generate_with_openai(
                requirements,
                context,
                references,
                materials,
                material_context,
                api_key,
            ):
                if event.kind == "case":
                    emitted_cases += 1
                yield event
            if emitted_cases:
                return
            yield GenerationEvent(
                "thought",
                {"text": "模型响应未形成结构化用例，已切换本地生成器。"},
            )
        except Exception as exc:
            yield GenerationEvent(
                "thought",
                {"text": f"模型调用暂不可用，已切换本地生成器：{type(exc).__name__}"},
            )

    async for event in _generate_demo(requirements, context, references, materials, material_context):
        yield event


def _api_doc_llm_enhance_enabled() -> bool:
    value = os.getenv("API_DOC_LLM_ENHANCE", "true").strip().lower()
    return value not in {"0", "false", "no", "off"}


async def _collect_openai_events(
    requirements: str,
    context: str,
    references: str,
    materials: list[UploadedMaterial],
    material_context: str,
    api_key: str,
    *,
    api_fact_context: str = "",
    repair_feedback: str = "",
) -> list[GenerationEvent]:
    events: list[GenerationEvent] = []
    async for event in _generate_with_openai(
        requirements,
        context,
        references,
        materials,
        material_context,
        api_key,
        api_fact_context=api_fact_context,
        repair_feedback=repair_feedback,
    ):
        events.append(event)
    return events


def _case_payloads(events: list[GenerationEvent]) -> list[dict[str, Any]]:
    return [dict(event.payload) for event in events if event.kind == "case"]


async def _stream_collected_events(events: list[GenerationEvent]) -> AsyncIterator[GenerationEvent]:
    case_index = 0
    for event in events:
        await asyncio.sleep(0.02)
        if event.kind != "case":
            yield event
            continue
        case_index += 1
        payload = dict(event.payload)
        payload["id"] = f"TC-{case_index:03d}"
        yield GenerationEvent("case", payload)


def _repair_feedback_text(issues: list[str]) -> str:
    details = "\n".join(f"- {issue}" for issue in issues[:8])
    return f"""
上一次生成结果没有通过平台事实校验，请修复后重新输出完整 NDJSON：
{details}

修复重点：
1. 所有接口用例必须包含 api_test。
2. api_test.method 和 api_test.url 必须匹配接口文档事实。
3. 不允许使用平台自测接口。
4. 正向用例必须带上文档请求示例或关键业务参数。
5. 断言必须覆盖 HTTP 状态码和响应 JSON 字段。
""".strip()


async def _generate_with_openai(
    requirements: str,
    context: str,
    references: str,
    materials: list[UploadedMaterial],
    material_context: str,
    api_key: str,
    *,
    api_fact_context: str = "",
    repair_feedback: str = "",
) -> AsyncIterator[GenerationEvent]:
    base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    timeout_seconds = float(os.getenv("LLM_TIMEOUT_SECONDS", "120"))
    max_tokens = int(os.getenv("LLM_MAX_TOKENS", "5000"))

    content: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": _build_prompt(
                requirements,
                context,
                references,
                materials,
                material_context,
                api_fact_context=api_fact_context,
                repair_feedback=repair_feedback,
            ),
        }
    ]
    for image in [item for item in materials if item.is_image]:
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": image.as_data_url()},
            }
        )

    payload = {
        "model": model,
        "stream": True,
        "temperature": 0.2,
        "max_tokens": max_tokens,
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是资深测试架构师和质量工程专家。"
                    "你擅长从 PRD、思维导图、流程图、界面截图、Excel 表格、Word/PDF 文档、"
                    "文本需求、飞书文档正文、外部链接和背景信息中抽取业务规则、页面状态、"
                    "流程分支、异常路径、边界条件和质量风险，并输出适合沉淀为思维导图的结构化测试用例。"
                ),
            },
            {"role": "user", "content": content},
        ],
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    buffer = ""
    url = f"{base_url}/chat/completions"
    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
        async with client.stream("POST", url, headers=headers, json=payload) as response:
            response.raise_for_status()
            async for raw_line in response.aiter_lines():
                if not raw_line.startswith("data:"):
                    continue
                data = raw_line.removeprefix("data:").strip()
                if data == "[DONE]":
                    break
                packet = json.loads(data)
                delta = (
                    packet.get("choices", [{}])[0]
                    .get("delta", {})
                    .get("content", "")
                )
                if not delta:
                    continue
                buffer += delta
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    event = _parse_model_line(line)
                    if event:
                        yield event

    event = _parse_model_line(buffer)
    if event:
        yield event


def _build_prompt(
    requirements: str,
    context: str,
    references: str,
    materials: list[UploadedMaterial],
    material_context: str,
    *,
    api_fact_context: str = "",
    repair_feedback: str = "",
) -> str:
    material_summary = "\n".join(f"- {item.describe()}" for item in materials) or "- 未上传文件"
    image_count = sum(1 for item in materials if item.is_image)
    api_fact_section = f"\n\n{api_fact_context}" if api_fact_context.strip() else ""
    repair_section = f"\n\n校验修复反馈：\n{repair_feedback}" if repair_feedback.strip() else ""

    return f"""
请根据上传的多源材料、用户要求和上下文，生成专业、覆盖全面、可落地执行的测试用例。

材料清单：
{material_summary}

材料类型说明：
- 图片材料数量：{image_count}
- 表格、文档、文本、PDF 等可解析文件内容会出现在“抽取文本材料”中。
- 飞书文档、网页、知识库等链接会出现在“外部文档/链接”中；如果已配置飞书开放平台授权，读取到的飞书正文会出现在“抽取文本材料”的“飞书链接读取结果”里。
- 公开 HTML 接口文档、普通网页和 JSON 文档链接会尝试读取正文；读取到的内容会出现在“抽取文本材料”的“普通网页接口文档读取结果”里。
- 如果链接未配置授权、无权限、需要登录或类型暂不支持，只能根据链接、用户上下文和用户粘贴/导出的内容推断。

抽取文本材料：
{material_context or "无"}

用户要求：
{requirements or "无"}

上下文背景：
{context or "无"}

外部文档/链接状态：
{"已提供，详见抽取文本材料" if references.strip() else "无"}
{api_fact_section}
{repair_section}

输出要求：
1. 严格只输出 NDJSON，每一行都是一个独立 JSON 对象，不要输出 Markdown、代码块或解释性段落。
2. 先输出 2 到 4 行 event 为 thought 的对象，用于展示识别到的模块、流程和风险。
3. 再输出 12 到 30 行 event 为 case 的对象，覆盖主流程、分支流程、异常流程、边界值、权限、数据一致性、兼容性、易用性、安全性、性能风险，以及输入材料中暴露出的表格字段、文档规则和链接来源。
4. 每条 case 必须包含这些字段：
   event, id, module, title, priority, case_type, scenario, preconditions, steps, expected_results, test_data, tags, source, requirement_id
5. 如果材料中包含接口、OpenAPI、Swagger、URL、接口文档或可推断接口行为，请给对应 case 增加 api_test 对象，结构如下：
   api_test.method, api_test.url, api_test.headers, api_test.body, api_test.bodyMode, api_test.expectedStatus, api_test.expectedContains, api_test.assertions, api_test.extractors, api_test.databaseAssertions, api_test.jsonSchema, api_test.variables, api_test.timeoutSeconds
6. 如果材料中包含 Web 页面、表单、按钮、输入框、登录/搜索/提交/审批等页面操作场景，且可以推断稳定执行步骤，请给对应 case 增加 ui_test 对象，结构如下：
   ui_test.baseUrl, ui_test.browser, ui_test.viewport, ui_test.variables, ui_test.steps
   ui_test.steps 中只使用 goto、click、fill、type、press、select、check、uncheck、waitForSelector、wait、screenshot 动作，以及 visible、hidden、textVisible、urlContains、urlEquals、titleContains、textContains 断言。
7. UI locator 优先使用 role=button[name=提交]、getByLabel:用户名、getByPlaceholder:搜索、text=保存成功、testId=submit-button；无法确认稳定 locator 时，不要臆造脆弱 CSS，在 scenario 或 source 中写明需要补齐页面定位器或测试账号。
8. 如果是接口或 UI 自动化相关场景但暂时无法形成可执行配置，也要保留该 case，并写明缺少的信息，例如缺少接口地址、鉴权方式、页面地址、测试账号、稳定 locator 或前置数据。
9. api_test.url 和 ui_test.steps 中的 url/value 可以使用 {{base_url}}、{{web_base_url}}、{{token}}、{{username}}、{{password}} 等变量。
10. 对接口用例要覆盖正向、缺参、非法参数、边界、权限、重复提交、数据一致性和性能风险；对 UI 用例要覆盖页面跳转、表单校验、按钮状态、成功/失败提示和权限可见性。
11. preconditions、steps、expected_results、tags 必须是字符串数组。
12. expected_results 必须可验证，尽量写成状态码、字段值、页面状态、数据库结果或明确提示。
13. 避免重复标题；如果场景接近，也要通过触发条件、测试数据或断言点体现差异。
14. priority 只能使用 P0、P1、P2、P3。
15. id 使用 TC-001 这种格式。

示例行：
{{"event":"thought","text":"识别到核心流程包含创建、提交、审批和结果通知。"}}
{{"event":"case","id":"TC-001","module":"提交流程","title":"必填信息完整时提交成功","priority":"P0","case_type":"功能","scenario":"覆盖主流程提交","preconditions":["用户已登录","进入提交页面"],"steps":["填写所有必填项","点击提交"],"expected_results":["提交成功","生成记录编号"],"test_data":"有效表单数据","tags":["主流程","正向"],"source":"界面截图和用户要求"}}
""".strip()


def _parse_model_line(line: str) -> GenerationEvent | None:
    line = line.strip()
    if not line or line.startswith("```"):
        return None
    try:
        item = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(item, dict):
        return None

    event_name = item.get("event")
    if event_name == "thought":
        return GenerationEvent("thought", {"text": str(item.get("text", ""))})
    if event_name == "case":
        payload = dict(item.get("case") or item)
        payload.pop("event", None)
        return GenerationEvent("case", payload)
    if event_name in {"summary", "status"}:
        return GenerationEvent("thought", {"text": str(item.get("text", ""))})
    if "title" in item or "steps" in item:
        return GenerationEvent("case", item)
    return None


async def _generate_demo(
    requirements: str,
    context: str,
    references: str,
    materials: list[UploadedMaterial],
    material_context: str,
) -> AsyncIterator[GenerationEvent]:
    material_names = "、".join(item.filename for item in materials) or "未上传文件"
    requirement_hint = _compact(requirements, "未填写特定要求")
    context_hint = _compact(context, "未填写上下文")
    reference_hint = _compact(references, "未填写外部链接")
    parsed_count = sum(1 for item in materials if item.extracted_text)

    thoughts = [
        f"已读取材料：{material_names}。",
        f"可解析文件数量：{parsed_count}。",
        f"外部文档/链接：{reference_hint}。",
        f"需求关注点：{requirement_hint}。",
        f"业务背景：{context_hint}。",
        "将按主流程、异常分支、边界、权限、数据、性能与易用性生成覆盖集。",
    ]
    for thought in thoughts:
        await asyncio.sleep(0.12)
        yield GenerationEvent("thought", {"text": thought})

    doc_cases = build_api_doc_cases(requirements, context, material_context)
    if doc_cases:
        yield GenerationEvent(
            "thought",
            {
                "text": (
                    f"本地生成器已从接口文档正文识别到 {len({case['module'] for case in doc_cases})} 个接口模块，"
                    "将基于真实请求路径、方法、参数和返回示例生成可执行接口用例。"
                )
            },
        )
        for index, case in enumerate(doc_cases, 1):
            await asyncio.sleep(0.06)
            case["id"] = f"TC-{index:03d}"
            yield GenerationEvent("case", case)
        return

    cases = _demo_cases()
    for index, case in enumerate(cases, 1):
        await asyncio.sleep(0.06)
        case["id"] = f"TC-{index:03d}"
        case = _with_demo_api_test(case, index)
        yield GenerationEvent("case", case)


def _cases_from_api_docs(requirements: str, context: str, material_context: str) -> list[dict[str, Any]]:
    endpoints = _extract_api_doc_endpoints(material_context)
    if not endpoints:
        return []

    focus = f"{requirements}\n{context}".strip()
    ranked = sorted(endpoints, key=lambda item: _endpoint_score(item, focus), reverse=True)
    selected = ranked[:3]
    cases: list[dict[str, Any]] = []
    for endpoint in selected:
        cases.extend(_endpoint_cases(endpoint))
    return cases[:18]


def _extract_api_doc_endpoints(material_context: str) -> list[ApiDocEndpoint]:
    if "请求URL" not in material_context or "请求方式" not in material_context:
        return []

    lines = [_clean_doc_cell(line) for line in material_context.splitlines()]
    endpoints: list[ApiDocEndpoint] = []
    seen: set[tuple[str, str]] = set()
    for index, line in enumerate(lines):
        if line != "请求URL":
            continue
        path = _next_doc_value(lines, index)
        method_index = _find_next_line(lines, "请求方式", index + 1, index + 20)
        method = _next_doc_value(lines, method_index).upper() if method_index >= 0 else ""
        if not path or not method:
            continue
        if not re.match(r"^[A-Z]+$", method):
            continue
        key = (method, path)
        if key in seen:
            continue
        seen.add(key)

        start = max(0, index - 90)
        end = min(len(lines), index + 180)
        chunk = "\n".join(lines[start:end])
        title = _nearest_doc_title(lines, index) or path
        if " - " in title:
            title = title.split(" - ", 1)[0].strip()
        description_index = _find_previous_line(lines, "简要描述", index, index - 40)
        description = _next_doc_value(lines, description_index) if description_index >= 0 else title
        request_sample = _extract_request_sample(chunk)
        params = _extract_request_params(chunk, request_sample)
        endpoints.append(
            ApiDocEndpoint(
                title=title or description or path,
                method=method,
                path=path,
                source_url=_nearest_source_url(lines, index),
                description=description,
                request_sample=request_sample,
                params=params,
                content=chunk,
            )
        )
    return endpoints


def _endpoint_cases(endpoint: ApiDocEndpoint) -> list[dict[str, Any]]:
    module = endpoint.title or endpoint.path
    source = f"网页接口文档：{endpoint.source_url or endpoint.path}"
    business_params = [item for item in endpoint.params if item not in {"application", "application_client_type", "token", "ajax"}]
    primary_param = _pick_primary_param(business_params, endpoint.request_sample)
    sample_payload = endpoint.request_sample or _sample_payload_from_params(business_params)
    invalid_payload = dict(sample_payload)
    if primary_param:
        invalid_payload[primary_param] = "invalid"
    missing_payload = dict(sample_payload)
    if primary_param:
        missing_payload.pop(primary_param, None)

    cases = [
        _api_doc_case(
            endpoint,
            title=f"{module}接口正向请求成功",
            priority="P0",
            case_type="接口",
            scenario=f"使用文档示例参数调用 {endpoint.method} {endpoint.path}",
            preconditions=["ShopXO API 服务已启动", "已准备有效业务数据", "如接口需要登录则已准备有效 token"],
            steps=["设置 base_url、application、application_client_type 和 token 变量", "按文档示例参数发送请求", "校验响应状态码和业务 code"],
            expected_results=["HTTP 状态码为 200", "响应 JSON 中 code 为 0", "返回 msg 字段和业务 data 字段"],
            test_data=sample_payload,
            tags=["接口", "正向", "网页文档"],
            source=source,
            body=sample_payload,
            assertions=_positive_assertions(),
            expected_contains="code",
        ),
        _api_doc_case(
            endpoint,
            title=f"{module}接口缺少必填参数时返回失败",
            priority="P0",
            case_type="异常",
            scenario=f"覆盖 {primary_param or '必填参数'} 缺失后的参数校验",
            preconditions=["ShopXO API 服务已启动", "接口文档已声明请求参数"],
            steps=[f"移除请求参数 {primary_param or '必填字段'}", "发送接口请求", "校验失败响应"],
            expected_results=["HTTP 状态码为 200 或接口约定错误状态", "响应 JSON 中 code 不为 0", "错误提示能够说明参数缺失或请求失败"],
            test_data=missing_payload,
            tags=["接口", "缺参", "异常"],
            source=source,
            body=missing_payload,
            assertions=_negative_assertions(),
            expected_contains="code",
        ),
        _api_doc_case(
            endpoint,
            title=f"{module}接口参数类型非法时返回失败",
            priority="P1",
            case_type="异常",
            scenario=f"覆盖 {primary_param or '业务参数'} 类型非法或格式错误",
            preconditions=["ShopXO API 服务已启动"],
            steps=[f"将 {primary_param or '业务参数'} 设置为非法字符串", "发送接口请求", "校验接口未按成功处理"],
            expected_results=["HTTP 状态码为 200 或接口约定错误状态", "响应 JSON 中 code 不为 0", "不会产生成功业务数据"],
            test_data=invalid_payload,
            tags=["接口", "非法参数"],
            source=source,
            body=invalid_payload,
            assertions=_negative_assertions(),
            expected_contains="code",
        ),
        _api_doc_case(
            endpoint,
            title=f"{module}接口无效 token 场景校验",
            priority="P0",
            case_type="权限",
            scenario="覆盖登录态缺失、token 过期或 token 非法",
            preconditions=["ShopXO API 服务已启动", "接口存在用户态或订单态数据"],
            steps=["将 token 变量设置为空或无效值", "发送接口请求", "校验鉴权失败或业务拒绝"],
            expected_results=["接口不应按已登录用户成功处理", "响应 JSON 中 code 不为 0 或返回明确鉴权提示"],
            test_data=sample_payload,
            tags=["接口", "权限", "token"],
            source=source,
            body=sample_payload,
            variables={"token": "invalid-token"},
            assertions=_negative_assertions(),
            expected_contains="code",
        ),
        _api_doc_case(
            endpoint,
            title=f"{module}接口重复提交幂等性校验",
            priority="P1",
            case_type="幂等",
            scenario="覆盖短时间重复调用同一业务请求",
            preconditions=["ShopXO API 服务已启动", "准备一组可重复验证的业务数据"],
            steps=["使用相同参数连续发送两次请求", "分别记录两次响应", "核对业务状态是否重复变更"],
            expected_results=["接口不产生重复扣减、重复支付或重复业务记录", "第二次请求返回明确状态或保持幂等结果"],
            test_data=sample_payload,
            tags=["接口", "重复提交", "数据一致性"],
            source=source,
            body=sample_payload,
            assertions=[{"name": "响应业务码存在", "source": "json", "path": "$.code", "operator": "exists"}],
            expected_contains="code",
        ),
        _api_doc_case(
            endpoint,
            title=f"{module}接口响应契约字段校验",
            priority="P1",
            case_type="契约",
            scenario="覆盖文档返回示例中的基础字段结构",
            preconditions=["ShopXO API 服务已启动"],
            steps=["按文档示例参数发送请求", "检查响应 JSON 结构", "校验 code、msg、data 字段存在"],
            expected_results=["响应为 JSON 对象", "code、msg、data 字段存在", "字段类型与接口文档示例一致"],
            test_data=sample_payload,
            tags=["接口", "响应契约", "JSON"],
            source=source,
            body=sample_payload,
            assertions=[
                {"name": "code 字段存在", "source": "json", "path": "$.code", "operator": "exists"},
                {"name": "msg 字段存在", "source": "json", "path": "$.msg", "operator": "exists"},
                {"name": "data 字段存在", "source": "json", "path": "$.data", "operator": "exists"},
            ],
            expected_contains="code",
            json_schema={
                "type": "object",
                "required": ["code", "msg", "data"],
                "properties": {
                    "code": {"type": ["integer", "number", "string"]},
                    "msg": {"type": "string"},
                },
            },
        ),
    ]
    return cases


def _api_doc_case(
    endpoint: ApiDocEndpoint,
    *,
    title: str,
    priority: str,
    case_type: str,
    scenario: str,
    preconditions: list[str],
    steps: list[str],
    expected_results: list[str],
    test_data: dict[str, Any],
    tags: list[str],
    source: str,
    body: dict[str, Any],
    assertions: list[dict[str, Any]],
    expected_contains: str,
    variables: dict[str, str] | None = None,
    json_schema: dict[str, Any] | None = None,
) -> dict[str, Any]:
    api_test = _api_test_for_endpoint(endpoint, body, assertions, expected_contains, variables, json_schema)
    return {
        "module": endpoint.title or endpoint.path,
        "title": title,
        "priority": priority,
        "case_type": case_type,
        "scenario": scenario,
        "preconditions": preconditions,
        "steps": steps,
        "expected_results": expected_results,
        "test_data": json.dumps(test_data, ensure_ascii=False),
        "tags": tags,
        "source": source,
        "requirement_id": endpoint.path,
        "api_test": api_test,
    }


def _api_test_for_endpoint(
    endpoint: ApiDocEndpoint,
    body: dict[str, Any],
    assertions: list[dict[str, Any]],
    expected_contains: str,
    variables: dict[str, str] | None,
    json_schema: dict[str, Any] | None,
) -> dict[str, Any]:
    common_variables = {
        "base_url": "http://127.0.0.1:8080",
        "application": "app",
        "application_client_type": "weixin",
        "token": "",
        **(variables or {}),
    }
    query = "application={{application}}&application_client_type={{application_client_type}}&token={{token}}&ajax=ajax"
    return {
        "name": f"{endpoint.title or endpoint.path} - {endpoint.method} {endpoint.path}",
        "method": endpoint.method,
        "url": f"{{{{base_url}}}}/api.php?s={endpoint.path}&{query}",
        "headers": {"Accept": "application/json"},
        "body": json.dumps(body, ensure_ascii=False),
        "bodyMode": "form" if endpoint.method in {"POST", "PUT", "PATCH"} else "raw",
        "formFields": body if endpoint.method in {"POST", "PUT", "PATCH"} else {},
        "expectedStatus": 200,
        "expectedContains": expected_contains,
        "timeoutSeconds": 10,
        "maxResponseMs": 3000,
        "variables": common_variables,
        "assertions": assertions,
        "extractors": [],
        "databaseAssertions": [],
        "jsonSchema": json_schema,
    }


def _positive_assertions() -> list[dict[str, Any]]:
    return [
        {"name": "HTTP 状态码为 200", "source": "status", "operator": "equals", "expected": 200},
        {"name": "业务 code 为 0", "source": "json", "path": "$.code", "operator": "equals", "expected": 0},
        {"name": "msg 字段存在", "source": "json", "path": "$.msg", "operator": "exists"},
    ]


def _negative_assertions() -> list[dict[str, Any]]:
    return [
        {"name": "HTTP 状态码为 200", "source": "status", "operator": "equals", "expected": 200},
        {"name": "业务 code 不为 0", "source": "json", "path": "$.code", "operator": "not_equals", "expected": 0},
        {"name": "msg 字段存在", "source": "json", "path": "$.msg", "operator": "exists"},
    ]


def _extract_request_sample(chunk: str) -> dict[str, Any]:
    match = re.search(r"请求参数\s*(?:\||\n)\s*(\{.*?\})\s*(?:\||\n)\s*参数名", chunk, flags=re.S)
    if not match:
        return {}
    snippet = match.group(1)
    try:
        parsed = json.loads(snippet)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _extract_request_params(chunk: str, sample: dict[str, Any]) -> list[str]:
    params = list(sample.keys())
    if "请求参数" not in chunk:
        return params
    area = chunk.split("请求参数", 1)[1].split("返回示例", 1)[0]
    tokens: list[str] = []
    for line in area.splitlines():
        tokens.extend(_clean_doc_cell(item) for item in line.split("|"))
    for index, token in enumerate(tokens):
        if token == "参数名":
            cursor = index + 5
            while cursor < len(tokens):
                name = tokens[cursor]
                if not name or name in {"是否必须", "类型", "默认值", "描述"}:
                    cursor += 1
                    continue
                if re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", name) and name not in params:
                    params.append(name)
                cursor += 5
    return params


def _sample_payload_from_params(params: list[str]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for param in params:
        lower = param.lower()
        if lower.endswith("_id") or lower == "id" or lower == "ids":
            payload[param] = "1"
        elif "stock" in lower or "num" in lower or "count" in lower:
            payload[param] = "1"
        else:
            payload[param] = "test"
    return payload


def _pick_primary_param(params: list[str], sample: dict[str, Any]) -> str:
    for candidate in ("ids", "id", "order_id", "goods_id", "payment_id"):
        if candidate in sample or candidate in params:
            return candidate
    return params[0] if params else next(iter(sample), "")


def _endpoint_score(endpoint: ApiDocEndpoint, focus: str) -> int:
    text = f"{endpoint.title} {endpoint.description} {endpoint.path} {endpoint.content}".lower()
    terms = set(re.findall(r"[A-Za-z0-9_/-]{3,}", focus.lower()))
    for phrase in re.findall(r"[\u4e00-\u9fff]{2,}", focus.lower()):
        terms.add(phrase)
        for size in (2, 3, 4):
            for index in range(0, max(0, len(phrase) - size + 1)):
                terms.add(phrase[index : index + size])
    return sum(1 for term in terms if term and term in text)


def _clean_doc_cell(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _next_doc_value(lines: list[str], index: int) -> str:
    if index < 0:
        return ""
    for line in lines[index + 1 : index + 8]:
        value = _clean_doc_cell(line)
        if value:
            return value
    return ""


def _find_next_line(lines: list[str], target: str, start: int, end: int) -> int:
    end = min(len(lines), end)
    for index in range(max(0, start), end):
        if lines[index] == target:
            return index
    return -1


def _find_previous_line(lines: list[str], target: str, start: int, end: int) -> int:
    for index in range(min(start, len(lines) - 1), max(-1, end), -1):
        if lines[index] == target:
            return index
    return -1


def _nearest_doc_title(lines: list[str], index: int) -> str:
    for cursor in range(index, max(-1, index - 120), -1):
        line = lines[cursor]
        if line.startswith("【网页文档：") and line.endswith("】"):
            return line.removeprefix("【网页文档：").removesuffix("】").strip()
    return ""


def _nearest_source_url(lines: list[str], index: int) -> str:
    for cursor in range(index, max(-1, index - 120), -1):
        line = lines[cursor]
        if line.startswith("来源："):
            return line.removeprefix("来源：").strip()
    return ""


def _with_demo_api_test(case: dict[str, Any], index: int) -> dict[str, Any]:
    base_variables = {"base_url": "http://127.0.0.1:8000"}
    api_tests: dict[int, dict[str, Any]] = {
        1: {
            "name": "数据库状态接口检查",
            "method": "GET",
            "url": "{{base_url}}/api/database/status",
            "headers": {"Accept": "application/json"},
            "body": "",
            "bodyMode": "raw",
            "expectedStatus": 200,
            "expectedContains": "message",
            "timeoutSeconds": 10,
            "maxResponseMs": 1000,
            "variables": base_variables,
            "assertions": [
                {"name": "enabled 字段存在", "source": "json", "path": "$.enabled", "operator": "exists"},
                {"name": "message 字段存在", "source": "json", "path": "$.message", "operator": "exists"},
            ],
            "extractors": [{"name": "db_message", "source": "json", "path": "$.message"}],
            "databaseAssertions": [],
            "jsonSchema": {
                "type": "object",
                "required": ["enabled", "connected", "message"],
                "properties": {
                    "enabled": {"type": "boolean"},
                    "connected": {"type": "boolean"},
                    "message": {"type": "string"},
                },
            },
        },
        2: {
            "name": "生成历史接口检查",
            "method": "GET",
            "url": "{{base_url}}/api/history?limit=1",
            "headers": {"Accept": "application/json"},
            "body": "",
            "bodyMode": "raw",
            "expectedStatus": 200,
            "expectedContains": "items",
            "timeoutSeconds": 10,
            "maxResponseMs": 1500,
            "variables": base_variables,
            "assertions": [
                {"name": "items 字段存在", "source": "json", "path": "$.items", "operator": "exists"},
                {"name": "message 字段存在", "source": "json", "path": "$.message", "operator": "exists"},
            ],
            "extractors": [],
            "databaseAssertions": [],
            "jsonSchema": {
                "type": "object",
                "required": ["enabled", "connected", "message", "items"],
                "properties": {
                    "enabled": {"type": "boolean"},
                    "connected": {"type": "boolean"},
                    "message": {"type": "string"},
                    "items": {"type": "array"},
                },
            },
        },
        6: {
            "name": "执行器接口自检",
            "method": "POST",
            "url": "{{base_url}}/api/api-tests/run",
            "headers": {"Accept": "application/json", "Content-Type": "application/json"},
            "body": json.dumps(
                {
                    "name": "嵌套健康检查",
                    "method": "GET",
                    "url": "http://127.0.0.1:8000/",
                    "expectedStatus": 200,
                    "assertions": [{"name": "status 字段存在", "source": "json", "path": "$.status", "operator": "exists"}],
                },
                ensure_ascii=False,
            ),
            "bodyMode": "json",
            "expectedStatus": 200,
            "expectedContains": "passed",
            "timeoutSeconds": 10,
            "maxResponseMs": 3000,
            "variables": base_variables,
            "assertions": [
                {"name": "执行结果存在", "source": "json", "path": "$.passed", "operator": "exists"},
                {"name": "断言摘要存在", "source": "json", "path": "$.summary", "operator": "exists"},
            ],
            "extractors": [{"name": "nested_run_id", "source": "json", "path": "$.runId"}],
            "databaseAssertions": [],
            "jsonSchema": {"type": "object", "required": ["runId", "passed", "assertions"]},
        },
        9: {
            "name": "接口执行历史检查",
            "method": "GET",
            "url": "{{base_url}}/api/api-tests/history?limit=5",
            "headers": {"Accept": "application/json"},
            "body": "",
            "bodyMode": "raw",
            "expectedStatus": 200,
            "expectedContains": "items",
            "timeoutSeconds": 10,
            "maxResponseMs": 1500,
            "variables": base_variables,
            "assertions": [{"name": "items 字段存在", "source": "json", "path": "$.items", "operator": "exists"}],
            "extractors": [],
            "databaseAssertions": [],
            "jsonSchema": {"type": "object", "required": ["enabled", "connected", "message", "items"]},
        },
    }
    if index in api_tests:
        enriched = dict(case)
        enriched["api_test"] = api_tests[index]
        enriched["tags"] = [*enriched.get("tags", []), "接口", "自动化"]
        return enriched
    return case


def _demo_cases() -> list[dict[str, Any]]:
    return [
        {
            "module": "流程入口",
            "title": "有效用户进入核心流程并看到正确初始状态",
            "priority": "P0",
            "case_type": "功能",
            "scenario": "覆盖用户进入流程后的默认页面状态",
            "preconditions": ["用户账号有效", "用户具备访问入口权限"],
            "steps": ["登录系统", "进入目标功能入口", "观察页面默认状态和关键操作入口"],
            "expected_results": ["页面加载成功", "关键字段、按钮和导航状态与设计一致", "无异常提示或空白区域"],
            "test_data": "有效账号、默认业务数据",
            "tags": ["主流程", "界面"],
            "source": "上传图片与上下文材料",
        },
        {
            "module": "主流程",
            "title": "必填信息完整时提交业务成功",
            "priority": "P0",
            "case_type": "功能",
            "scenario": "覆盖核心业务成功路径",
            "preconditions": ["用户已进入目标页面", "存在可提交的数据条件"],
            "steps": ["填写所有必填字段", "选择合法选项", "点击提交或下一步", "查看结果反馈"],
            "expected_results": ["系统校验通过", "业务记录保存成功", "页面展示成功反馈或进入下一节点"],
            "test_data": "完整合法表单数据",
            "tags": ["主流程", "正向"],
            "source": "流程图主干路径",
        },
        {
            "module": "表单校验",
            "title": "必填字段为空时阻止提交并定位错误",
            "priority": "P0",
            "case_type": "异常",
            "scenario": "覆盖必填项缺失",
            "preconditions": ["用户已进入编辑或提交页面"],
            "steps": ["清空一个或多个必填字段", "点击提交", "逐项检查错误提示"],
            "expected_results": ["系统阻止提交", "缺失字段附近展示明确错误提示", "已填写数据不丢失"],
            "test_data": "空值、空格、仅换行",
            "tags": ["异常", "表单校验"],
            "source": "界面字段与用户要求",
        },
        {
            "module": "表单校验",
            "title": "字段长度达到边界值时校验结果正确",
            "priority": "P1",
            "case_type": "边界",
            "scenario": "覆盖最小长度、最大长度和超长输入",
            "preconditions": ["页面存在长度限制字段"],
            "steps": ["输入最小合法长度", "输入最大合法长度", "输入超过最大长度 1 个字符", "分别提交"],
            "expected_results": ["合法边界可提交", "超长输入被拦截或截断策略明确", "错误提示包含限制信息"],
            "test_data": "0、1、最大长度、最大长度+1 字符",
            "tags": ["边界值", "健壮性"],
            "source": "界面输入控件",
        },
        {
            "module": "流程分支",
            "title": "用户选择不同分支后进入对应后续节点",
            "priority": "P0",
            "case_type": "流程",
            "scenario": "覆盖流程图中的条件分支",
            "preconditions": ["用户已完成前置节点", "存在多种可选业务条件"],
            "steps": ["选择分支 A 并提交", "返回并选择分支 B 提交", "核对后续页面或状态"],
            "expected_results": ["分支 A 进入对应节点", "分支 B 进入对应节点", "流程状态和页面文案一致"],
            "test_data": "满足不同分支条件的数据",
            "tags": ["分支", "流程"],
            "source": "流程图分支路径",
        },
        {
            "module": "异常恢复",
            "title": "提交过程中接口失败时页面可恢复",
            "priority": "P1",
            "case_type": "异常",
            "scenario": "覆盖服务端异常、网络超时和重试",
            "preconditions": ["用户已填写有效数据", "可模拟接口 500 或超时"],
            "steps": ["触发提交", "模拟接口失败", "观察提示", "恢复接口后重新提交"],
            "expected_results": ["失败时展示可理解错误提示", "按钮状态恢复可点击", "重试成功后不产生重复脏数据"],
            "test_data": "有效表单数据、接口异常响应",
            "tags": ["异常恢复", "接口"],
            "source": "业务提交动作",
        },
        {
            "module": "权限控制",
            "title": "无权限用户无法访问或执行受限操作",
            "priority": "P0",
            "case_type": "安全",
            "scenario": "覆盖页面访问权限和按钮级权限",
            "preconditions": ["准备无权限账号", "准备有权限账号作为对照"],
            "steps": ["无权限账号访问目标 URL", "尝试点击受限操作", "切换有权限账号验证"],
            "expected_results": ["无权限用户被拦截或看不到入口", "后端接口同样拒绝非法操作", "有权限用户可正常完成"],
            "test_data": "不同角色账号",
            "tags": ["权限", "安全"],
            "source": "上下文权限要求",
        },
        {
            "module": "数据一致性",
            "title": "提交成功后列表、详情和导出数据保持一致",
            "priority": "P1",
            "case_type": "数据",
            "scenario": "覆盖多视图数据同步",
            "preconditions": ["用户已完成一条业务提交"],
            "steps": ["查看列表记录", "进入详情页", "触发导出或查询接口", "核对关键字段"],
            "expected_results": ["列表、详情和导出数据一致", "时间、状态、编号格式正确", "无缓存旧数据"],
            "test_data": "包含日期、金额、枚举状态的数据",
            "tags": ["数据一致性", "回归"],
            "source": "业务结果页面",
        },
        {
            "module": "重复提交",
            "title": "快速重复点击提交不会产生重复记录",
            "priority": "P0",
            "case_type": "稳定性",
            "scenario": "覆盖按钮防抖和幂等控制",
            "preconditions": ["用户已填写完整合法数据"],
            "steps": ["连续快速点击提交按钮多次", "观察按钮状态", "查询后台记录数量"],
            "expected_results": ["提交中按钮置灰或展示加载状态", "只生成一条有效记录", "重复请求被安全处理"],
            "test_data": "同一份合法业务数据",
            "tags": ["幂等", "并发"],
            "source": "关键提交动作",
        },
        {
            "module": "草稿与返回",
            "title": "中途返回或刷新后数据保存策略符合预期",
            "priority": "P2",
            "case_type": "易用性",
            "scenario": "覆盖用户中断操作",
            "preconditions": ["用户正在编辑未提交数据"],
            "steps": ["填写部分字段", "点击返回或刷新页面", "重新进入页面"],
            "expected_results": ["系统按产品策略提示保存或丢弃", "不会误提交半成品数据", "用户可明确选择下一步"],
            "test_data": "半填写表单",
            "tags": ["易用性", "状态保持"],
            "source": "页面交互路径",
        },
        {
            "module": "文件与图片",
            "title": "上传合法图片后预览、校验和提交正常",
            "priority": "P1",
            "case_type": "功能",
            "scenario": "覆盖图片或附件类输入",
            "preconditions": ["页面存在上传控件"],
            "steps": ["上传 PNG、JPG、WebP 文件", "查看预览", "提交业务"],
            "expected_results": ["合法文件上传成功", "预览清晰且文件名正确", "提交后附件与业务记录关联"],
            "test_data": "小图、大图、不同图片格式",
            "tags": ["上传", "附件"],
            "source": "用户上传材料类型",
        },
        {
            "module": "文件与图片",
            "title": "非法文件类型或超大文件被阻止",
            "priority": "P1",
            "case_type": "异常",
            "scenario": "覆盖上传限制",
            "preconditions": ["页面存在上传控件"],
            "steps": ["上传非图片文件", "上传超过大小限制的图片", "观察提示与控件状态"],
            "expected_results": ["非法文件被拒绝", "提示包含支持格式和大小限制", "页面未崩溃且可继续选择文件"],
            "test_data": "PDF、EXE、超大图片",
            "tags": ["上传", "异常"],
            "source": "上传入口",
        },
        {
            "module": "搜索与筛选",
            "title": "筛选条件组合后结果准确且可清空",
            "priority": "P2",
            "case_type": "功能",
            "scenario": "覆盖查询条件组合",
            "preconditions": ["存在多条不同状态、时间和关键字的数据"],
            "steps": ["输入关键字", "选择状态和时间范围", "执行查询", "清空条件再次查询"],
            "expected_results": ["组合查询结果准确", "空结果有清晰状态", "清空后恢复默认结果"],
            "test_data": "多状态、多时间段记录",
            "tags": ["查询", "筛选"],
            "source": "列表或流程节点",
        },
        {
            "module": "状态流转",
            "title": "业务状态按流程节点正确流转",
            "priority": "P0",
            "case_type": "流程",
            "scenario": "覆盖状态机正确性",
            "preconditions": ["存在可推进的业务记录"],
            "steps": ["完成当前节点操作", "进入下一节点", "重复推进直到终态", "尝试从终态回退或重复推进"],
            "expected_results": ["每一步状态变化符合流程图", "非法状态迁移被拒绝", "终态数据不可被错误修改"],
            "test_data": "覆盖全部状态的业务记录",
            "tags": ["状态机", "核心流程"],
            "source": "流程图节点",
        },
        {
            "module": "通知与消息",
            "title": "关键状态变化后通知对象和内容正确",
            "priority": "P2",
            "case_type": "集成",
            "scenario": "覆盖消息通知联动",
            "preconditions": ["系统配置通知渠道", "存在接收人账号"],
            "steps": ["触发关键状态变化", "查看站内信、邮件或消息记录", "核对通知内容"],
            "expected_results": ["通知发送给正确对象", "通知内容包含关键业务信息", "重复触发不会发送多余消息"],
            "test_data": "接收人、业务编号、状态变化",
            "tags": ["通知", "集成"],
            "source": "流程结果",
        },
        {
            "module": "兼容性",
            "title": "不同浏览器和常见分辨率下页面可用",
            "priority": "P2",
            "case_type": "兼容性",
            "scenario": "覆盖桌面端和移动端布局",
            "preconditions": ["准备 Chrome、Edge、Firefox 或移动视口"],
            "steps": ["分别打开目标页面", "执行主流程", "检查布局、滚动、弹层和按钮"],
            "expected_results": ["关键内容无遮挡", "文字不溢出", "主流程可完整执行"],
            "test_data": "1366x768、1920x1080、390x844",
            "tags": ["兼容性", "响应式"],
            "source": "界面截图",
        },
        {
            "module": "性能",
            "title": "高数据量或高并发场景下响应时间可接受",
            "priority": "P2",
            "case_type": "性能",
            "scenario": "覆盖列表加载、提交和查询性能",
            "preconditions": ["准备接近生产规模的数据量"],
            "steps": ["打开列表页面", "执行复杂查询", "连续提交多条记录", "记录响应时间"],
            "expected_results": ["页面首屏和查询响应满足性能基线", "提交无明显卡顿", "系统无超时或错误率异常"],
            "test_data": "大数据量列表、并发请求",
            "tags": ["性能", "容量"],
            "source": "上下文质量要求",
        },
        {
            "module": "安全输入",
            "title": "特殊字符和脚本输入被安全处理",
            "priority": "P1",
            "case_type": "安全",
            "scenario": "覆盖 XSS、SQL 特殊字符和富文本风险",
            "preconditions": ["页面存在文本输入字段"],
            "steps": ["输入脚本片段和 SQL 特殊字符", "提交并查看列表、详情、导出结果"],
            "expected_results": ["系统不执行恶意脚本", "特殊字符按策略转义或拒绝", "页面和导出文件无异常"],
            "test_data": "<script>alert(1)</script>、' OR 1=1 --",
            "tags": ["安全", "输入校验"],
            "source": "输入字段",
        },
        {
            "module": "可观测性",
            "title": "失败和关键操作可追踪审计",
            "priority": "P3",
            "case_type": "运维",
            "scenario": "覆盖日志、审计和问题定位",
            "preconditions": ["系统开启日志和审计记录"],
            "steps": ["执行成功操作", "执行失败操作", "查看审计记录和错误日志"],
            "expected_results": ["关键操作有审计记录", "失败日志包含请求标识和错误原因", "日志不泄露敏感信息"],
            "test_data": "成功请求、失败请求",
            "tags": ["审计", "可观测性"],
            "source": "专业测试覆盖要求",
        },
    ]


def _compact(text: str, fallback: str) -> str:
    text = " ".join((text or "").split())
    if not text:
        return fallback
    return text[:90] + ("..." if len(text) > 90 else "")
