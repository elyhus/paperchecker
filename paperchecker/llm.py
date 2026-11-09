# -*- coding: utf-8 -*-
"""语义检查：规则引擎判定不了的部分交给大模型（可选功能）。

设计要求：
1. 用户自填 API Key，程序不内置任何密钥；
2. 密钥存入系统密钥链（macOS Keychain / Windows 凭据管理器），不落明文、不进 SQLite；
3. 请求直连厂商，不经过自建中转；
4. 模型不可用时整段降级，不影响规则引擎的结论。
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass

from . import secretstore


@dataclass
class LLMConfig:
    base_url: str = "https://api.deepseek.com/v1"
    model: str = "deepseek-chat"
    api_key: str = ""
    timeout: int = 60


# ----------------------------- 密钥管理 -----------------------------

def load_key() -> str:
    """跨平台读取：Keychain / 凭据管理器 / Secret Service / 环境变量。"""
    return secretstore.load_key()


def save_key(key: str) -> bool:
    return secretstore.save_key(key)


def key_backend() -> str:
    return secretstore.backend()


# ----------------------------- 调用 -----------------------------

def chat(config: LLMConfig, system_prompt: str, user_prompt: str) -> str:
    payload = {
        "model": config.model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.1,
    }
    request = urllib.request.Request(
        config.base_url.rstrip("/") + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config.api_key}",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=config.timeout) as response:
        body = json.loads(response.read().decode("utf-8"))
    return body["choices"][0]["message"]["content"]


SEMANTIC_PROMPT = """你是论文格式检查助手。根据给定的摘要与关键词，只输出 JSON，不要解释：
{"keyword_not_in_abstract": ["不在摘要中出现的词"], "summary": "一句话结论"}"""


def semantic_check(abstract: str, keywords: list[str], config: LLMConfig) -> dict | None:
    """检查关键词是否都出现在摘要中；失败返回 None（调用方静默降级）。"""
    if not config.api_key:
        return None
    user = f"摘要：{abstract}\n关键词：{'，'.join(keywords)}"
    try:
        raw = chat(config, SEMANTIC_PROMPT, user)
        raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        return json.loads(raw)
    except (urllib.error.URLError, KeyError, ValueError, TimeoutError, OSError):
        return None


# ----------------------------- 文档语义检查 -----------------------------

SEMANTIC_DOC_PROMPT = """你是论文格式审阅助手。根据给出的【摘要】【关键词】【结论】三部分，只做三项判断：
1. 每个关键词是否都在摘要正文中出现；
2. 结论是否包含"不足/局限"方面的表述；
3. 结论是否包含"展望/下一步工作"方面的表述。
只输出 JSON，不要任何解释，格式：
{"keyword_missing": ["未出现在摘要中的关键词"], "conclusion_lacks": ["不足"、"展望"，缺哪项填哪项], "comment": "一句话总体判断"}"""


def semantic_issues(doc, config: "LLMConfig"):
    """对一篇已解析文档做语义检查，返回 (issues, raw)。

    无 Key、网络失败、模型输出不是 JSON —— 一律返回 ([], {"error": ...})，
    由调用方降级处理，绝不影响规则引擎的结论。
    """
    from .model import Issue, Severity

    abstract, _ = doc.section_text(("摘要", "摘　要"), ("关键词", "关键字", "Abstract"))
    conclusion, _ = doc.section_text(("结论", "结　论", "结束语"), ("致谢", "致　谢", "参考文献"))
    keywords: list[str] = []
    for block in doc.text_paragraphs:
        text = block.text.strip()
        if text.startswith(("关键词", "关 键 词")):
            raw = text.split("：", 1)[-1].split(":", 1)[-1]
            keywords = [p.strip() for p in raw.replace("，", ",").split(",") if p.strip()]
            break

    if not (abstract or conclusion):
        return [], {"skipped": "文档里没有找到摘要或结论，跳过语义检查"}
    if not config.api_key:
        return [], {"skipped": "未配置 API Key"}

    user = (f"【摘要】{abstract[:1500]}\n\n【关键词】{'，'.join(keywords) or '（未填写）'}\n\n"
            f"【结论】{conclusion[:1500]}")
    try:
        raw_text = chat(config, SEMANTIC_DOC_PROMPT, user).strip()
        raw_text = raw_text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        data = json.loads(raw_text)
    except Exception as exc:
        return [], {"error": f"{type(exc).__name__}: {exc}"}

    issues = []
    missing = data.get("keyword_missing") or []
    if missing:
        issues.append(Issue(
            rule_id="S001", rule_name="关键词应出现在摘要中", severity=Severity.WARN,
            message=f"关键词未在摘要中出现：{'、'.join(str(m) for m in missing)}",
            location="摘要 · 关键词", actual="、".join(map(str, missing)), expected="关键词均出现在摘要中"))
    lacks = data.get("conclusion_lacks") or []
    if lacks:
        issues.append(Issue(
            rule_id="S002", rule_name="结论应包含不足与展望", severity=Severity.WARN,
            message=f"结论缺少「{'、'.join(map(str, lacks))}」相关表述",
            location="结论", actual="缺少", expected="包含不足与展望"))
    if not issues and data.get("comment"):
        issues.append(Issue(
            rule_id="S003", rule_name="语义检查结论", severity=Severity.INFO,
            message=str(data["comment"])[:200], location="摘要 / 结论"))
    return issues, data
