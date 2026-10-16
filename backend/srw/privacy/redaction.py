from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RedactionSpan:
    kind: str
    start: int
    end: int


@dataclass(frozen=True, slots=True)
class RedactionResult:
    text: str
    counts: dict[str, int]
    spans: tuple[RedactionSpan, ...]
    length_preserved: bool


PATTERNS: tuple[tuple[str, re.Pattern[str], str], ...] = (
    ("email", re.compile(r"(?<![A-Za-z0-9._%+\-])[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}(?![A-Za-z0-9._%+\-])", re.I), "[邮箱已脱敏]"),
    ("identity", re.compile(r"(?<!\d)\d{17}[0-9Xx](?!\d)"), "[证件号已脱敏]"),
    ("phone", re.compile(r"(?<!\d)(?:(?:\+|00)\s*86[\s().-]*)?1[3-9](?:[\s().-]*\d){9}(?!\d)"), "[手机号已脱敏]"),
    ("wechat", re.compile(r"(?:微信(?:号)?|WeChat|WX|VX)\s*[:：]?\s*[A-Za-z][-_A-Za-z0-9]{5,19}", re.I), "[微信号已脱敏]"),
    ("address", re.compile(r"(?:现居住地|现住址|家庭住址|通讯地址|联系地址|住址|地址)\s*[:：]\s*[^\r\n。；;]{4,100}"), "[精确地址已脱敏]"),
    ("landline", re.compile(r"(?<!\d)(?:\+?86[-\s]?)?0\d{2,3}[-\s]?\d{7,8}(?!\d)"), "[座机已脱敏]"),
    ("passport", re.compile(r"(?:护照(?:号)?|passport)\s*[:：]?\s*[A-Z][A-Z0-9]{7,11}", re.I), "[护照号已脱敏]"),
    ("qq", re.compile(r"(?:QQ(?:号)?)\s*[:：]?\s*[1-9]\d{4,11}", re.I), "[QQ号已脱敏]"),
    ("bank_account", re.compile(r"(?:银行卡|银行账号|卡号)\s*[:：]?\s*\d(?:[ -]?\d){15,22}"), "[银行账号已脱敏]"),
    ("profile_url", re.compile(r"https?://(?:www\.)?(?:linkedin\.com/in|github\.com)/[^\s/]+", re.I), "[个人主页已脱敏]"),
    ("name", re.compile(r"(?:姓名|候选人)\s*[:：]\s*[\u4e00-\u9fff·]{2,20}"), "[姓名已脱敏]"),
)


def _mask(value: str, mask_char: str) -> str:
    # Keep layout/offsets stable so safe-provider quotes can be rebound to local source text.
    return "".join(ch if ch in "\r\n\t " else mask_char for ch in value)


def redact_personal_data(
    text: str,
    *,
    known_names: list[str] | tuple[str, ...] = (),
    preserve_length: bool = False,
    mask_char: str = "█",
) -> RedactionResult:
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    redacted = text
    counts: dict[str, int] = {}
    spans: list[RedactionSpan] = []

    for kind, pattern, label in PATTERNS:
        matches = list(pattern.finditer(redacted))
        if not matches:
            continue
        for match in reversed(matches):
            replacement = _mask(match.group(0), mask_char) if preserve_length else label
            redacted = redacted[:match.start()] + replacement + redacted[match.end():]
            counts[kind] = counts.get(kind, 0) + 1
            if preserve_length:
                spans.append(RedactionSpan(kind, match.start(), match.end()))

    for raw_name in known_names:
        candidate = str(raw_name or "").strip()
        if not (2 <= len(candidate) <= 80) or candidate.startswith("["):
            continue
        pattern = re.compile(re.escape(candidate))
        matches = list(pattern.finditer(redacted))
        for match in reversed(matches):
            replacement = _mask(match.group(0), mask_char) if preserve_length else "[姓名已脱敏]"
            redacted = redacted[:match.start()] + replacement + redacted[match.end():]
            counts["name"] = counts.get("name", 0) + 1
            if preserve_length:
                spans.append(RedactionSpan("name", match.start(), match.end()))

    spans.sort(key=lambda item: (item.start, item.end, item.kind))
    if preserve_length and len(redacted) != len(text):
        raise AssertionError("privacy scoring projection must preserve source offsets")
    return RedactionResult(redacted, counts, tuple(spans), preserve_length)
