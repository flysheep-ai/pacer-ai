from __future__ import annotations
import re
import json
from typing import Any
from pacer.llm.client import LLMClient, LLMMessage

RED_LINE_PATTERNS: dict[str, list[tuple[str, int]]] = {
    "self_harm": [
        (r"自杀|自残|割腕|跳楼|结束(自己|生命)|不想活|活不下去|死了算了|死了一了百了", 10),
        (r"kill\s*myself|end\s*my\s*life|suicide|self[\s-]harm", 10),
    ],
    "severe_depression": [
        (r"重度抑郁|确诊抑郁|抑郁发作|完全没动力|行尸走肉|连续.*失眠|每天都不想醒", 8),
    ],
    "crisis": [
        (r"活着的意义|为什么活着|撑不住了|坚持不下去|快崩溃了|崩溃边缘", 6),
    ],
    "abuse_disclosure": [
        (r"被打|家暴|虐待|体罚|被欺负|霸凌|性侵|猥亵", 10),
    ],
}

ESCALATION_RESPONSE = (
    "我听到了你的话，这些感受很重要。如果现在你正在经历非常困难的时刻，"
    "以下资源可能对你有帮助：\n"
    "- 全国心理援助热线：400-161-9995\n"
    "- 北京心理危机研究与干预中心：010-82951332\n"
    "- 生命热线：400-821-1215\n"
    "我也会把你今天说的话记录下来，如果你愿意，可以和信任的家人或老师聊聊。"
)

_CONFIRM_SYSTEM = """You are a mental health triage assistant. Given a student message,
confirm whether it represents an immediate crisis. Output STRICT JSON only:
{"is_crisis": true|false, "severity": "high"|"medium"|"low"|"none", "recommendation": "immediate_escalation"|"monitor"|"none"}
"""


def scan_keywords(text: str) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    for category, patterns in RED_LINE_PATTERNS.items():
        for pattern, weight in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                hits.append({"category": category, "pattern": pattern, "weight": weight})
    return hits


def should_escalate(hits: list[dict[str, Any]]) -> bool:
    if not hits:
        return False
    total_weight = sum(h["weight"] for h in hits)
    high_severity = any(h["category"] in ("self_harm", "abuse_disclosure") for h in hits)
    return total_weight >= 8 or high_severity


async def confirm_with_llm(llm: LLMClient, model: str, text: str) -> dict[str, Any]:
    resp = await llm.chat(
        [LLMMessage(role="user", content=text)],
        system=_CONFIRM_SYSTEM, model=model,
    )
    try:
        return json.loads(resp.text.strip())
    except (json.JSONDecodeError, ValueError, TypeError):
        return {"is_crisis": False, "severity": "none", "recommendation": "none"}
