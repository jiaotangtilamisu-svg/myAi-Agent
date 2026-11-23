"""Non-sensitive provider usage; never emit prompts, headers, credentials or errors."""
import structlog
from langchain_core.callbacks import BaseCallbackHandler

logger = structlog.get_logger()


class ModelUsageCallback(BaseCallbackHandler):
    def on_llm_end(self, response, **kwargs):
        output = response.llm_output or {}
        usage = output.get("token_usage") or {}
        if not usage:
            for generation in response.generations:
                for result in generation:
                    data = getattr(getattr(result, "message", None), "usage_metadata", None)
                    if data:
                        usage = {"prompt_tokens": data.get("input_tokens"), "completion_tokens": data.get("output_tokens"), "total_tokens": data.get("total_tokens")}
                        break
        logger.info("llm_usage", model=output.get("model_name"), prompt_tokens=usage.get("prompt_tokens"), completion_tokens=usage.get("completion_tokens"), total_tokens=usage.get("total_tokens"), usage_provided=bool(usage))

    def on_llm_error(self, error, **kwargs):
        logger.warning("llm_usage_error", error_type=type(error).__name__)


model_usage_callback = ModelUsageCallback()
