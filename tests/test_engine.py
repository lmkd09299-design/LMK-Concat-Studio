import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from standalone.engine import (Clip, RecapError, condensed_transcript, normalize_clips,
                               read_srt, write_srt, media_duration, bundled_ffmpeg)
from standalone.gemini_auth import extract_json, GeminiError, google_only_env
from standalone.concat_bridge import locate_concat


class RecapUnitTests(unittest.TestCase):
    def test_srt_round_trip(self):
        cues=[{'start':1.2,'end':3.8,'text':'Hello world'},
              {'start':4,'end':8.25,'text':'Cảnh thứ hai'}]
        with tempfile.TemporaryDirectory() as d:
            file=Path(d)/'transcript.srt';write_srt(cues,file)
            self.assertEqual(read_srt(file),cues)

    def test_model_json_without_markdown(self):
        a=extract_json('```json\n{"title":"Hi","clips":[]}\n```')
        self.assertEqual(a['title'],'Hi')
        with self.assertRaises(GeminiError):extract_json('no JSON here')

    def test_validate_clips_time_and_order(self):
        source={'clips':[{'start':19,'end':50,'narration':'B'},
                         {'start':5,'end':15,'narration':'A'},
                         {'start':14,'end':24,'narration':'C'},
                         {'start':150,'end':200,'narration':'wrong'}]}
        result=normalize_clips(source,40,40)
        self.assertEqual(result[0].start,5)
        self.assertLessEqual(sum(x.duration for x in result),40.01)
        self.assertTrue(all(a.end<=b.start for a,b in zip(result,result[1:])))
        with self.assertRaises(RecapError):normalize_clips({'clips':[]},50,40)

    def test_sample_long_transcript_includes_last(self):
        cues=[{'start':i*10,'end':i*10+8,'text':f'line {i}'} for i in range(900)]
        condensed=condensed_transcript(cues)
        self.assertIn('line 0',condensed)
        self.assertIn('line 898',condensed)
        self.assertLess(len(condensed),47001)

    def test_no_gemini_keys_in_environment(self):
        with patch.dict('os.environ',{'GEMINI_API_KEY':'secret','GOOGLE_API_KEY':'other'},clear=False):
            sanitized=google_only_env()
            self.assertNotIn('GEMINI_API_KEY',sanitized)
            self.assertNotIn('GOOGLE_API_KEY',sanitized)

    def test_ffmpeg_bundled_smoke_if_available(self):
        try: exe=bundled_ffmpeg()
        except RecapError: return
        with tempfile.TemporaryDirectory() as d:
            file=Path(d)/'sample.mp4'
            import subprocess
            p=subprocess.run([exe,'-hide_banner','-loglevel','error','-y','-f','lavfi',
                              '-i','color=c=black:s=320x180:r=25:d=2',
                              '-c:v','mpeg4',str(file)],capture_output=True)
            if p.returncode: self.skipTest('FFmpeg binary lacks lavfi encoder')
            self.assertGreater(media_duration(file,exe),1.8)

if __name__ == '__main__': unittest.main()
