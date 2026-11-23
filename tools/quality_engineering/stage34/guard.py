"""Local egress guard: allow-listed isolated ES indices and bounded paid API calls.

Only this process reads the existing API credentials. Test application processes
receive a dummy local proxy credential. No request/response body or auth header
is logged. A missing enable-real.json means paid calls are forbidden.
"""
import asyncio
import json
import os
import time
from pathlib import Path

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

ROOT = Path(os.environ['QUALITY34_ROOT']).resolve()
RUN = Path(os.environ['QUALITY34_RUN']).resolve()
PLAN = json.loads((RUN/'plan.json').read_text(encoding='utf8'))
assert RUN.is_relative_to(ROOT/'.cache/stage34')
PREFIX = PLAN['indexPrefix']
app = FastAPI(docs_url=None, redoc_url=None)
lock = asyncio.Lock()
counts = json.loads((RUN/'budget-state.json').read_text()) if (RUN/'budget-state.json').exists() else {'llm': 0, 'embedding': 0}
REAL_TIMEOUT_SECONDS = 20


def record(row):
    with (RUN/'egress.jsonl').open('a', encoding='utf8') as out:
        out.write(json.dumps({'at': time.time(), **row}, ensure_ascii=False)+'\n')


def allowed_es(path, method, raw):
    if any(part in {'.','..'} for part in path.split('/')) or '%' in path or '\\' in path:
        return False
    pieces = path.strip('/').split('/')
    if method == 'GET' and path in {'', '/', '_cluster/health', '_nodes/http'}:
        return True
    if pieces[0] in {PLAN['productIndex'], PLAN['vectorIndex']}:
        return True
    if path == '_bulk':
        try:
            # Each action must name an isolated index. Source rows are skipped.
            lines = [json.loads(s) for s in raw.splitlines() if s.strip()]
            i = 0
            while i < len(lines):
                action = lines[i]
                if len(action) != 1 or next(iter(action)) not in {'index','create','update','delete'}:
                    return False
                kind = next(iter(action))
                index = action[kind].get('_index', '')
                if index not in {PLAN['productIndex'], PLAN['vectorIndex']}:
                    return False
                i += 1 if kind == 'delete' else 2
            return True
        except (ValueError, TypeError, KeyError):
            return False
    return False


