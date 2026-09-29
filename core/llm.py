"""LLM 调用模块 - 对接 DeepSeek API

特性：
- 120s 超时
- 限流/超时/网络错误自动指数退避重试（最多 3 次）
- 鉴权/参数错误不重试，包装成 LLMError 供 UI 层友好提示
"""

import os
import time

from openai import (
    OpenAI,
    APITimeoutError,
    APIConnectionError,
    RateLimitError,
    AuthenticationError,
    PermissionDeniedError,
    BadRequestError,
    InternalServerError,
)


DEFAULT_MODEL = "deepseek-chat"
REQUEST_TIMEOUT = 120  # 秒
MAX_RETRIES = 3
RETRY_BASE_WAIT = 2  # 指数退避基数：2s, 4s, 8s


class LLMError(Exception):
    """对外统一异常，UI 层捕获后展示友好文案，不让进程崩溃"""


# 可重试的瞬时错误
_RETRYABLE_ERRORS = (
    APITimeoutError,
    APIConnectionError,
    RateLimitError,
    InternalServerError,
)


def get_client() -> OpenAI:
    """获取 DeepSeek API 客户端"""
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise LLMError("未配置 DeepSeek API Key，请在左侧侧边栏填写后再试")
    return OpenAI(
        api_key=api_key,
        base_url="https://api.deepseek.com",
        timeout=REQUEST_TIMEOUT,
    )


def _friendly_message(exc: Exception) -> str:
    """把 openai 异常翻译成用户能看懂的中文"""
    if isinstance(exc, AuthenticationError):
        return (
            "DeepSeek API Key 无效或已过期（401）。"
            "请到 platform.deepseek.com 检查 Key，并在左侧侧边栏重新填写。"
        )
    if isinstance(exc, PermissionDeniedError):
        return "API Key 权限不足或账户已被禁用（403），请检查 DeepSeek 账户状态。"
    if isinstance(exc, RateLimitError):
        return "DeepSeek 接口限流（429），已重试 3 次仍失败，请稍后再试。"
    if isinstance(exc, APITimeoutError):
        return f"DeepSeek 接口响应超时（>{REQUEST_TIMEOUT}s），可能是文件过长或网络波动，请稍后重试。"
    if isinstance(exc, APIConnectionError):
        return "无法连接 DeepSeek 接口，请检查本机网络后重试。"
    if isinstance(exc, BadRequestError):
        # 常见为 context_length_exceeded
        msg = str(exc)
        if "context" in msg.lower() or "token" in msg.lower():
            return "招标文件内容超过模型上下文长度，请确认已启用分块提取或截取关键章节后重试。"
        return f"请求参数被 DeepSeek 拒绝（400）：{exc}"
    if isinstance(exc, InternalServerError):
        return "DeepSeek 服务端错误（500），已重试 3 次仍失败，请稍后再试。"
    return f"LLM 调用失败：{exc}"


def _call_with_retry(create_call):
    """统一重试封装：create_call() 发起一次请求并返回结果"""
    last_exc = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return create_call()
        except _RETRYABLE_ERRORS as e:
            last_exc = e
            if attempt == MAX_RETRIES:
                break
            time.sleep(RETRY_BASE_WAIT ** (attempt - 1))
        except Exception as e:
            # 鉴权/参数错误等不可重试异常，立即包装抛出
            raise LLMError(_friendly_message(e)) from e
    raise LLMError(_friendly_message(last_exc)) from last_exc


def chat(messages: list, model: str = DEFAULT_MODEL, temperature: float = 0.3) -> str:
    """非流式调用，返回完整文本（带重试）"""
    client = get_client()

    def _do():
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            stream=False,
        )
        return response.choices[0].message.content

    return _call_with_retry(_do)


def chat_stream(messages: list, model: str = DEFAULT_MODEL, temperature: float = 0.3):
    """流式调用，yield 每段文本（建连阶段带重试，读取中途失败直接抛出）"""
    client = get_client()

    def _connect():
        return client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            stream=True,
        )

    stream = _call_with_retry(_connect)
    for chunk in stream:
        if chunk.choices and chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content
