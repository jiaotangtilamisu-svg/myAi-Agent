"""Disposable MySQL message integration. Never creates rows in a business schema."""
import asyncio
import json
import os
from pathlib import Path
import re
import sys
from unittest.mock import AsyncMock, patch

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'Simlect-backend/Simlect-agent'))
os.environ.update(LLM_BASE_URL='https://model.invalid',EMBEDDING_BASE_URL='https://embedding.invalid',
                  SIMLECT_INTERNAL_TOKEN='quality32-isolated-internal-token-not-for-production-001',
                  SHOPPING_REQUIREMENT_LLM_ENABLED='false',LLM_API_KEY='isolated-fixture',EMBEDDING_API_KEY='isolated-fixture')

async def main():
    import aiomysql
    import httpx
    from app.db import pool
    from app.auth.agent_context import agent_user_context
    from app.services.message_service import agent_message_service as messages,MessagePersistenceError
    from app.services.agent_runtime import _persist_and_notify
    from app.services.stream_service import stream_service
    from app.services.saved_agent_result import load_saved_result
    schema=os.environ['QUALITY_MYSQL_SCHEMA']
    assert re.fullmatch(r'simlect_quality32_[a-f0-9]{12}',schema)
    # Block every HTTP request, including hidden model/embedding calls.
    with patch.object(httpx.AsyncClient,'send',AsyncMock(side_effect=AssertionError('HTTP_FORBIDDEN'))):
        pool._pool=await aiomysql.create_pool(host='127.0.0.1',port=13306,user='root',password=os.environ['QUALITY_MYSQL_PASSWORD'],db=schema,autocommit=True,charset='utf8mb4',minsize=1,maxsize=2)
        checks=[]
        try:
            async with pool.acquire() as cur:
                await cur.execute('CREATE TABLE agent_message LIKE simlect_agent.agent_message')
                await cur.execute("SELECT DATA_TYPE FROM information_schema.columns WHERE table_schema=%s AND table_name='agent_message' AND column_name='biz_data'",(schema,))
                assert (await cur.fetchone())['DATA_TYPE']=='mediumtext'
            checks.append('same MEDIUMTEXT schema')
            for scenario in ['NORMAL','MODEL_TIMEOUT','HTTP_503','BODY_DISCONNECTED','WS_DISCONNECTED']:
                row=await messages.save_user_message('QUALITY32_A',scenario)
                mid=row['messageId']
                evidence={'documentId':'FIXTURE-DOC','version':1,'chunkId':'FIXTURE-CLAUSE',
                          'sourceUrl':'https://official.invalid/fixture','content':'隔离测试证据，不是正式政策。'*400}
                report={'agentType':'shopping','executionAllowed':False,'scenario':scenario,'evidence':[evidence]}
                payload=json.dumps({'agentType':'shopping','messageId':mid,'fullReport':report},ensure_ascii=False)
                assert len(payload)>2000
                notify=AsyncMock(side_effect=RuntimeError('isolated notification fault')) if scenario=='WS_DISCONNECTED' else AsyncMock()
                with patch.object(stream_service,'push_done',notify):
                    assert await _persist_and_notify(row,'正常回答' if scenario=='NORMAL' else '模型未完成，保留有来源的检索证据。','agent',payload)
                stored=await messages.get_message('QUALITY32_A',mid)
                assert stored['status']==2 and json.loads(stored['bizData'])==json.loads(payload)
                assert await messages.get_message('QUALITY32_B',mid) is None
                with agent_user_context('QUALITY32_A','isolated-not-a-real-session'):
                    assert await load_saved_result('QUALITY32_A',mid,'shopping')==report
                # A second completion must not overwrite a completed result.
                assert await messages.complete_message(mid,'MUST_NOT_REPLACE','agent','{}') is False
                assert (await messages.get_message('QUALITY32_A',mid))['bizData']==payload
                checks.extend([scenario+':roundtrip',scenario+':ownership',scenario+':cache-independent recovery',scenario+':terminal protection'])
            row=await messages.save_user_message('QUALITY32_A','cancelled')
            await messages.cancel_message('QUALITY32_A',row['messageId'])
            assert not await messages.complete_message(row['messageId'],'not saved','agent','{}')
            checks.append('cancelled terminal protection')
            # Exercise a real MySQL write error exclusively in the disposable schema.
            async with pool.acquire() as cur:await cur.execute('RENAME TABLE agent_message TO saved_fixture_messages')
            try:
                try:await messages.complete_message(1,'failed','agent','{}')
                except MessagePersistenceError as exc:assert str(exc)=='MESSAGE_WRITE_FAILED'
                else:raise AssertionError('Database failure reported as success')
            finally:
                async with pool.acquire() as cur:await cur.execute('RENAME TABLE saved_fixture_messages TO agent_message')
            checks.append('actual MySQL write error classified')
            result={'passed':len(checks),'failed':0,'checks':checks,'scope':'REAL_ISOLATED_MYSQL_MESSAGE_SERVICE; MODEL_SCENARIOS_AND_WS_MOCK','realLlmCalls':0,'realEmbeddingCalls':0}
            output=Path(os.environ.get('QUALITY_CASE_OUTPUT',str(ROOT/'.cache/stage32/mysql'))).resolve()
            assert output.is_relative_to((ROOT/'.cache').resolve())
            (output/'messages.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
            print(json.dumps({'passed':len(checks),'failed':0}))
        finally:await pool.close_pool()

if __name__=='__main__':asyncio.run(main())
