"""Official HTML preview only; never publishes, embeds or writes a database."""
import hashlib,json,re,uuid
from html.parser import HTMLParser
from pathlib import Path

class ArticleBody(HTMLParser):
 def __init__(self):
  super().__init__(convert_charrefs=True);self.depth=0;self.parts=[];self.finished=False
 def handle_starttag(self,tag,attrs):
  if self.finished:return
  if not self.depth:
   if dict(attrs).get('id')=='UCAP-CONTENT':self.depth=1
  elif tag not in {'br','img','meta','link','input','hr'}:self.depth+=1
 def handle_endtag(self,tag):
  if self.depth:
   if tag in {'p','div','h1','h2'}:self.parts.append('\n')
   self.depth-=1
   if not self.depth:self.finished=True
 def handle_data(self,data):
  if self.depth:self.parts.append(data)

def prepare(path,url):
 raw=Path(path).read_bytes();parser=ArticleBody();parser.feed(raw.decode('utf8'))
 if not parser.finished:raise ValueError('OFFICIAL_BODY_NOT_FOUND')
 text='\n'.join(line.strip() for line in ''.join(parser.parts).splitlines() if line.strip())
 positions=list(re.finditer(r'(?m)^第[一二三四五六七八九十百]+条',text))
 chunks=[{'article':m[0],'text':text[m.start():positions[i+1].start() if i+1<len(positions) else len(text)].strip()} for i,m in enumerate(positions)]
 if not chunks:raise ValueError('NO_ARTICLES')
 return {'state':'LOCAL_PREVIEW_NOT_IMPORTED','officialUrl':url,'sha256':hashlib.sha256(raw).hexdigest(),'versionReview':'2020修订文本；当前有效状态仍待官方目录核验','text':text,'articles':chunks}
