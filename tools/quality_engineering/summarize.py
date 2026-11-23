from pathlib import Path
import json,re,xml.etree.ElementTree as ET
out=Path('.cache/quality-engineering-20261105')
def read(p):
 b=p.read_bytes();return b.decode('utf-16' if b.startswith((b'\xff\xfe',b'\xfe\xff')) else 'utf-8-sig',errors='replace')
text=read(out/'java-all.log')
rows=[dict(zip(('tests','failures','errors','skipped'),map(int,m[:4])),name=m[4]) for m in re.findall(r'Tests run: (\d+), Failures: (\d+), Errors: (\d+), Skipped: (\d+).* -- in ([^\r\n]+)',text)]
gates=json.loads(read(out/'gates.json')) if (out/'gates.json').exists() else []
summary={'gates':gates,'allGatesPassed':bool(gates) and all(g.get('exitCode')==0 for g in gates),'java':{'discovered':sum(r['tests'] for r in rows),'passed':sum(r['tests']-r['failures']-r['errors']-r['skipped'] for r in rows),'failed':sum(r['failures']+r['errors'] for r in rows),'skipped':sum(r['skipped'] for r in rows),'classes':rows}}
p=out/'python-all.xml'
if p.exists():
 suites=ET.parse(p).getroot().findall('.//testsuite');summary['python']={k:sum(int(s.get(k,0)) for s in suites) for k in ('tests','failures','errors','skipped')};summary['python']['passed']=summary['python']['tests']-summary['python']['failures']-summary['python']['errors']-summary['python']['skipped']
for app in ('web','admin'):
 s=read(out/f'{app}-tests.log');summary[app]={k:int(re.search(r'\b'+label+r' (\d+)',s)[1]) for k,label in [('passed','pass'),('failed','fail'),('skipped','skipped')]}
(out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8');print({k:({a:b for a,b in v.items() if a!='classes'} if isinstance(v,dict) else v) for k,v in summary.items()})
