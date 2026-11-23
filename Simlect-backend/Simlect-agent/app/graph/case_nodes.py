"""Optional case recording after diagnosis; user confirmation is a separate API."""

from copy import deepcopy

from app.config.settings import get_settings
from app.services.aftersales_case_service import create_case
from app.services.agent_runtime import is_cancelled


async def case_record_node(state):
    if state.get("cancelled"):
        return {"cancelled": True}
    report = deepcopy(state.get("diagnosis_report") or {})
    if (report.get("orderFacts") or {}).get("queryStatus") != "SUCCESS":
        workflow = {"status": "INELIGIBLE", "executionAllowed": False}
    elif state.get("collect_only") or not get_settings().aftersales_cases_auto_create:
        workflow = {
            "status": "ON_REQUEST",
            "creationEndpoint": "/api/agent/aftersales/cases",
            "executionAllowed": False,
        }
    else:
        if await is_cancelled(state["user_id"], state["message_id"]):
            return {"cancelled": True}
        try:
            result = await create_case(state["user_id"], state["message_id"], report)
            workflow = {
                "status": "RECORDED",
                "caseId": result["caseId"],
                "caseState": result["state"],
                "version": result["version"],
                "executionAllowed": False,
            }
        except Exception:  # noqa: BLE001 -- Case outage must not fabricate success or erase diagnosis.
            workflow = {"status": "UNAVAILABLE", "executionAllowed": False}
    report["caseWorkflow"] = workflow
    return {
        "diagnosis_report": report,
        "tool_biz": {**(state.get("tool_biz") or {}), "aftersalesDiagnosis": report},
    }
