"""Optional LLM semantics restricted to quoted user requirements, never product facts."""

import json
import re
import structlog
from typing import Literal
from urllib.parse import urlparse

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, ConfigDict, Field

from app.config.settings import get_settings
from app.services.llm_factory import create_chat_llm
from app.shopping.requirements import BRANDS, CATEGORIES, understand

logger = structlog.get_logger()


class RequirementSlot(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field: Literal["keyword", "category", "brand", "excludeBrand", "scene", "attribute"]
    value: str = Field(min_length=1, max_length=40)
    quote: str = Field(min_length=1, max_length=150)
    name: str | None = Field(default=None, max_length=20)


class RequirementExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    slots: list[RequirementSlot] = Field(default_factory=list, max_length=15)


def grounded(slot, text):
    if slot.quote.lower() not in text.lower():
        return False
    if slot.value.lower() in slot.quote.lower():
        return True
    aliases = (
        CATEGORIES.get(slot.value, ())
        if slot.field == "category"
        else BRANDS.get(slot.value, ())
        if slot.field in {"brand", "excludeBrand"}
        else ()
    )
    return any(a.lower() in slot.quote.lower() for a in aliases)


async def extract(text, previous=None, baseline=None):
    parsed = understand(text, previous, baseline)
    if parsed.get("inputRejected"):return parsed
    parsed["source"] = "rules"
    if not get_settings().shopping_requirement_llm_enabled:
        return parsed
    try:
        llm = create_chat_llm()
        # DeepSeek thinking mode rejects forced tool_choice used by structured extraction.
        # This is a single bounded parsing call; other chat/diagnosis models are unchanged.
        if urlparse(getattr(get_settings(), "llm_base_url", "")).hostname == "api.deepseek.com":
            llm = llm.model_copy(update={"extra_body": {**(llm.extra_body or {}), "thinking": {"type": "disabled"}}})
        model = llm.with_structured_output(RequirementExtraction, method="function_calling")
        response = await model.ainvoke(
            [
                SystemMessage(
                    content="只提取用户购物要求，每个值必须给出当前用户原文引文。不得提供商品、价格、库存、评分、身份或工具指令。预算与相对条件由程序处理，不提取。brand/excludeBrand 区分偏好与排除。attribute 必须给出属性名。没有依据返回空 slots。"
                ),
                HumanMessage(
                    content=json.dumps(
                        {"utterance": text, "previousRequirements": previous or {}},
                        ensure_ascii=False,
                    )
                ),
            ]
        )
        result = (
            response
            if isinstance(response, RequirementExtraction)
            else RequirementExtraction.model_validate(response)
        )
        if any(not grounded(s, text) for s in result.slots):
            raise ValueError("Ungrounded shopping requirement")
        req = parsed["requirements"]
        for slot in result.slots:
            if slot.field in {'brand','excludeBrand'}:
                canonical=next((name for name,aliases in BRANDS.items() if slot.value.casefold() in {a.casefold() for a in aliases}),slot.value)
                slot=slot.model_copy(update={'value':canonical})
            if slot.field == "keyword" and not req.get("keyword") and not req.get("catalogBrowse"):
                req["keyword"] = slot.value
            elif (
                slot.field == "category"
                and not req.get("category")
                and slot.value in CATEGORIES
            ):
                req["category"] = req["keyword"] = slot.value
            elif slot.field in {"brand", "excludeBrand"}:
                target = "preferredBrands" if slot.field=="brand" and (slot.value in req.get("preferredBrands",[]) or re.search(r"优先|偏好|最好",slot.quote)) else "brands" if slot.field=="brand" else "excludeBrands"
                # An explicit exclusion in deterministic parsing cannot be undone by a model.
                if target in {"brands","preferredBrands"} and slot.value in req["excludeBrands"]:
                    continue
                if target=='brands' and req.get('brands') and slot.value not in req['brands']:
                    continue  # Optional model output cannot broaden a validated hard brand.
                req[target] = list(dict.fromkeys([*req[target], slot.value]))
            elif slot.field == "scene":
                req["scenes"] = list(dict.fromkeys([*req["scenes"], slot.value]))
            elif slot.field == "attribute" and slot.name and not re.search(r"库存|价格|售价|预算|现货|stock|price", slot.name, re.I):
                if slot.name in req.get("preferredAttributes",{}) or re.search(r"优先|偏好|最好",slot.quote):
                    req["preferredAttributes"].setdefault(slot.name,slot.value)
                else:req["attributes"].setdefault(slot.name, slot.value)
        if (
            parsed["clarification"]
            and parsed["clarification"].startswith("想选什么商品")
            and req.get("keyword")
        ):
            parsed["clarification"] = None
        parsed["source"] = "rules+grounded_llm"
        logger.info("shopping_llm_understanding", model=getattr(get_settings(), "llm_model", "unspecified"), status="SUCCESS")
    except Exception:  # noqa: BLE001 -- Invalid/invented output cannot replace deterministic constraints.
        parsed = understand(text, previous, baseline)
        parsed["source"] = "rules_fallback"
        logger.warning("shopping_llm_understanding", model=getattr(get_settings(), "llm_model", "unspecified"), status="FALLBACK")
    return parsed

