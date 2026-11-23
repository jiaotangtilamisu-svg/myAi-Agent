"""Opt-in, local public-read graph exercise; no authenticated message writes."""
import asyncio
import importlib.util
import json
from pathlib import Path
import uuid

ROOT = Path.cwd()
spec = importlib.util.spec_from_file_location("stage33_reads", ROOT / "tools/quality_engineering/stage33/local_business_reads.py")
reads = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reads)


async def main():
    user = "QUALITY33_" + uuid.uuid4().hex
    checks = []
    await reads.redis_service.connect()
    try:
        previous = {}
        with reads.agent_user_context(user, "public-read-not-login-fixture"):
            for i, text in enumerate(["推荐8000元以上的三星手机", "换成苹果", "预算改成5000以内", "增加256GB要求"]):
                state = await reads.build_shopping_graph().ainvoke({"user_id": user, "message_id": 2100033300 + i, "text": text, "previous": previous})
                result = state["result"]
                req = result["requirements"]
                assert req["brands"] == (["三星"] if i == 0 else ["苹果"])
                assert req["category"] == "手机"
                assert req["budgetMin"] == ("8000" if i < 2 else None)
                assert req["budgetMax"] == (None if i < 2 else "5000")
                if i == 3:
                    assert req["attributes"]["存储容量"] == "256GB"
                assert result["status"] in {"SUCCESS", "NO_RESULTS", "NO_MATCHING_SKU"}
                reads.assert_shopping_result(result, state.get("products", []), floor=req["budgetMin"], ceiling=req["budgetMax"])
                assert all(p["attributes"].get("品牌") == req["brands"] for p in result["recommendations"])
                if i < 2:
                    assert result["recommendations"], "EXPECTED_REAL_CATALOGUE_BRAND_CANDIDATE"
                checks.append({"question": text, "requirements": req, "status": result["status"], "ids": [p["productId"] for p in result["recommendations"]], "tools": result["toolsCalled"]})
                previous = {"requirements": req, "ids": [p["productId"] for p in result["recommendations"]], "baseline": [{"price": p["price"]["min"]} for p in result["recommendations"]]}
        result = {"scope": "REAL_LOCAL_MCP_PRODUCT_STOCK_READS_WITH_DIRECT_LANGGRAPH_CONTEXT_NOT_MESSAGE_LOGIN_E2E", "passed": len(checks), "failed": 0, "checks": checks, "businessRequests": reads.calls, "realLlmCalls": 0, "realEmbeddingCalls": 0}
        (ROOT / ".cache/stage33/multi-turn-reads.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print("Multi-turn real business reads:", len(checks), "passed")
    finally:
        await reads.redis_service.close()


if __name__ == "__main__":
    asyncio.run(main())
