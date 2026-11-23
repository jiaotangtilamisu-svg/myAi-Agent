"""Acceptance infrastructure is itself tested. No real model, DB or ES calls."""
import asyncio
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from starlette.requests import Request


@pytest.fixture
def guard(tmp_path, monkeypatch):
    run=tmp_path/'.cache/stage34/unit'
    run.mkdir(parents=True)
    (run/'plan.json').write_text(json.dumps({'indexPrefix':'q34_unit_','productIndex':'q34_unit_products','vectorIndex':'q34_unit_vectors'}))
    monkeypatch.setenv('QUALITY34_ROOT',str(tmp_path));monkeypatch.setenv('QUALITY34_RUN',str(run))
    path=Path(__file__).resolve().parents[3]/'tools/quality_engineering/stage34/guard.py'
    spec=importlib.util.spec_from_file_location('isolated_guard_fixture',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    import app.config.settings as settings
    monkeypatch.setattr(settings,'Settings',lambda **kw:SimpleNamespace(llm_api_key='fixture-only',embedding_api_key='fixture-only',llm_base_url='https://provider.invalid',embedding_base_url='https://embedding.invalid/v1',llm_model='fixture-model',embedding_model='fixture-embedding',embedding_dimensions=1024))
    return module


def request(body):
    raw=body if isinstance(body,bytes) else json.dumps(body).encode()
    async def receive():return {'type':'http.request','body':raw,'more_body':False}
    return Request({'type':'http','method':'POST','path':'/llm/v1/chat/completions','headers':[]},receive)


def transport(monkeypatch, module, handler):
    cls=httpx.AsyncClient
    class Client(cls):
        def __init__(self,**kw):super().__init__(transport=httpx.MockTransport(handler),**kw)
    monkeypatch.setattr(module.httpx,'AsyncClient',Client)


@pytest.mark.parametrize('path,method,allowed',[('q34_unit_products/_search','POST',True),('q34_unit_vectors/_doc/C','PUT',True),('simlect-index/_doc/C','PUT',False),('simlect_vectorstore/_search','POST',False),('_search','POST',False),('q34_unit_products/../simlect-index','PUT',False),('q34_unit_products%2f../simlect-index','PUT',False)])
def test_index_allowlist_cannot_touch_formal_indices(guard,path,method,allowed):
    assert guard.allowed_es(path,method,b'{}') is allowed


def test_bulk_actions_each_require_exact_isolated_index(guard):
    good=b'{"index":{"_index":"q34_unit_vectors"}}\n{"content":"fixture"}\n'
    bad=good+b'{"delete":{"_index":"simlect_vectorstore","_id":"existing"}}\n'
    assert guard.allowed_es('_bulk','POST',good)
    assert not guard.allowed_es('_bulk','POST',bad)


@pytest.mark.asyncio
async def test_paid_calls_require_explicit_phase_enable_and_bounded_count(guard,monkeypatch):
    calls=[]
    def handle(req):
        body=json.loads(req.content);calls.append(body)
        assert body['max_tokens']==512 and body['stream'] is False
        return httpx.Response(200,json={'usage':{'total_tokens':9},'choices':[]})
    transport(monkeypatch,guard,handle)
    assert (await guard.paid(request({}),'llm','chat/completions')).status_code==503
    assert not calls
    (guard.RUN/'enable-real.json').write_text('{}')
    for _ in range(4):assert (await guard.paid(request({'max_tokens':99999}),'llm','chat/completions')).status_code==200
    assert (await guard.paid(request({}),'llm','chat/completions')).status_code==503
    assert len(calls)==4
    assert json.loads((guard.RUN/'budget-state.json').read_text())['llm']==4


@pytest.mark.asyncio
@pytest.mark.parametrize('status',[429,503])
async def test_upstream_failure_stops_paid_phase_without_retry(guard,monkeypatch,status):
    calls=[]
    def handle(req):calls.append(req);return httpx.Response(status,json={'error':'fixture'})
    transport(monkeypatch,guard,handle);(guard.RUN/'enable-real.json').write_text('{}')
    assert (await guard.paid(request({}),'llm','chat/completions')).status_code==status
    assert len(calls)==1 and (guard.RUN/'api-stopped.json').exists()
    (guard.RUN/'enable-real.json').write_text('{}')
    assert (await guard.paid(request({}),'llm','chat/completions')).status_code==503
    assert len(calls)==1


@pytest.mark.asyncio
@pytest.mark.parametrize('fault',['delayed-body','disconnected-body'])
async def test_http200_headers_body_failure_is_not_success(guard,monkeypatch,fault):
    class Body(httpx.AsyncByteStream):
        async def __aiter__(self):
            if fault=='delayed-body':await asyncio.sleep(.1)
            else:raise httpx.RemoteProtocolError('fixture body disconnected')
            yield b'{}'
    transport(monkeypatch,guard,lambda req:httpx.Response(200,stream=Body()))
    monkeypatch.setattr(guard,'REAL_TIMEOUT_SECONDS',.01)
    (guard.RUN/'enable-real.json').write_text('{}')
    result=await guard.paid(request({}),'llm','chat/completions')
    assert result.status_code==503 and guard.counts['llm']==1
    assert (guard.RUN/'api-stopped.json').exists()
    rows=[json.loads(s) for s in (guard.RUN/'egress.jsonl').read_text().splitlines()]
    assert rows[-1]['http']==200 and rows[-1]['phase']=='BODY'
    assert rows[-1]['retries']==0


@pytest.mark.asyncio
async def test_invalid_json_and_streaming_never_reach_provider(guard,monkeypatch):
    transport(monkeypatch,guard,lambda req:(_ for _ in ()).throw(AssertionError('NO_PROVIDER_CALL')))
    (guard.RUN/'enable-real.json').write_text('{}')
    assert (await guard.paid(request(b'{'),'llm','chat/completions')).status_code==400
    assert (await guard.paid(request({'stream':True}),'llm','chat/completions')).status_code==400
    assert guard.counts['llm']==0


def test_additional_websocket_host_is_deployment_only_and_exact(monkeypatch):
    from app.api.websocket import _origin_allowed
    import app.config.settings as settings
    monkeypatch.setattr(settings,'get_settings',lambda:SimpleNamespace(ws_extra_allowed_hosts=''))
    assert not _origin_allowed('http://127.0.0.2:16001')
    monkeypatch.setattr(settings,'get_settings',lambda:SimpleNamespace(ws_extra_allowed_hosts='127.0.0.2'))
    assert _origin_allowed('http://127.0.0.2:16001')
    assert not _origin_allowed('http://127.0.0.2.evil.example')
    assert not _origin_allowed('ftp://127.0.0.2')
