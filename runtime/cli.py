"""Scriptable interface. Example: python cli.py recap --input movie.mp4 --srt movie.srt --out output"""
import argparse,json,sys,os
from core.ai import AISettings
from core.oxion_keys import is_oxion, load as load_oxion_key, store as save_oxion_key
from core.editor import build_edited_video
from core.recap import build_recap
from core.rights import audit_and_transform
from core.media import MediaError, remux_voice, probe
from pathlib import Path

def main():
    p=argparse.ArgumentParser(description='LMK Video Studio CLI')
    p.add_argument('mode',choices=['edit','recap','rights','mix']);p.add_argument('--input',required=True)
    p.add_argument('--srt',default='');p.add_argument('--out',required=True)
    p.add_argument('--aspect',default='9:16',choices=['9:16','16:9','1:1'])
    p.add_argument('--api-url',default=os.environ.get('LMK_AI_BASE_URL',''));p.add_argument('--api-model',default=os.environ.get('LMK_AI_MODEL',''))
    p.add_argument('--api-key-env',default='LMK_AI_KEY')
    p.add_argument('--language',default='Giữ nguyên');p.add_argument('--model',default='tiny')
    p.add_argument('--voice',action='store_true');p.add_argument('--voice-name',default='vi-VN-HoaiMyNeural')
    p.add_argument('--tts',default='edge',choices=['edge','system'])
    p.add_argument('--minutes',type=int,default=3);p.add_argument('--burn-subs',action='store_true')
    p.add_argument('--rights',default='Chưa xác minh');p.add_argument('--commentary',action='store_true')
    p.add_argument('--analysis-file',default='',help='UTF-8 text file containing original commentary')
    p.add_argument('--mute-original',action='store_true',help='Mute the source audio and music')
    p.add_argument('--threshold',type=float,default=.30)
    p.add_argument('--voice-file',default='')
    p.add_argument('--no-ai',action='store_true')
    p.add_argument('--remember-oxion-key',action='store_true',help='Encrypt entered Oxion API key for this Windows user')
    p.add_argument('--replacement-audio',default='')
    p.add_argument('--license-note',default='')
    a=p.parse_args()
    # Select a voice in the recap target language unless CLI explicitly
    # overrides the voice. UI uses default voice-name, not a voice picker.
    if a.mode == 'recap' and '--voice-name' not in sys.argv:
        a.voice_name = {
            'English': 'en-US-AriaNeural',
            'Thai': 'th-TH-PremwadeeNeural',
            'Tiếng Việt': 'vi-VN-HoaiMyNeural',
        }.get(a.language, a.voice_name)
    key = os.environ.get(a.api_key_env,'')
    try:
        if a.mode == 'recap' and not a.no_ai and is_oxion(a.api_url):
            if key and a.remember_oxion_key:
                save_oxion_key(key)
            if not key:
                key = load_oxion_key()
        ai=AISettings() if a.no_ai else AISettings(a.api_url,a.api_model,key)
    except MediaError as e:
        print('FAILED:', e, file=sys.stderr)
        return 2
    try:
        if a.mode == 'mix':
            if not a.voice_file:
                raise MediaError('Missing --voice-file for native Concat voice')
            directory=Path(a.out).expanduser().resolve()
            directory.mkdir(parents=True,exist_ok=True)
            merged=remux_voice(Path(a.input),Path(a.voice_file),
                               directory/'recap_concat_voice.mp4')
            report_path=directory/'report.json'
            report=json.loads(report_path.read_text(encoding='utf-8'))
            report['output']=str(merged)
            report['output_duration']=probe(merged)['duration']
            report['voice_engine']='concat-native'
            report_path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
            r=report
        elif a.mode=='rights':
            r=audit_and_transform(a.input,a.out,license_status=a.rights,
                replacement_audio=a.replacement_audio,license_note=a.license_note,
                remove_original=a.mute_original,progress=print)
        elif a.mode=='recap':
            r=build_recap(a.input,a.out,srt_path=a.srt,ai=ai,target_minutes=a.minutes,
                          language=a.language if a.language!='Giữ nguyên' else 'Tiếng Việt',
                          aspect=a.aspect,scene_threshold=a.threshold,model=a.model,
                          voice=a.voice,voice_name=a.voice_name,voice_engine=a.tts,progress=print)
        else:
            r=build_edited_video(a.input,a.out,srt_path=a.srt,ai=ai,asr_model=a.model,
               aspect=a.aspect,language=a.language,dubbing=a.voice,burn_subs=a.burn_subs,
               voice_name=a.voice_name,voice_engine=a.tts,rights_status=a.rights,
               analysis_text=(__import__('pathlib').Path(a.analysis_file).read_text(encoding='utf-8-sig') if a.analysis_file else ''),
               mute_original=a.mute_original,progress=print)
        print(json.dumps(r,ensure_ascii=False,indent=2));return 0
    except (MediaError,ValueError) as e:print('FAILED:',e,file=sys.stderr);return 2

if __name__=='__main__':raise SystemExit(main())
