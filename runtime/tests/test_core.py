import sys
import json
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core.speech import srt_stamp,parse_stamp,read_srt,write_srt
from core.recap import clips_from_scenes,choose_clips,save_plan
from core.ai import AISettings
from core.editor import audit_rights

class TestLMK(unittest.TestCase):
    def test_srt_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'clip.srt'
            x=[{'start':.13,'end':4.89,'text':'Hello world'},{'start':6,'end':7.23,'text':'Chào bạn'}]
            write_srt(x,p);assert read_srt(p)==x
            assert srt_stamp(3600.999)=='01:00:00,999'
            assert parse_stamp('01:00:00,999')==3600.999
    def test_scene_order(self):
        scenes=[(i*5.,(i+1)*5.) for i in range(36)]
        trans=[{'start':i*5.,'end':i*5.+4.,'text':'Help! But why? What happened?' if i%3==0 else 'ok'} for i in range(36)]
        c=clips_from_scenes(scenes,trans,max_length=10.,min_length=3.)
        chosen=choose_clips(c,50)
        assert len(chosen)>=4
        assert all(a['start']<b['start'] for a,b in zip(chosen,chosen[1:]))
        assert chosen[0]['start']<40 and chosen[-1]['start']>90
    def test_no_fake_rights(self):
        r=audit_rights('video.mp4','Chưa xác minh',commentary=True)
        assert r['platform_clearance'].startswith('Chưa xác minh')
    def test_ai_policy(self):
        assert not AISettings().ready()
        try:AISettings('http://example.com/v1','test').chat('a','b')
        except Exception as e:assert 'HTTPS' in str(e)
        else:raise AssertionError('http external URL not blocked')

if __name__=='__main__':unittest.main()
