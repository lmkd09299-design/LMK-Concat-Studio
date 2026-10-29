"""Scriptable interface. Example: python cli.py recap --input movie.mp4 --srt movie.srt --out output"""
import argparse,json,sys,os
from core.ai import AISettings
from core.editor import build_edited_video
from core.recap import build_recap
from core.rights import audit_and_transform
from core.media import MediaError

def main():
    p=argparse.ArgumentParser(description='LMK Video Studio CLI')
    p.add_argument('mode',choices=['edit','recap','rights']);p.add_argument('--input',required=True)
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
    ai=AISettings(a.api_url,a.api_model,os.environ.get(a.api_key_env,''))
    try:
        if a.mode=='rights':
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
