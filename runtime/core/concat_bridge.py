"""Real Concat MCP integration. Imports rendered clips into an editable project.

Uses Concat --mcp headless as documented by jub0t/Concat (AGPL-3.0).
It never edits the user's already-open Concat project.
"""
from __future__ import annotations
import json
import os
import queue
import subprocess
import threading
from pathlib import Path
from .media import MediaError, probe

class ConcatMCP:
    def __init__(self,exe:str,allowed:Path):
        self.exe=exe;self.allowed=str(allowed);self.p=None;self.seq=0
        self.results=queue.Queue()
    def __enter__(self):
        env=os.environ.copy();env['CONCAT_MCP_ROOTS']=str(self.allowed)
        self.p=subprocess.Popen([self.exe,'--mcp','headless'],stdin=subprocess.PIPE,
          stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,encoding='utf-8',
          bufsize=1,env=env,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        def reader():
            try:
                for line in self.p.stdout:
                    try:self.results.put(json.loads(line))
                    except json.JSONDecodeError:continue
            finally:self.results.put({'_eof':True})
        threading.Thread(target=reader,daemon=True).start()
        self.ask('initialize',{'protocolVersion':'2025-06-18','capabilities':{},
                  'clientInfo':{'name':'LMK Video Studio','version':'1.0'}})
        self.send({'jsonrpc':'2.0','method':'notifications/initialized'})
        return self
    def send(self,payload):
        if not self.p or not self.p.stdin:raise MediaError('MCP đã đóng')
        self.p.stdin.write(json.dumps(payload,ensure_ascii=False)+'\n');self.p.stdin.flush()
    def ask(self,method,params):
        self.seq+=1;target=self.seq
        self.send({'jsonrpc':'2.0','id':target,'method':method,'params':params})
        while True:
            try:r=self.results.get(timeout=90)
            except queue.Empty:raise MediaError('Concat không phản hồi sau 90 giây.')
            if '_eof' in r:raise MediaError('Concat MCP đã ngắt kết nối.')
            if r.get('id')==target:
                if 'error' in r:raise MediaError('Concat MCP: '+str(r['error']))
                return r.get('result',{})
    def tool(self,name,args):
        r=self.ask('tools/call',{'name':name,'arguments':args})
        if r.get('isError'):raise MediaError(f'Concat {name}: '+str(r.get('content',[]))[:700])
        return r.get('structuredContent',{})
    def __exit__(self,*exc):
        if self.p:
            try:self.p.stdin.close()
            except Exception:pass
            try:self.p.wait(timeout=3)
            except subprocess.TimeoutExpired:self.p.kill();self.p.wait()

def create_editable_project(exe:str,clip_paths:list[str],project_parent:str,name='LMK_Recap',progress=None)->Path:
    if not clip_paths:raise MediaError('Chưa có clip để nhập Concat')
    base=Path(project_parent).expanduser().resolve();base.mkdir(parents=True,exist_ok=True)
    for p in clip_paths:
        if not Path(p).is_file():raise MediaError('Thiếu clip '+p)
    dest=base/name
    if dest.exists():raise MediaError('Project đã tồn tại, hãy đổi tên hoặc chuyển thư mục.')
    log=progress or (lambda s:None)
    # MCP grants access to the chosen output root and each source clip directory.
    roots=os.pathsep.join(sorted({str(base),*(str(Path(p).resolve().parent) for p in clip_paths)}))
    first=probe(clip_paths[0])
    with ConcatMCP(exe,roots) as client:
        # Concat headless accepts multiple folders through CONCAT_MCP_ROOTS.
        client.tool('project_create',{'location':str(base),'name':name,
             'video':{'width':int(first['width']),'height':int(first['height']),'rateNum':25,'rateDen':1}})
        ids=[]
        for i,path in enumerate(clip_paths,1):
            resp=client.tool('media_import',{'path':str(dest),'file':str(Path(path).resolve())})
            mid=resp.get('createdId')
            if not mid:raise MediaError(f'Concat không trả mediaId cho clip {i}: '+str(resp)[:400])
            ids.append(mid);log(f'Concat nhập clip {i}/{len(clip_paths)}')
        client.tool('clips_add_sequence',{'path':str(dest),'mediaIds':ids,'start':0.})
        client.tool('project_save',{'path':str(dest)})
    return dest
