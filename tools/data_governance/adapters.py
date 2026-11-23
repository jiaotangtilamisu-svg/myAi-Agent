"""Adapters to EXISTING Java contracts. No historical customer -> live user conversion."""

import hashlib
import re
from dataclasses import dataclass
from decimal import Decimal

from .olist import canonical, digest


@dataclass(frozen=True)
class SyntheticBinding:
    """Loaded from a persisted provenance mapping, never from LLM/request arguments."""

    source_record_id: str
    product_id: str
    sku_hash: str
    source_type: str
    target_user_id: str

    def validate(self):
        if (
            self.source_type != "SYNTHETIC"
            or not self.source_record_id
            or not re.fullmatch(r"SYNTH_[A-Z0-9]{1,4}", self.target_user_id)
        ):
            raise ValueError("ISOLATED_SYNTHETIC_BINDING_REQUIRED")
        if not re.fullmatch(
            r"[A-Za-z0-9_-]{1,15}", self.product_id
        ) or not re.fullmatch(r"[a-f0-9]{32}", self.sku_hash):
            raise ValueError("INVALID_BOUND_SKU")


class StockScenarioAdapter:
    def __init__(self, transport, resolve_binding, claim_operation=None):
        self.transport = transport
        self.resolve_binding = resolve_binding
        self.claim_operation = claim_operation

    def reserve(self, source_id, scenario_id, quantity):
        return self._change(source_id, scenario_id, quantity, False)

    def release(self, source_id, scenario_id, quantity):
        return self._change(source_id, scenario_id, quantity, True)

    def _change(self, source_id, scenario_id, quantity, release):
        binding = self.resolve_binding(source_id)
        if not isinstance(binding, SyntheticBinding):
            raise ValueError("REGISTERED_BINDING_REQUIRED")
        binding.validate()
        if type(quantity) is not int or not 0 < quantity <= 100:
            raise ValueError("INVALID_QUANTITY")
        if (
            not isinstance(scenario_id, str)
            or not scenario_id
            or len(scenario_id) > 100
        ):
            raise ValueError("INVALID_SCENARIO")
        if self.claim_operation is None:
            raise ValueError("DURABLE_OPERATION_INTENT_REQUIRED")
        # Persist an immutable intent BEFORE any stock call; changed quantities must be rejected.
        reservation = "DG23:" + digest("|".join((source_id, scenario_id)))
        self.claim_operation(
            reservation,
            digest(
                canonical(
                    {
                        "source": source_id,
                        "product": binding.product_id,
                        "sku": binding.sku_hash,
                        "quantity": quantity,
                        "actor": binding.target_user_id,
                    }
                )
            ),
        )
        payload = {
            "operationId": reservation + (":release" if release else ":reserve"),
            "items": [
                {
                    "productId": binding.product_id,
                    "propertyValueIdHash": binding.sku_hash,
                    "changeAmount": quantity if release else -quantity,
                }
            ],
        }
        if release:
            payload["requiredOperationId"] = reservation + ":reserve"
        return self.transport.post("/internal/stock/changeBatch", payload)


class BusinessReadAdapter:
    def __init__(self, transport):
        self.transport = transport

    def products(self, ids):
        if not isinstance(ids, list) or not 1 <= len(ids) <= 12:
            raise ValueError("BOUNDED_PRODUCT_IDS_REQUIRED")
        return self.transport.post(
            "/internal/product/agent/queryBatch", {"productIds": ids}
        )

    def owned_order(self, order_id):
        # Transport supplies a verified server identity/session, not an argument supplied by a model.
        user = getattr(self.transport, "verified_user_id", None)
        if not user:
            raise ValueError("VERIFIED_SERVER_USER_REQUIRED")
        return self.transport.post(
            "/internal/order/agent/getOrder", {"orderId": order_id, "userId": user}
        )


def catalogue_publication_plan(candidate):
    """ProductSaveDTO plan only: generated productId must be returned/registered before retryable publication."""
    from .catalogue import validate_candidate

    validate_candidate(candidate)
    return {
        "state": "REQUIRES_ADMIN_PUBLICATION",
        "sourceRecordId": candidate["sourceRecordId"],
        "existingEndpoint": "/admin-api/productInfo/addProduct",
        "requires": [
            "authenticated administrator",
            "confirmed category/property IDs",
            "capture generated productId",
            "register provenance atomically or reconcile",
            "stock binding before simulations",
        ],
        "candidate": candidate,
        "executionAllowed": False,
    }


def product_save_dto(candidate, category_id, parent_category_id, property_id):
    """Map a reviewed candidate into the existing ProductSaveDTO. Does not POST it."""
    from .catalogue import validate_candidate

    validate_candidate(candidate)
    if not all(
        re.fullmatch(r"[A-Za-z0-9_-]{1,5}", str(v))
        for v in (category_id, parent_category_id)
    ):
        raise ValueError("EXISTING_CATEGORY_IDS_REQUIRED")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,10}", str(property_id)):
        raise ValueError("EXISTING_PROPERTY_ID_REQUIRED")
    properties = []
    skus = []
    for i, sku in enumerate(candidate["skus"]):
        value_id = "V" + digest(sku["sourceSkuId"])[:14]
        properties.append(
            {
                "propertyId": property_id,
                "propertyName": "规格",
                "propertyValueId": value_id,
                "propertyValue": next(iter(sku["specifications"].values())),
                "propertySort": 1,
                "sort": i,
                "coverType": 0,
            }
        )
        skus.append(
            {
                "propertyValueIds": value_id,
                "propertyValueIdHash": hashlib.md5(
                    value_id.encode(), usedforsecurity=False
                ).hexdigest(),
                "price": sku["price"],
                "sort": i,
            }
        )
    prices = [Decimal(s["price"]) for s in candidate["skus"]]
    return {
        "productInfo": {
            "productName": candidate["productName"],
            "productDesc": "合成测试商品；来源 "
            + candidate["sourceUrl"]
            + "；sourceRecordId="
            + candidate["sourceRecordId"]
            + "；价格/SKU/库存均为合成测试，不是真实商业报价。",
            "categoryId": category_id,
            "pCategoryId": parent_category_id,
            "status": 0,
            "minPrice": str(min(prices)),
            "maxPrice": str(max(prices)),
        },
        "productPropertyList": properties,
        "skuList": skus,
    }


def order_scenario_plan(binding):
    binding.validate()
    return {
        "sourceType": "SYNTHETIC",
        "actor": binding.target_user_id,
        "executionAllowed": False,
        "existingContracts": {
            "create": "/api/order/postOrder",
            "mockMode": "/api/order/paymentMode",
            "mockPayment": "/api/order/localPay",
            "case": "/api/agent/aftersales/cases",
        },
        "preconditions": [
            "dedicated authenticated synthetic user",
            "only provenance-bound synthetic SKUs",
            "valid synthetic address",
            "server localMock=true",
            "user confirmation and original admin approval for cases",
        ],
        "forbidden": [
            "historical order publication",
            "real payment",
            "refund execution",
            "approval bypass",
        ],
    }
