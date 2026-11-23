from unittest.mock import AsyncMock
import pytest
from app.auth.agent_context import agent_user_context
from app.domain.aftersales_intent import classify
from app.services.aftersales_context import load_case_progress, render_case_progress
from app.services.java_internal_client import java_internal_client

ORDER='202611011536325281K0gVGxDdIOERZy'

@pytest.mark.parametrize('text',[f'订单{ORDER}的货退货进程',f'查询订单{ORDER}退款进度','查询退款','退货进展','查看售后申请','退款到账了吗'])
def test_progress_is_not_a_new_refund_application(text):
    assert classify(text)['operation']=='AFTERSALES_PROGRESS'

@pytest.mark.asyncio
async def test_named_order_uses_scoped_list_and_one_verified_detail(monkeypatch):
    row={'caseId':'case-A','orderId':ORDER,'state':'IN_PROGRESS','version':16}
    detail={**row,'fulfillment':{'refundMode':'MOCK','refundStatus':'PENDING','logisticsStatus':'REGISTERED'}}
    call=AsyncMock(side_effect=[[row],detail]);monkeypatch.setattr(java_internal_client,'post_json',call)
    with agent_user_context('A','unit-fixture'):
        rows=await load_case_progress('A',ORDER)
    assert call.await_count==2
    assert call.await_args_list[0].args==('/api/order/aftersalesCase/list',{'orderId':ORDER})
    text=render_case_progress(rows)
    assert '尚无验收记录' in text and '待执行，尚未开始' in text and '重复登记物流不会推进退款' in text
    assert '成功（仅模拟' not in text

@pytest.mark.asyncio
async def test_mismatched_case_detail_is_never_exposed(monkeypatch):
    call=AsyncMock(side_effect=[[{'caseId':'A','orderId':ORDER,'state':'IN_PROGRESS'}],{'caseId':'B','orderId':'OTHER','fulfillment':{'refundStatus':'SUCCEEDED'}}])
    monkeypatch.setattr(java_internal_client,'post_json',call)
    with agent_user_context('A','unit-fixture'):rows=await load_case_progress('A',ORDER)
    assert rows[0]['progressDetailStatus']=='UNAVAILABLE' and 'fulfillment' not in rows[0]

def test_no_case_is_not_proof_of_no_bank_refund():
    assert '不能据此确认资金是否到账' in render_case_progress([])
