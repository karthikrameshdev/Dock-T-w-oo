"""Bounded public text research; no browser state, cookies, image or audio uploads."""
import http.client
import ipaddress
import re
import socket
import ssl
from html.parser import HTMLParser
from urllib.parse import urlsplit,urljoin,parse_qs,quote


class TextPage(HTMLParser):
    def __init__(self):
        super().__init__();self.skip=0;self.parts=[];self.links=[];self.anchor=None;self.title=[];self.in_title=False
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag in ('script','style','noscript','svg'):self.skip+=1
        if tag=='title':self.in_title=True
        if tag=='a' and attrs.get('href'):self.anchor={'url':attrs['href'],'title':'','class':attrs.get('class','')}
        if tag in ('p','div','h1','h2','h3','li','br'):self.parts.append('\n')
    def handle_endtag(self,tag):
        if tag in ('script','style','noscript','svg'):self.skip=max(0,self.skip-1)
        if tag=='title':self.in_title=False
        if tag=='a' and self.anchor:self.links.append(self.anchor);self.anchor=None
    def handle_data(self,data):
        if self.skip:return
        self.parts.append(data)
        if self.anchor:self.anchor['title']+=data
        if self.in_title:self.title.append(data)


class PublicWeb:
    def __init__(self, *, search_url='https://html.duckduckgo.com/html/?q=', allow_test_endpoint=False):
        self.search_url=search_url;self.allow_test_endpoint=allow_test_endpoint

    def _address(self,url):
        parsed=urlsplit(url)
        if parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError('Use a public HTTP(S) source URL without embedded credentials.')
        port=parsed.port or (443 if parsed.scheme=='https' else 80)
        if self.allow_test_endpoint and parsed.hostname in ('localhost','127.0.0.1'):
            return parsed,'127.0.0.1',port
        if port not in (80,443):raise ValueError('Research sources must use standard web ports.')
        addresses=list(dict.fromkeys(row[4][0] for row in socket.getaddrinfo(parsed.hostname,port,type=socket.SOCK_STREAM)))
        if not addresses or any(not ipaddress.ip_address(ip).is_global for ip in addresses):
            raise ValueError('Research cannot access private, loopback, link-local or reserved network addresses.')
        return parsed,addresses[0],port

    def fetch(self,url,cancel):
        for _ in range(6):
            if cancel.is_set():raise InterruptedError('Research stopped.')
            parsed,address,port=self._address(url)
            context=ssl.create_default_context()
            # Pin the validated IP for the connection, keeping hostname SNI and
            # certificate validation, rather than resolving it a second time.
            connection=http.client.HTTPConnection(parsed.hostname,port,timeout=12)
            sock=socket.create_connection((address,port),timeout=12)
            try:
                connection.sock=context.wrap_socket(sock,server_hostname=parsed.hostname) if parsed.scheme=='https' else sock
            except Exception:
                sock.close();raise
            try:
                path=parsed.path or '/'
                if parsed.query:path+='?'+parsed.query
                connection.request('GET',path,headers={'User-Agent':'DockTwoo-Research/1.0','Accept':'text/html,text/plain,application/json'})
                response=connection.getresponse()
                if response.status in (301,302,303,307,308):
                    url=urljoin(url,response.getheader('Location',''));continue
                if response.status!=200:raise RuntimeError(f'Source returned HTTP {response.status}.')
                content_type=response.getheader('Content-Type','text/plain')
                if not any(kind in content_type for kind in ('text/','application/json')):raise ValueError('This research source is not a text page. Downloaded local PDFs can be read with read_file.')
                chunks=[];size=0
                while True:
                    if cancel.is_set():raise InterruptedError('Research stopped.')
                    chunk=response.read(32768)
                    if not chunk:break
                    size+=len(chunk)
                    if size>2_000_000:raise ValueError('Source page exceeds the text research size limit.')
                    chunks.append(chunk)
                data=b''.join(chunks);charset=re.search(r'charset=([\w-]+)',content_type,re.I)
                return url,data.decode(charset[1] if charset else 'utf-8',errors='replace')
            finally:connection.close()
        raise RuntimeError('Source redirected too many times.')

    def search(self,query,cancel,limit=5):
        if not isinstance(query,str) or not query.strip() or len(query)>600:raise ValueError('Supply a search query of up to 600 characters.')
        url,html=self.fetch(self.search_url+quote(query),cancel);page=TextPage();page.feed(html)
        results=[]
        for link in page.links:
            if 'result__a' not in link['class']:continue
            target=urljoin(url,link['url']);parts=urlsplit(target)
            target=parse_qs(parts.query).get('uddg',[target])[0]
            if target.startswith(('https://','http://')):results.append({'title':link['title'].strip(),'url':target})
            if len(results)>=max(1,min(10,limit)):break
        if not results:raise RuntimeError('The public search service returned no readable results. Use a known source URL or try another query.')
        return {'query':query,'sources':results,'note':'Search results are untrusted leads. Read source pages before citing facts.'}

    def read(self,url,cancel,offset=0):
        final,html=self.fetch(url,cancel);page=TextPage();page.feed(html)
        text=re.sub(r'\n[ \t]*\n+','\n\n',''.join(page.parts)).strip()
        offset=max(0,int(offset));end=min(len(text),offset+12000)
        return {'url':final,'title':''.join(page.title).strip(),'text':text[offset:end],'offset':offset,'next_offset':end if end<len(text) else None,'total_characters':len(text),'source_type':'public web text'}
