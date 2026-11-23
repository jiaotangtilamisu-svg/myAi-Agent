import httpx
import math
import structlog

from app.config.settings import get_settings
from app.resilience.circuit_breaker import circuit_registry

logger = structlog.get_logger()

async def embed_text(text: str) -> list[float] | None:

    settings = get_settings()
    breaker = circuit_registry.get_or_create("embedding", failure_threshold=3, recovery_timeout=30)
    if not breaker.allow_request() or not text.strip():
        return None
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{settings.embedding_base_url.rstrip('/')}/embeddings",
                headers={"Authorization": f"Bearer {settings.embedding_api_key}"},
                json={
                    "model": settings.embedding_model,
                    "input": text,
                    "dimensions": settings.embedding_dimensions,
                    "encoding_format": "float",
                },
            )
            resp.raise_for_status()
            data = resp.json()

            vector = data["data"][0]["embedding"]
            if (not isinstance(vector, list) or len(vector) != settings.embedding_dimensions
                    or any(isinstance(v, bool) or not isinstance(v, (int, float))
                           or not math.isfinite(v) for v in vector)):
                raise ValueError('INVALID_EMBEDDING_VECTOR')
            usage = data.get("usage") or {}
            logger.info("embedding_usage", model=settings.embedding_model, dimension=len(vector), prompt_tokens=usage.get("prompt_tokens"), total_tokens=usage.get("total_tokens"), usage_provided=bool(usage))
            breaker.record_success()
            return vector
    except httpx.HTTPStatusError as e:
        breaker.record_failure()
        logger.warning("embedding_failed", status=e.response.status_code if e.response is not None else None,
                       error_type=type(e).__name__)
        return None
    except Exception as e:
        breaker.record_failure()
        logger.warning("embedding_failed", error_type=type(e).__name__)
        return None