async def paid(request, kind, suffix):
    raw = await request.body()
    try:
        body = json.loads(raw)
    except ValueError:
        return JSONResponse({'error': {'type':'INVALID_JSON'}}, status_code=400)
    limit = {'llm': 4, 'embedding': 6}[kind]
    async with lock:
        if not (RUN/'enable-real.json').is_file() or (RUN/'api-stopped.json').exists() or counts[kind] >= limit:
            record({'kind':kind,'outcome':'BLOCKED_BUDGET_OR_NOT_ENABLED','forwarded':False})
            return JSONResponse({'error':{'type':'QUALITY34_REAL_API_DISABLED'}},status_code=503)
        if kind == 'llm' and body.get('stream'):
            record({'kind':kind,'outcome':'BLOCKED_STREAMING','forwarded':False})
            return JSONResponse({'error':{'type':'QUALITY34_NONSTREAM_ONLY'}},status_code=400)
        if len(raw) > 50000 or (kind == 'embedding' and len(raw)>12000):
            return JSONResponse({'error':{'type':'QUALITY34_INPUT_LIMIT'}},status_code=413)
        counts[kind] += 1
        attempt = counts[kind]
        (RUN/'budget-state.json').write_text(json.dumps(counts),encoding='utf8')
    # Normal configuration loader: credentials remain in this process only.
    from app.config.settings import Settings
    settings = Settings(_env_file=ROOT/'Simlect-backend/Simlect-agent/.env')
    key = settings.llm_api_key if kind == 'llm' else settings.embedding_api_key
    upstream = settings.llm_base_url if kind == 'llm' else settings.embedding_base_url
    if not key:
        record({'kind':kind,'attempt':attempt,'outcome':'MISSING_CONFIGURATION','forwarded':False})
        return JSONResponse({'error':{'type':'QUALITY34_CONFIG_MISSING'}},status_code=503)
    if kind == 'llm':
        body.pop('max_completion_tokens', None)
        body['max_tokens'] = 512
        body['stream'] = False
        body['model'] = settings.llm_model
        if httpx.URL(upstream).host == 'api.deepseek.com':
            body['thinking'] = {'type':'disabled'}
    else:
        body['model'] = settings.embedding_model
        body['dimensions'] = settings.embedding_dimensions
    base = upstream.rstrip('/')
    if not base.endswith('/v1'):
        base += '/v1'
    started = time.monotonic()
    status = None
    phase = 'CONNECT'
    try:
        async with asyncio.timeout(REAL_TIMEOUT_SECONDS):
            async with httpx.AsyncClient(timeout=httpx.Timeout(REAL_TIMEOUT_SECONDS,connect=min(5,REAL_TIMEOUT_SECONDS)),trust_env=False,follow_redirects=False) as client:
                async with client.stream('POST',base+'/'+suffix,headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'},json=body) as response:
                    status = response.status_code
                    phase = 'BODY'
                    content = await response.aread()
        usage = None
        try:
            result = json.loads(content)
            usage = result.get('usage')
        except ValueError:
            pass
        record({'kind':kind,'attempt':attempt,'forwarded':True,'http':status,'elapsedMs':round((time.monotonic()-started)*1000),'usage':usage,'model':body['model'],'maxOutputTokens':512 if kind=='llm' else None,'retries':0})
        if status >= 500 or status == 429:
            (RUN/'api-stopped.json').write_text(json.dumps({'kind':kind,'attempt':attempt,'http':status}),encoding='utf8')
            (RUN/'enable-real.json').unlink(missing_ok=True)
        # No upstream authentication headers, cookies, or body are persisted.
        return Response(content,status_code=status,media_type='application/json')
    except Exception as exc:
        record({'kind':kind,'attempt':attempt,'forwarded':True,'http':status,'phase':phase,'elapsedMs':round((time.monotonic()-started)*1000),'errorType':type(exc).__name__,'retries':0})
        # Stop the paid phase on the first transport/upstream failure.
        (RUN/'api-stopped.json').write_text(json.dumps({'kind':kind,'attempt':attempt,'errorType':type(exc).__name__}),encoding='utf8')
        (RUN/'enable-real.json').unlink(missing_ok=True)
        return JSONResponse({'error':{'type':'QUALITY34_UPSTREAM_FAILURE'}},status_code=503)


@app.get('/quality34/health')
async def health():
    return {'status':'ok','indexPrefix':PREFIX,'paidEnabled':(RUN/'enable-real.json').exists(),'counts':counts}


@app.api_route('/llm/v1/chat/completions',methods=['POST'])
async def llm(request: Request):
    return await paid(request,'llm','chat/completions')


@app.api_route('/embedding/v1/embeddings',methods=['POST'])
async def embedding(request: Request):
    return await paid(request,'embedding','embeddings')


@app.api_route('/{path:path}',methods=['GET','POST','PUT','DELETE','HEAD'])
async def es(request: Request,path: str):
    raw = await request.body()
    if not allowed_es(path,request.method,raw):
        record({'kind':'es','outcome':'DENIED_NON_ISOLATED_TARGET','method':request.method,'path':path})
        return JSONResponse({'error':'QUALITY34_INDEX_NOT_ALLOWED'},status_code=403)
    # Prevent a reindex request or aliases from escaping the index allow-list.
    if any(p in {'_reindex','_aliases','_alias','_snapshot','_restore'} for p in path.split('/')):
        return JSONResponse({'error':'QUALITY34_OPERATION_NOT_ALLOWED'},status_code=403)
    async with httpx.AsyncClient(timeout=25,trust_env=False,follow_redirects=False) as client:
        response = await client.request(request.method,'http://127.0.0.1:9200/'+path,params=request.query_params,content=raw,headers={k:v for k,v in request.headers.items() if k.lower() in {'content-type','accept'}})
    record({'kind':'es','method':request.method,'path':path,'http':response.status_code})
    return Response(response.content,status_code=response.status_code,headers={k:v for k,v in response.headers.items() if k.lower() in {'content-type','x-elastic-product'}})
