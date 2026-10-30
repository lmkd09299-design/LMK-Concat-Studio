"""MCP bridge to unmodified Concat.exe. Creates a NEW project, never changes a live edit."""
from __future__ import annotations
import json
import os
import subprocess
from pathlib import Path


class ConcatError(RuntimeError):
    pass


def locate_concat() -> Path | None:
    roots = [Path(os.environ.get('LOCALAPPDATA', '')) / 'Programs' / 'Concat' / 'concat.exe',
             Path(os.environ.get('PROGRAMFILES', 'C:/Program Files')) / 'Concat' / 'concat.exe']
    return next((x for x in roots if x.is_file()), None)


class ConcatMCP:
    def __init__(self, exe: Path):
        self.exe = Path(exe)
        self.process = None
        self.next_id = 0
        self.tools = set()

    def __enter__(self):
        if not self.exe.is_file():
            raise ConcatError('Không tìm thấy Concat.exe: ' + str(self.exe))
        self.process = subprocess.Popen([str(self.exe), '--mcp', 'headless'],
                        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                        stderr=subprocess.DEVNULL, bufsize=1, text=True,
                        encoding='utf-8', errors='replace')
        self.send('initialize', {'protocolVersion':'2025-11-25','capabilities':{},
                                  'clientInfo':{'name':'LMK Recap Bridge','version':'1.0'}})
        self._write({'jsonrpc':'2.0','method':'notifications/initialized','params':{}})
        catalog = self.send('tools/list', {})
        self.tools = {t['name'] for t in catalog['tools']}
        return self

    def __exit__(self, *_):
        if self.process:
            try:
                self.process.stdin.close()
                self.process.wait(timeout=5)
            except (OSError, subprocess.TimeoutExpired):
                self.process.kill()
                self.process.wait(timeout=5)
            self.process = None

    def _write(self, data: dict):
        self.process.stdin.write(json.dumps(data, ensure_ascii=False) + '\n')
        self.process.stdin.flush()

    def send(self, method: str, params: dict):
        self.next_id += 1
        self._write({'jsonrpc':'2.0','id':self.next_id,'method':method,'params':params})
        while True:
            line = self.process.stdout.readline()
            if not line:
                raise ConcatError('Concat MCP dừng đột ngột; hãy kiểm tra phiên bản Concat và Automation.')
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            if data.get('id') != self.next_id:
                continue  # Ignore progress notifications unrelated to this command.
            if 'error' in data:
                raise ConcatError(method + ': ' + str(data['error']))
            return data.get('result', {})

    def call(self, tool: str, args: dict) -> dict:
        if tool not in self.tools:
            raise ConcatError(f'Concat bản này thiếu MCP tool {tool}.')
        result = self.send('tools/call', {'name':tool,'arguments':args})
        if result.get('isError'):
            raise ConcatError(tool + ': ' + str(result.get('content', []))[:800])
        content = result.get('structuredContent')
        if isinstance(content, dict):
            return content
        snippets = [x.get('text','') for x in result.get('content', []) if x.get('type')=='text']
        if not snippets:
            return result
        try:
            return json.loads(snippets[0])
        except json.JSONDecodeError:
            return {'text': '\n'.join(snippets)}


def prepare_concat_project(exe: Path, movie: Path, out_dir: Path, title: str) -> Path:
    """Create an editable Concat project holding the generated recap MP4.

    Concat MCP cannot operate on a project already open in its GUI. It makes
    an isolated project that the user may open in the normal Concat window.
    """
    root = out_dir / 'Concat-Projects'
    root.mkdir(parents=True, exist_ok=True)
    name = ''.join(ch if ch.isalnum() or ch in ' -_' else '-' for ch in title)[:65].strip() or 'LMK Recap'
    candidate = name
    n = 2
    while (root / candidate).exists():
        candidate = f'{name}-{n}'
        n += 1
    folder = root / candidate
    with ConcatMCP(exe) as mcp:
        mcp.call('concat_version', {})
        mcp.call('project_create', {'location':str(root), 'name':candidate})
        imported = mcp.call('media_import', {'path':str(folder), 'file':str(movie)})
        media_id = imported.get('createdId')
        if not media_id:
            raise ConcatError('Concat import thành công nhưng không trả media ID: ' + str(imported)[:500])
        timeline = mcp.call('timeline_read', {'path':str(folder)})
        tracks = timeline.get('tracks', [])
        track_id = tracks[0].get('id') if tracks else None
        args = {'path':str(folder),'mediaId':media_id,'start':0.0}
        if track_id is not None:
            args['trackId'] = track_id
        mcp.call('clip_add', args)
        mcp.call('project_save', {'path':str(folder)})
        mcp.call('project_close', {'path':str(folder),'save':True})
    return folder
