"""LLM 工厂模块：根据配置创建 LangChain ChatOpenAI 实例，区分对话流式与记忆压缩非流式模型。"""

from langchain_openai import ChatOpenAI  # import statement — OpenAI 兼容聊天模型封装
from urllib.parse import urlparse
import httpx

from app.config.settings import Settings, get_settings  # import statement — 配置类与获取方法
from app.services.model_usage import model_usage_callback


def create_policy_llm(*, http_async_client) -> ChatOpenAI:
    """One bounded JSON selection call; keep ordinary chat streaming unchanged."""
    s = get_settings()
    options = {}
    if urlparse(s.llm_base_url).hostname == "api.deepseek.com":
        # ChatOpenAI renames max_tokens; DeepSeek documents the original key.
        options["extra_body"] = {"thinking": {"type": "disabled"}, "max_tokens": 512}
    return ChatOpenAI(
        api_key=s.llm_api_key, base_url=s.llm_base_url, model=s.llm_model,
        timeout=httpx.Timeout(s.policy_llm_timeout_seconds,
            connect=min(5, s.policy_llm_timeout_seconds),
            write=min(5, s.policy_llm_timeout_seconds),
            pool=min(5, s.policy_llm_timeout_seconds)), max_retries=0,
        streaming=False, max_tokens=None if options else 512, temperature=0,
        http_async_client=http_async_client, callbacks=[model_usage_callback],
        **options,
    )

def create_chat_llm() -> ChatOpenAI:  # 工厂方法 — 类似 Java static factory createChatLlm()

    s = get_settings()  # 读取全局配置 — 类似 @Value 注入
    return ChatOpenAI(  # 构造流式对话 LLM
        api_key=s.llm_api_key,
        base_url=s.llm_base_url,
        model=s.llm_model,
        timeout=s.llm_timeout,
        max_retries=0,
        streaming=True,  # 启用流式输出 — 类似 SSE 逐 token 推送
        stream_usage=True,
        callbacks=[model_usage_callback],
    )

def create_memory_llm() -> ChatOpenAI:  # 工厂方法 — 创建记忆压缩专用 LLM

    s = get_settings()
    api_key, base_url, model, timeout = _resolve_memory_llm_config(s)  # 元组解包 — 类似 Java 多返回值需封装对象
    return ChatOpenAI(
        api_key=api_key,
        base_url=base_url,
        model=model,
        timeout=timeout,
        max_retries=0,
        streaming=False,  # 记忆压缩不需要流式
        callbacks=[model_usage_callback],
    )

def _resolve_memory_llm_config(s: Settings) -> tuple[str, str, str, int]:  # 私有方法 — 解析记忆 LLM 配置

    api_key = (s.memory_llm_api_key or s.llm_api_key).strip()  # 优先 memory 专用 key，否则回退主 LLM key
    base_url = (s.memory_llm_base_url or s.llm_base_url).strip()
    model = (s.memory_llm_model or s.llm_model).strip()

    timeout = s.memory_llm_timeout if s.memory_llm_timeout is not None else s.llm_timeout  # None 类似 null 判空
    return api_key, base_url, model, timeout  # 返回四元组

def create_llm() -> ChatOpenAI:  # 兼容别名 — 默认创建对话 LLM

    return create_chat_llm()
