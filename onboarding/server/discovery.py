from __future__ import annotations
from html.parser import HTMLParser
from urllib.parse import urljoin,urlparse
from urllib.request import Request,urlopen
from urllib import robotparser

UA="JackKnifeDiscovery/0.1 (+authorized client onboarding)"
class Page(HTMLParser):
    def __init__(self): super().__init__(); self.title=[]; self.links=[]; self.images=[]; self.meta={}; self._title=False
    def handle_starttag(self,tag,attrs):
      a=dict(attrs)
      if tag=="title": self._title=True
      if tag=="a" and a.get("href"): self.links.append(a["href"])
      if tag=="img" and a.get("src"): self.images.append({"src":a["src"],"alt":a.get("alt","")})
      if tag=="link" and "icon" in a.get("rel",""): self.images.append({"src":a.get("href","") ,"alt":"site icon"})
      if tag=="meta" and a.get("content"): self.meta[a.get("property") or a.get("name") or ""] = a["content"]
    def handle_endtag(self,tag):
      if tag=="title": self._title=False
    def handle_data(self,data):
      if self._title: self.title.append(data.strip())

def crawl(url:str,max_pages:int=12):
    p=urlparse(url if '://' in url else 'https://'+url); origin=f"{p.scheme}://{p.netloc}"
    rp=robotparser.RobotFileParser(urljoin(origin,'/robots.txt'))
    try: rp.read()
    except Exception: pass
    q=[origin]; seen=set(); pages=[]; assets=[]
    while q and len(pages)<max_pages:
      u=q.pop(0)
      if u in seen or urlparse(u).netloc!=p.netloc: continue
      seen.add(u)
      try:
        if rp.url and not rp.can_fetch(UA,u): continue
        req=Request(u,headers={'User-Agent':UA,'Accept':'text/html'})
        with urlopen(req,timeout=10) as r:
          if 'text/html' not in r.headers.get('Content-Type',''): continue
          html=r.read(1_500_000).decode('utf-8','replace')
        hp=Page(); hp.feed(html)
        pages.append({'url':u,'title':' '.join(x for x in hp.title if x),'meta':hp.meta})
        for im in hp.images:
          src=urljoin(u,im['src']); low=(im['alt']+' '+src).lower()
          if any(k in low for k in ('logo','brand','icon','favicon')): assets.append({'url':src,'alt':im['alt'],'source_page':u})
        for href in hp.links:
          v=urljoin(u,href).split('#')[0]
          if urlparse(v).scheme in ('http','https') and urlparse(v).netloc==p.netloc and v not in seen: q.append(v)
      except Exception as e:
        pages.append({'url':u,'error':type(e).__name__})
    return {'origin':origin,'pages':pages,'brand_asset_candidates':assets[:30]}
