"""Specialist contracts preserve business values; validation never fills missing facts."""

import hashlib
import json
import math
from decimal import Decimal, InvalidOperation
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Agent = Literal["aftersales", "shopping"]


class Task(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    agent: Agent
    text: str = Field(min_length=1, max_length=500)


class AgentResult(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    agent: Agent
    status: Literal[
        "SUCCESS",
        "NEEDS_CLARIFICATION",
        "ERROR",
        "TIMEOUT",
        "CANCELLED",
        "INVALID_RESULT",
    ]
    data: dict = Field(default_factory=dict)
    errorCode: (
        Literal[
            "SPECIALIST_FAILED",
            "SPECIALIST_TIMEOUT",
            "CONTRACT_REJECTED",
            "TOOL_ERROR",
            "SHOPPING_BUSY",
            "CONTEXT_UNAVAILABLE",
            "CANCELLED",
        ]
        | None
    ) = None
    executionAllowed: Literal[False] = False


def fingerprint(data):
    return hashlib.sha256(
        json.dumps(data, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()
    ).hexdigest()


def deny_private_fields(value):
    if isinstance(value, dict):
        for k, v in value.items():
            if str(k).replace("_", "").replace("-", "").lower() in {
                "userid",
                "token",
                "apikey",
                "password",
                "actiontoken",
                "paramsjson",
            }:
                raise ValueError("Unexpected identity/credential/execution field")
            deny_private_fields(v)
    elif isinstance(value, list):
        for v in value:
            deny_private_fields(v)


def policy(value):
    if not isinstance(value, dict) or value.get("status") not in {
        "SUCCESS",
        "NO_MATCH",
        "LOW_RELEVANCE",
        "EMBEDDING_FAILED",
        "ES_UNAVAILABLE",
        "CATALOG_UNAVAILABLE",
        "RETRIEVAL_ERROR",
        "SKIPPED",
    }:
        raise ValueError("Invalid policy result")
    hits = value.get("hits")
    if (
        not isinstance(hits, list)
        or len(hits) > 20
        or (value["status"] == "SUCCESS" and not hits)
    ):
        raise ValueError("Invalid policy evidence")
    for hit in hits:
        if (
            not isinstance(hit, dict)
            or not all(
                isinstance(hit.get(k), str) and hit[k]
                for k in ("documentId", "documentName", "section", "source", "text")
            )
            or type(hit.get("revision")) is not int
            or hit["revision"] < 1
            or type(hit.get("score")) not in (float, int)
            or not math.isfinite(hit["score"])
        ):
            raise ValueError("Missing policy provenance")


def price(value):
    if value is None:
        return
    if not isinstance(value, str):
        raise TypeError("Price representation changed")
    try:
        n = Decimal(value)
        if not n.is_finite() or n < 0:
            raise ValueError("Invalid business price")
    except InvalidOperation as exc:
        raise ValueError("Invalid business price") from exc


def checked_result(value, expected):
    result = (
        value if isinstance(value, AgentResult) else AgentResult.model_validate(value)
    )
    if result.agent != expected:
        raise ValueError("Wrong specialist returned")
    deny_private_fields(result.data)
    if (
        len(json.dumps(result.data, ensure_ascii=False, allow_nan=False).encode())
        > 384 * 1024
    ):
        raise ValueError("Specialist result too large")
    if result.agent == "shopping" and result.data:
        data = result.data.get("shopping")
        if (
            not isinstance(data, dict)
            or data.get("agentType") != "shopping"
            or data.get("schemaVersion") != 1
            or data.get("executionAllowed") is not False
            or not isinstance(data.get("recommendations"), list)
            or len(data["recommendations"]) > 3
        ):
            raise ValueError("Invalid shopping contract")
        for p in data["recommendations"]:
            if (
                p.get("productStatus") != "ON_SALE"
                or not p.get("productId")
                or not p.get("productName")
            ):
                raise ValueError("Unverified product")
            price(p["price"].get("min"))
            price(p["price"].get("max"))
            if "GET_PRODUCT_DETAIL" not in data.get("toolsCalled", []):
                raise ValueError("Missing required product tool")
            if not isinstance(p.get("eligibleSkus"), list) or not p["eligibleSkus"]:
                raise ValueError("No eligible SKU evidence")
            for sku in p["eligibleSkus"]:
                price(sku.get("price"))
                sku_id = sku.get("sku_id") or sku.get("property_value_id_hash")
                original = next(
                    (
                        s
                        for s in p.get("skus", [])
                        if (s.get("sku_id") or s.get("property_value_id_hash"))
                        == sku_id
                    ),
                    None,
                )
                if (
                    not sku_id
                    or not original
                    or any(
                        sku.get(k) != original.get(k)
                        for k in ("price", "stock", "stock_query_status")
                    )
                ):
                    raise ValueError("Eligible SKU facts differ from original evidence")
                count = sku.get("stock")
                if count is not None and (
                    type(count) is not int
                    or count <= 0
                    or sku.get("stock_query_status") != "SUCCESS"
                ):
                    raise ValueError("Invalid available stock evidence")
                if count is None and sku.get("stock_query_status") == "SUCCESS":
                    raise ValueError("Unknown stock mislabeled as success")
                if (
                    sku.get("product_id") is not None
                    and sku["product_id"] != p["productId"]
                ):
                    raise ValueError("SKU belongs to another product")
            known = [
                Decimal(s["price"])
                for s in p["eligibleSkus"]
                if s.get("price") is not None
            ]
            if (
                not known
                and (
                    p["price"].get("min") is not None
                    or p["price"].get("max") is not None
                )
            ) or (
                known
                and (
                    p["price"].get("min") is None
                    or p["price"].get("max") is None
                    or Decimal(p["price"]["min"]) != min(known)
                    or Decimal(p["price"]["max"]) != max(known)
                )
            ):
                raise ValueError("Price range does not match eligible SKU evidence")
            availability = (
                "IN_STOCK"
                if any(s.get("stock") is not None for s in p["eligibleSkus"])
                else "UNKNOWN"
            )
            if p.get("availability") != availability:
                raise ValueError("Availability contradicts SKU evidence")
    if result.agent == "aftersales" and result.data:
        if 'caseList' in result.data:
            rows=result.data['caseList']
            if not isinstance(rows,list) or len(rows)>20 or any(not isinstance(r,dict) or not all(isinstance(r.get(k),str) and r[k] for k in ('caseId','orderId','state')) for r in rows):raise ValueError('Invalid case list')
            return result
        if 'orderList' in result.data:
            rows=result.data['orderList']
            if not isinstance(rows,list) or len(rows)>20 or any(not isinstance(r,dict) or not isinstance(r.get('orderId'),str) or not r['orderId'] for r in rows):
                raise ValueError('Invalid order list')
            return result
        diagnosis = result.data.get("diagnosis")
        if diagnosis is not None:
            if (
                not isinstance(diagnosis, dict)
                or diagnosis.get("schemaVersion") != 1
                or diagnosis.get("executionAllowed") is not False
                or type(diagnosis.get("approvalRequired")) is not bool
            ):
                raise ValueError("Invalid advice contract")
            order = diagnosis.get("orderFacts") or {}
            if order.get("queryStatus") == "SUCCESS":
                data = order.get("data") or {}
                if data.get("ownerVerified") is not True or data.get(
                    "orderId"
                ) != diagnosis.get("orderId"):
                    raise ValueError("Missing ownership evidence")
            if any(
                a.get("executionAllowed") is not False
                for a in diagnosis.get("recommendedActions", [])
            ):
                raise ValueError("Executable proposal is forbidden")
            if (
                diagnosis.get("caseType")
                in {"REFUND_PROGRESS", "PAYMENT_ANOMALY", "PRODUCT_QUALITY"}
                or diagnosis.get("diagnosis", {}).get("status")
                in {"UNCERTAIN", "CONFLICT"}
            ) and diagnosis["approvalRequired"] is not True:
                raise ValueError("Required human review missing")
            policy(diagnosis["policyEvidence"])
        elif "policy" in result.data:
            policy(result.data["policy"])
        else:
            raise ValueError("Missing aftersales evidence")
    if result.status == "SUCCESS" and not result.data:
        raise ValueError("Empty success is not evidence")
    return result
