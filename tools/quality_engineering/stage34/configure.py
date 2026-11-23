"""Generate deployment-only settings; secrets stay in ignored private files."""
import json
from pathlib import Path
from urllib.parse import quote

ROOT=Path(__file__).resolve().parents[3]
BASE=ROOT/'.cache/stage34'
RUN=Path(json.loads((BASE/'active.json').read_text())['directory'])
p=json.loads((RUN/'plan.json').read_text())
c=json.loads((RUN/'private.json').read_text())

common={'JAVA_HOME':'E:/JDK17','TEMP':'E:/SimlectRuntime/tmp','TMP':'E:/SimlectRuntime/tmp','PYTHONUTF8':'1',
 'LANGCHAIN_TRACING_V2':'false','LANGSMITH_TRACING':'false','OTEL_SDK_DISABLED':'true',
 'SIMLECT_INTERNAL_TOKEN':c['internalToken'],'MYSQL_HOST':'127.0.0.1','MYSQL_PORT':'13306','MYSQL_USER':c['dbUser'],'MYSQL_PASSWORD':c['dbPassword'],
 'REDIS_HOST':'127.0.0.1','REDIS_PORT':'26379','REDIS_DB':'0','REDIS_PASSWORD':'','SPRING_DATA_REDIS_DATABASE':'0',
 'RABBIT_HOST':'127.0.0.1','RABBIT_PORT':'5672','RABBIT_USER':c['mqUser'],'RABBIT_PASSWORD':c['mqPassword'],'RABBIT_VHOST':p['rabbitVhost'],
 'RABBITMQ_URL':'amqp://'+c['mqUser']+':'+quote(c['mqPassword'],safe='')+'@127.0.0.1:5672/'+quote(p['rabbitVhost'],safe=''),
 'NACOS_ADDR':'127.0.0.1:8848','NACOS_GROUP':p['nacosGroup'],'NACOS_NAMESPACE':'','SEATA_ENABLED':'false',
 'SPRING_CLOUD_SENTINEL_ENABLED':'false','SIMLECT_SENTINEL_FEIGN_RULES':'false',
 'ADMIN_ACCOUNT':c['adminAccount'],'ADMIN_PASSWORD':c['adminPassword'],'ADMIN_EMAILS':'',
 'PROJECT_FOLDER':str(RUN/'uploads')+'/','PROJECT_DOMAIN':'http://127.0.0.2:16001','PROJECT_AUTO_CHECKPAY':'false',
 'ALIYUN_ACCESS_KEY_ID':'','ALIYUN_ACCESS_KEY_SECRET':'','ALIPAY_APPID':'','ALIPAY_APP_PRIVATE_KEY':'','BAIDU_AIP_ENABLED':'false',
 'AGENT_HOST':'127.0.0.1','AGENT_PORT':'17050','AGENT_BASE_URL':'http://127.0.0.1:17050',
 'JAVA_WEB_URL':'http://127.0.0.1:18080','MCP_SERVER_URL':'http://127.0.0.1:17060','FASTMCP_HOST':'127.0.0.1','FASTMCP_PORT':'17060',
 'WS_EXTRA_ALLOWED_HOSTS':'127.0.0.2',
 'ES_URIS':'http://127.0.0.1:19200','ES_HOSTS':'http://127.0.0.1:19200','ES_INDEX':p['vectorIndex'],'VECTOR_INDEX':p['vectorIndex'],
 'LLM_API_KEY':'quality34-local-proxy','LLM_BASE_URL':'http://127.0.0.1:19200/llm/v1','LLM_MODEL':'deepseek-flash','LLM_MAX_RETRIES':'0','LLM_TIMEOUT':'20','POLICY_LLM_TIMEOUT_SECONDS':'20',
 'EMBEDDING_API_KEY':'quality34-local-proxy','EMBEDDING_BASE_URL':'http://127.0.0.1:19200/embedding/v1','EMBEDDING_MODEL':'text-embedding-v4','EMBEDDING_DIMENSIONS':'1024',
 'MEMORY_LLM_API_KEY':'','MEMORY_LLM_BASE_URL':'http://127.0.0.1:19200/llm/v1','MEMORY_LLM_TIMEOUT':'20',
 'ASSISTANT_HISTORY_MAX_LEN':'100000','COMPRESS_TOKEN_THRESHOLD':'10000000','WORKING_TOKEN_BUDGET':'10000000',
 'SHOPPING_REQUIREMENT_LLM_ENABLED':'false','SHOPPING_DATA_MODE':'DEMO','INTENT_USE_LLM':'false','INTERNAL_READ_BACKEND':'http',
 'AGENT_REFUND_EXECUTION_ENABLED':'false','AFTERSALES_CASES_AUTO_CREATE':'false','GRAPH_CHECKPOINT_HMAC_SECRET':c['internalToken'],
 'GRAPH_CHECKPOINT_PREFIX':p['indexPrefix']+'checkpoint','CATALOGUE_SCHEMA':p['databases']['data_governance'],
 'SPRING_DATASOURCE_HIKARI_MAXIMUM_POOL_SIZE':'3','SPRING_DATASOURCE_HIKARI_MINIMUM_IDLE':'1','SERVER_TOMCAT_THREADS_MAX':'12','SERVER_TOMCAT_THREADS_MIN_SPARE':'2',
 'PYTHONPATH':str(ROOT/'Simlect-backend/Simlect-agent')+';'+str(ROOT),
 'QUALITY34_ROOT':str(ROOT),'QUALITY34_RUN':str(RUN)}
