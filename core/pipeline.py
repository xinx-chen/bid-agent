"""要点提取流水线

集中解决四个 P0 问题：
1. 大文件分块提取 + 代码侧合并（防超 token）
2. JSON 容错解析（剥围栏/括号匹配/修复重试）
3. 时间字段标准化（YYYY-MM-DD HH:MM）
4. 关键条款正则兜底（★/●/必须/不得/应当/严禁/废标/无效）
"""

import json
import re

from core.llm import chat, LLMError
from prompts.extract import (
    build_extract_prompt,
    build_extract_chunk_prompt,
)


# ========== 阈值 ==========
# 全文低于该长度直接单次提取；超过则分块
SINGLE_CALL_MAX_CHARS = 24000
# 每个分块的最大字符数（DeepSeek 64k 上下文的保守值，约 1.2 万 token）
CHUNK_MAX_CHARS = 18000

# JSON Schema 字段分组
_SCALAR_FIELDS = [
    "project_name", "project_code", "buyer", "agency", "budget",
    "deadline", "bid_opening_time", "qa_deadline",
    "deposit", "contract_duration", "delivery_location",
]
_LIST_FIELDS = [
    "qualifications", "technical_specs", "scoring_criteria",
    "disqualification_clauses",
]
_TIME_FIELDS = ["deadline", "bid_opening_time", "qa_deadline"]

# 关键条款触发词
_CLAUSE_MARKERS_STRONG = ["★", "●"]
_CLAUSE_MARKERS_WEAK = ["否决投标", "投标无效", "废标", "拒收", "不予受理"]
_CLAUSE_MAX = 30
_CLAUSE_MAX_LEN = 200


# ========== P0-1：分块 ==========

def split_text(text: str, max_chars: int = CHUNK_MAX_CHARS) -> list:
    """按段落边界把长文本切成不超过 max_chars 的块（尽量不切断段落）"""
    paragraphs = re.split(r"\n{2,}", text)
    chunks = []
    buf = ""
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        # 单段就超长：按行硬切
        if len(para) > max_chars:
            if buf:
                chunks.append(buf)
                buf = ""
            lines = para.split("\n")
            line_buf = ""
            for line in lines:
                if len(line_buf) + len(line) + 1 > max_chars and line_buf:
                    chunks.append(line_buf)
                    line_buf = line
                else:
                    line_buf = f"{line_buf}\n{line}".strip()
            if line_buf:
                chunks.append(line_buf)
            continue
        if len(buf) + len(para) + 2 > max_chars and buf:
            chunks.append(buf)
            buf = para
        else:
            buf = f"{buf}\n\n{para}".strip() if buf else para
    if buf:
        chunks.append(buf)
    return chunks


# ========== P0-2：JSON 容错解析 ==========

def parse_json_loose(raw: str) -> dict:
    """
    宽松解析 LLM 返回的 JSON：
    - 剥离 ```json ... ``` 代码围栏
    - 截取第一个 { 到最后一个 }
    - json.loads，失败抛 ValueError
    """
    if not raw or not raw.strip():
        raise ValueError("模型返回为空")

    text = raw.strip()

    # 剥离代码围栏
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL | re.IGNORECASE)
    if fence:
        text = fence.group(1).strip()

    # 截取最外层花括号
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start:end + 1]

    # 清洗 LLM 常见的尾逗号（} 或 ] 前面的逗号）
    text = re.sub(r",\s*([}\]])", r"\1", text)

    return json.loads(text)


def _repair_json(raw: str) -> dict:
    """解析失败时，让模型把坏输出修复成合法 JSON（仅重试一次）"""
    repair_messages = [
        {
            "role": "system",
            "content": (
                "你是 JSON 修复器。下面是大模型输出的、不符合规范的 JSON 文本，"
                "请修复为合法 JSON：补全缺失的引号/括号、删除注释和多余文字、"
                "去除尾逗号。只输出修复后的 JSON 本身，不要代码围栏、不要解释。"
            ),
        },
        {"role": "user", "content": raw[:12000]},
    ]
    fixed = chat(repair_messages, temperature=0.0)
    return parse_json_loose(fixed)


def parse_points_json(raw: str) -> dict:
    """解析要点提取结果，失败自动修复一次"""
    try:
        return parse_json_loose(raw)
    except (ValueError, json.JSONDecodeError):
        return _repair_json(raw)


# ========== P0-5：时间标准化 ==========

_DATE_RE = re.compile(
    r"(\d{4})\s*[年/\-.]\s*(\d{1,2})\s*[月/\-.]\s*(\d{1,2})\s*日?"
)
_TIME_RE = re.compile(
    r"(上午|下午|早上|晚上)?\s*(\d{1,2})\s*(?:[:：点时])\s*(\d{1,2})?"
)


def normalize_datetime(value):
    """
    把 '2026年8月25日14:00（北京时间）' 这类文本统一为 '2026-08-25 14:00'。
    无法识别时原样返回；非字符串原样返回。
    """
    if not isinstance(value, str) or not value.strip():
        return value

    dm = _DATE_RE.search(value)
    if not dm:
        return value
    year, month, day = int(dm.group(1)), int(dm.group(2)), int(dm.group(3))
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return value

    hour, minute = 0, 0
    tail = value[dm.end():]
    tm = _TIME_RE.search(tail)
    if tm:
        ampm, hh, mm = tm.group(1), int(tm.group(2)), tm.group(3)
        minute = int(mm) if mm is not None else 0
        hour = hh
        if ampm in ("下午", "晚上") and hour < 12:
            hour += 12
        elif ampm in ("上午", "早上") and hour == 12:
            hour = 0

    return f"{year:04d}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}"


