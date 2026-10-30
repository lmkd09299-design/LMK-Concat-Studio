import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from standalone.engine import (Config, bundled_ffmpeg, make_recap, media_duration, run, write_srt)


class FullVideoPipelineTests(unittest.TestCase):
    def test_real_video_render_with_mock_ai_and_voice(self):
        try:
            ffmpeg=bundled_ffmpeg()
        except Exception:
            self.skipTest('FFmpeg not available')
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            video=root/'movie.mp4'
            run([ffmpeg,'-loglevel','error','-y','-f','lavfi',
                 '-i','testsrc2=size=320x180:rate=25:duration=24',
                 '-c:v','mpeg4',str(video)])
            srt=root/'sub.srt'
            write_srt([{'start':2,'end':8,'text':'A door appears.'},
                       {'start':10,'end':16,'text':'They open the door.'},
                       {'start':17,'end':22,'text':'A surprise appears.'}],srt)
            def fake_voice(text,out,language,status):
                run([ffmpeg,'-loglevel','error','-y','-f','lavfi',
                     '-i','sine=frequency=440:duration=5','-c:a','libmp3lame',str(out)])
            ai={'title':'Mystery','summary':'A door appears unexpectedly.',
                'clips':[{'start':2,'end':8,'narration':'Someone finds a door.'},
                         {'start':10,'end':16,'narration':'The hidden room is opened.'}]}
            with patch('standalone.engine.ask_gemini',return_value=ai),\
                 patch('standalone.engine.synthesize_voice',side_effect=fake_voice):
                result=make_recap(Config(video,root/'exports',1,'English',srt=srt),lambda _:None)
            self.assertTrue(Path(result['output']).is_file())
            self.assertTrue(Path(result['plan']).is_file())
            self.assertEqual(result['clips'],2)
            self.assertGreater(media_duration(Path(result['output']),ffmpeg),8.0)

if __name__ == '__main__':unittest.main()
