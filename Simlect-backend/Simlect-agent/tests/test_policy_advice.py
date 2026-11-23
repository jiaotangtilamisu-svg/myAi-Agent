import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from app.rag import advice as mod

EVIDENCE={"status":"SUCCESS","hits":[{"chunkId":"known","documentId":"doc","source":"fixture://test","text":"TEST ONLY"}]}

@pytest.mark.asyncio
async def test_model_only_selects_verified_sources_and_questions(monkeypatch):
    fake=SimpleNamespace(ainvoke=AsyncMock(return_value=SimpleNamespace(content=json.dumps({'selectedChunkIds':['known'],'neededFacts':['category']}))))
    monkeypatch.setattr(mod,'create_policy_llm',lambda **kwargs:fake)
    result=await mod.policy_advice('TEST ONLY',EVIDENCE)
    assert result['status']=='MODEL_GROUNDED' and result['executionAllowed'] is False
    assert '商城自有承诺' in mod.render_advice(result) and '不能确认' in mod.render_advice(result)

@pytest.mark.asyncio
@pytest.mark.parametrize('body',[{'selectedChunkIds':['forged'],'neededFacts':[]},{'selectedChunkIds':['known'],'neededFacts':['execute_refund']},{'selectedChunkIds':['known'],'neededFacts':[],'promise':'refund granted'}])
async def test_model_cannot_invent_ids_actions_or_legal_promises(monkeypatch,body):
    monkeypatch.setattr(mod,'create_policy_llm',lambda **kwargs:SimpleNamespace(ainvoke=AsyncMock(return_value=SimpleNamespace(content=json.dumps(body)))))
    result=await mod.policy_advice('TEST ONLY',EVIDENCE)
    assert result['status']=='UNAVAILABLE' and 'refund granted' not in mod.render_advice(result)

@pytest.mark.asyncio
async def test_no_match_never_calls_llm(monkeypatch):
    def fail():raise AssertionError('must not invoke')
    monkeypatch.setattr(mod,'create_policy_llm',fail)
    assert (await mod.policy_advice('TEST',{'status':'NO_MATCH','hits':[]}))['status']=='NOT_CALLED'

@pytest.mark.asyncio
async def test_model_error_fails_closed(monkeypatch):
    monkeypatch.setattr(mod,'create_policy_llm',lambda **kwargs:SimpleNamespace(ainvoke=AsyncMock(side_effect=RuntimeError('private error'))))
    assert (await mod.policy_advice('TEST',EVIDENCE))['status']=='UNAVAILABLE'

@pytest.mark.asyncio
async def test_final_persisted_answer_keeps_grounded_advice(monkeypatch):
    from app.services import agent_runtime as rt
    done=AsyncMock();saved=AsyncMock()
    monkeypatch.setattr(rt.stream_service,'push_done',done)
    monkeypatch.setattr(rt.agent_message_service,'complete_message',saved)
    await rt.finalize_agent_response({'userId':'test','messageId':1},[],[],
        user_text='超过七天还能退货吗',tool_biz={'policyQuery':{'status':'NO_MATCH','hits':[]},
        'policyAdvice':{'status':'MODEL_GROUNDED','neededFacts':['category']}})
    assert '仅凭' in saved.await_args.args[1]
    assert done.await_args.args[2] == saved.await_args.args[1]