def normalize_points_times(points: dict) -> dict:
    """对三个时间字段做标准化"""
    for field in _TIME_FIELDS:
        if points.get(field):
            points[field] = normalize_datetime(points[field])
    return points


# ========== P0-6：关键条款正则兜底 ==========

def extract_keyword_clauses(file_text: str) -> list:
    """
    不依赖 LLM，直接从原文正则扫描强制性条款：
    - 含 ★ / ● 的行
    - 含 否决投标/投标无效/废标/拒收/不予受理 的句子
    """
    found = []
    seen = set()

    def _add(clause: str):
        clause = re.sub(r"\s+", " ", clause).strip(" 　\t|;:；：、，,。.")
        if not clause or len(clause) > _CLAUSE_MAX_LEN:
            return
        key = clause[:60]
        if key not in seen:
            seen.add(key)
            found.append(clause)

    # 按行扫描（招标文件通常每条占一行/一段）
    for line in file_text.splitlines():
        line = line.strip()
        if not line:
            continue
        if any(m in line for m in _CLAUSE_MARKERS_STRONG):
            _add(line)

    # 按句子扫描废标类表述
    for sentence in re.split(r"[。；;\n]", file_text):
        sentence = sentence.strip()
        if sentence and any(m in sentence for m in _CLAUSE_MARKERS_WEAK):
            _add(sentence)

    return found[:_CLAUSE_MAX]


def merge_keyword_clauses(points: dict, file_text: str) -> dict:
    """把正则扫到的条款并入 disqualification_clauses（去重）"""
    existing = points.get("disqualification_clauses") or []
    if not isinstance(existing, list):
        existing = [str(existing)]

    def _already_there(clause: str) -> bool:
        head = clause[:25]
        return any(head in str(e) or str(e)[:25] in clause for e in existing)

    for clause in extract_keyword_clauses(file_text):
        if not _already_there(clause):
            existing.append(clause)

    points["disqualification_clauses"] = existing
    return points


# ========== 分块结果合并 ==========

def _dedup_list(items: list) -> list:
    """对 list 字段去重（dict 按内容指纹，字符串按文本）"""
    result = []
    seen = set()
    for item in items:
        if isinstance(item, dict):
            key = json.dumps(item, ensure_ascii=False, sort_keys=True)
        else:
            key = str(item).strip()
        if key and key not in seen:
            seen.add(key)
            result.append(item)
    return result


def merge_points(partials: list) -> dict:
    """
    合并多个分块提取结果：
    - 标量字段：取第一个非空值（项目名称/编号/时间通常出现在首块）
    - 列表字段：并集去重
    """
    merged = {f: None for f in _SCALAR_FIELDS}
    merged.update({f: [] for f in _LIST_FIELDS})

    for part in partials:
        if not isinstance(part, dict):
            continue
        for f in _SCALAR_FIELDS:
            value = part.get(f)
            if merged[f] in (None, "", []) and value not in (None, "", []):
                merged[f] = value
        for f in _LIST_FIELDS:
            value = part.get(f)
            if isinstance(value, list):
                merged[f].extend(value)

    for f in _LIST_FIELDS:
        merged[f] = _dedup_list(merged[f])

    return merged


def _ensure_schema(points: dict) -> dict:
    """补齐缺失字段，防止下游 KeyError"""
    for f in _SCALAR_FIELDS:
        points.setdefault(f, None)
    for f in _LIST_FIELDS:
        value = points.get(f)
        if not isinstance(value, list):
            points[f] = []
    return points


# ========== 对外主入口 ==========

def finalize_points(raw: str, file_text: str) -> str:
    """
    单次（流式）提取后的统一收尾：
    解析 JSON → 补 schema → 时间标准化 → 关键条款兜底 → 返回美化 JSON 字符串
    """
    points = parse_points_json(raw)
    points = _ensure_schema(points)
    points = normalize_points_times(points)
    points = merge_keyword_clauses(points, file_text)
    return json.dumps(points, ensure_ascii=False, indent=2)


def extract_bid_points_chunked(file_text: str, progress_cb=None) -> str:
    """
    大文件分块提取（非流式，逐块调用后代码合并）。
    progress_cb(done, total, message) 可选，用于 UI 进度展示。
    返回美化后的 JSON 字符串。
    """
    chunks = split_text(file_text)
    total = len(chunks)
    partials = []

    for idx, chunk in enumerate(chunks, 1):
        if progress_cb:
            progress_cb(idx, total, f"正在提取第 {idx}/{total} 段…")
        messages = build_extract_chunk_prompt(chunk, idx, total)
        raw = chat(messages, temperature=0.1)
        try:
            partials.append(parse_points_json(raw))
        except LLMError:
            raise
        except Exception:
            # 单块彻底失败不致命：跳过该块，其余块照常合并
            continue

    if not partials:
        raise LLMError("所有分块提取均失败，请稍后重试或缩减文件范围")

    if progress_cb:
        progress_cb(total, total, "正在合并各段要点…")

    merged = merge_points(partials)
    merged = _ensure_schema(merged)
    merged = normalize_points_times(merged)
    merged = merge_keyword_clauses(merged, file_text)
    return json.dumps(merged, ensure_ascii=False, indent=2)


def needs_chunking(file_text: str) -> bool:
    """是否需要走分块流程"""
    return len(file_text) > SINGLE_CALL_MAX_CHARS