roles={}
for service in ['user','product','stock','order','search','admin','cart','gateway','mcp','agent']:
 env=dict(common)
 if service in c.get('serviceDbUsers',{}):
  env['MYSQL_USER']=c['serviceDbUsers'][service]['user']
  env['MYSQL_PASSWORD']=c['serviceDbUsers'][service]['password']
 env['SERVER_PORT']=str(p['ports'][service])
 if service not in {'gateway','mcp','agent'}:
  env['SPRING_DATASOURCE_URL']='jdbc:mysql://127.0.0.1:13306/'+p['databases'][service]+'?useUnicode=true&characterEncoding=utf-8&serverTimezone=Asia/Shanghai&allowPublicKeyRetrieval=true&useSSL=false&connectionAttributes=quality34_service:'+service
 if service in {'mcp','agent'}:
  env['MYSQL_DATABASE']=p['databases']['agent']
  if 'agent' in c.get('serviceDbUsers',{}):
   env['MYSQL_USER']=c['serviceDbUsers']['agent']['user'];env['MYSQL_PASSWORD']=c['serviceDbUsers']['agent']['password']
 if service=='order':
  env['SIMLECT_AFTERSALES_MOCK_REFUND_ENABLED']='true'
 roles[service]=env
roles['guard']={k:common[k] for k in ['PYTHONUTF8','PYTHONPATH','QUALITY34_ROOT','QUALITY34_RUN','TEMP','TMP']}
roles['web']={'VITE_DEV_PORT':'16001','VITE_API_PROXY_TARGET':'http://127.0.0.1:18080','VITE_AGENT_PROXY_TARGET':'http://127.0.0.1:17050','VITE_WS_PROXY_TARGET':'ws://127.0.0.1:17050','VITE_AGENT_CONVERSATIONS_ENABLED':'true'}
roles['admin-ui']={}
(RUN/'environment-private.json').write_text(json.dumps(roles,ensure_ascii=False),encoding='utf8')
(RUN/'browser-fixtures-private.json').write_text(json.dumps({'userEmail':p['emailA'],'userPassword':c['userPassword'],'adminAccount':c['adminAccount'],'adminPassword':c['adminPassword']}),encoding='utf8')
front=ROOT/'Simlect-front'
for service,folder in [('web','Simlect-web'),('admin-ui','Simlect-admin')]:
 config=(front/folder/('vite.config.ts' if service=='web' else 'vite.config.js')).as_uri()
 vite=(front/folder/'node_modules/vite/dist/node/index.js').as_uri()
 text=f"import original from {json.dumps(config)};\nimport {{defineConfig}} from {json.dumps(vite)};\n"
 if service=='web':
  text+="export default defineConfig(ctx=>{const c=original(ctx);return {...c,cacheDir:"+json.dumps(str(RUN/'web-vite-cache'))+",server:{...c.server,host:'127.0.0.2',port:16001,strictPort:true}};});\n"
 else:
  text+="export default defineConfig({...original,cacheDir:"+json.dumps(str(RUN/'admin-vite-cache'))+",server:{...original.server,host:'127.0.0.2',port:16002,strictPort:true,proxy:{'/admin-api':{target:'http://127.0.0.1:18080',changeOrigin:false},'/api':{target:'http://127.0.0.1:18080',changeOrigin:false,rewrite:p=>p.replace(/^\\/api/,'/admin-api')}}}});\n"
 (RUN/(service+'.vite.config.mjs')).write_text(text,encoding='utf8')
(RUN/'execution-plan.md').write_text('''# Stage34 execution plan
1. Back up formal schemas/digests and generate synthetic fixtures in least-privilege schemas.
2. Use a separate Redis container, RabbitMQ vhost/user, Nacos group, ports and browser host 127.0.0.2.
3. Route ES through an index allow-list guard; block paid calls until isolation is independently verified.
4. Build copied Java sources without overwriting running service JARs; start test services sequentially.
5. Validate actual datasource sessions, Redis clients, vhost permissions, registration group and ES targets.
6. Run browser user/admin return-confirm-review-logistics-acceptance-MOCK-refund workflow.
7. Enable a bounded real API phase only after readiness; stop on timeout, 429 or upstream 5xx.
8. Run regression/fault tests, compare formal digests and remove only recorded test resources.
No real funds, production writes, credential extraction, policy publication or Git commits.
''',encoding='utf8')
print('Isolated roles configured:',len(roles),'No credentials printed.')
