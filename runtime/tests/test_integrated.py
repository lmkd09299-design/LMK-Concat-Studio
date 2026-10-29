"""Run without Concat itself; official Concat executable is a Windows installer task."""
from __future__ import annotations
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.concat_install import find_concat
from core.concat_bridge import create_editable_project
from core.media import binary, probe

ROOT = Path(__file__).resolve().parents[1]

class TestIntegrated(unittest.TestCase):
    def test_find_concat_override(self):
        with tempfile.TemporaryDirectory() as temp:
            exe = Path(temp) / 'concat.exe'
            exe.write_bytes(b'fake exe')
            self.assertEqual(find_concat(str(exe)), str(exe.resolve()))

    def test_concat_env_override(self):
        with tempfile.TemporaryDirectory() as temp:
            exe = Path(temp) / 'concat.exe'
            exe.write_bytes(b'fake exe')
            with patch.dict(os.environ, {'LMK_CONCAT_EXE': str(exe)}):
                self.assertEqual(find_concat(), str(exe.resolve()))

    def test_video_fixture(self):
        self.assertTrue(Path(binary('ffprobe')).is_file())
        self.assertGreater(probe(ROOT / 'fixtures' / 'sample.mp4')['duration'], 5)

    @unittest.skipIf(os.name == 'nt', 'Mock Concat executable is POSIX-only')
    def test_mcp_compatibility_without_vendor_binary(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            fake = base / 'fake_concat'
            fake.write_text('#!' + sys.executable + '\n' + '''import json, sys
from pathlib import Path
created = ''
for line in sys.stdin:
    req = json.loads(line)
    method = req.get('method')
    if 'id' not in req: continue
    result = {}
    if method == 'tools/call':
        tool = req['params']['name']; args = req['params']['arguments']
        if tool == 'project_create':
            created = str(Path(args['location']) / args['name'])
            Path(created).mkdir()
        elif tool == 'media_import':
            result = {'createdId': 'm' + str(len(list(Path(created).glob('*.index'))) + 1)}
            (Path(created) / (result['createdId'] + '.index')).write_text(args['file'])
        elif tool == 'project_save':
            (Path(created) / 'concat.json').write_text('{"saved":true}')
        result = {'isError': False, 'structuredContent': result}
    print(json.dumps({'jsonrpc':'2.0','id':req['id'],'result':result}), flush=True)
''', encoding='utf-8')
            fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
            dest = create_editable_project(str(fake),
                [str(ROOT / 'fixtures' / 'sample.mp4')], str(base), name='Cut')
            self.assertTrue((dest / 'concat.json').exists())

if __name__ == '__main__': unittest.main()
