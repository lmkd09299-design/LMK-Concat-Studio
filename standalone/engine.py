"""End-to-end, consent-based movie recap; Gemini CLI uses Google OAuth, not API keys."""
from __future__ import annotations
import json
import math
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .gemini_auth import ask_gemini, GeminiError
from .concat_bridge import prepare_concat_project, ConcatError


class RecapError(RuntimeError):
    pass


@dataclass
class Clip:
    start: float
    end: float
    narration: str

    @property
    def duration(self) -> float:
        return self.end - self.start


def bundled_ffmpeg() -> str:
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except (ImportError, RuntimeError, OSError):
        exe = shutil.which('ffmpeg')
        if not exe:
            raise RecapError('Không tìm được FFmpeg, bản EXE phải đóng gói imageio-ffmpeg.')
        return exe


def run(cmd: list[str], *, timeout: int = 900) -> str:
    try:
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           text=True, encoding='utf-8', errors='replace', timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RecapError(f'Lỗi thực thi hoặc quá giờ: {cmd[0]} ({exc})') from exc
    if p.returncode:
        raise RecapError('Xử lý video thất bại: ' + p.stderr[-1100:])
    return p.stdout + '\n' + p.stderr


def media_duration(video: Path, ffmpeg: str) -> float:
    # FFmpeg prints input metadata on stderr and exits 1 without an output.
    p = subprocess.run([ffmpeg, '-hide_banner', '-i', str(video)],
                       capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=45)
    m = re.search(r'Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)', p.stderr)
    if not m:
        raise RecapError('Không đọc được thời lượng video bằng FFmpeg.')
    return int(m[1])*3600 + int(m[2])*60 + float(m[3])


def read_srt(file: Path) -> list[dict]:
    raw = file.read_text(encoding='utf-8-sig', errors='replace').replace('\r\n','\n')
    cues = []
    pattern = re.compile(r'(\d\d:\d\d:\d\d[,\.]\d+)\s*-->\s*(\d\d:\d\d:\d\d[,\.]\d+)[^\n]*\n([^\n]*(?:\n(?!\n)[^\n]*)*)', re.M)
    def seconds(t):
        h,m,s = t.replace(',','.').split(':')
        return int(h)*3600 + int(m)*60 + float(s)
    for hit in pattern.finditer(raw):
        text = re.sub(r'<[^>]+>', '', hit.group(3)).strip().replace('\n',' ')
        if text:
            cues.append({'start':seconds(hit.group(1)), 'end':seconds(hit.group(2)), 'text':text})
    if not cues:
        raise RecapError('SRT không có timecode/phụ đề hợp lệ.')
    return cues


def write_srt(cues: list[dict], path: Path):
    def stamp(v):
        total = round(v*1000)
        hour,rem = divmod(total,3600000)
        minute,rem = divmod(rem,60000)
        second,ms = divmod(rem,1000)
        return f'{hour:02}:{minute:02}:{second:02},{ms:03}'
    path.write_text('\n\n'.join(f'{i}\n{stamp(v["start"])} --> {stamp(v["end"])}\n{v["text"]}'
                                for i,v in enumerate(cues,1))+'\n', encoding='utf-8')


def transcript_video(video: Path, model: str, status: Callable[[str],None]) -> list[dict]:
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RecapError('Bản đóng gói thiếu faster-whisper.') from exc
    status('Whisper tải model nếu chưa có; phân tích lời thoại bằng CPU...')
    engine = WhisperModel(model, device='cpu', compute_type='int8', num_workers=2)
    segments,_ = engine.transcribe(str(video), beam_size=2, vad_filter=True)
    return [{'start':float(s.start),'end':float(s.end),'text':s.text.strip()}
            for s in segments if s.text.strip()]


def condensed_transcript(cues: list[dict], limit: int = 47000) -> str:
    # Cover *the entire movie*, not just the first part.
    if not cues:
        raise RecapError('Phim không có phụ đề hoặc lời thoại để phân tích.')
    per_item = max(1, math.ceil(len(cues)/min(700,len(cues))))
    rows=[f"[{int(x['start'])}-{int(x['end'])}s] {x['text'][:160]}"
          for x in cues[::per_item]]
    joined='\n'.join(rows)
    if len(joined) > limit:
        # Uniformly sample again while retaining chronological coverage.
        step=math.ceil(len(joined)/limit)
        joined='\n'.join(rows[::step])
    return joined


GEMINI_PROMPT = '''You are a meticulous documentary-style film recap editor. The user's transcript arrives on stdin, every segment tagged with original-movie timestamps. Create a completely ORIGINAL commentary-based recap plan in JSON, with no introductory text and no markdown.
Required JSON object exactly: {"title":"...","summary":"...","clips":[{"start":0.0,"end":12.5,"narration":"..."}]}
Select shots that tell a coherent chronological plot including opening, conflict, turning point and resolution ONLY IF supported by transcript. Select 8 to 45 clips, each 4 to 30 seconds, chronological and non-overlapping. Sum their durations to about TARGET_SECONDS seconds. Write original narration per clip, max 18 words; narrator must describe and interpret, not reproduce long dialogue. Prefer precise timestamps from the transcript. Never invent scenes, character identities or events. If missing context, be explicit. Output language is LANGUAGE. This is a user-supplied film with independently verified editing rights. TARGET_SECONDS=SECONDS; LANGUAGE=LANGUAGE. Do not run tools or change files, only reply with JSON.'''


def normalize_clips(payload: dict, movie_seconds: float, target_seconds: int) -> list[Clip]:
    raw=payload.get('clips')
    if not isinstance(raw,list) or not raw:
        raise RecapError('Gemini chưa trả danh sách clips/timecode hợp lệ.')
    clean=[]
    for item in raw[:80]:
        if not isinstance(item,dict):
            continue
        try:
            a,b = float(item['start']), float(item['end'])
        except (ValueError,TypeError,KeyError):
            continue
        narration=str(item.get('narration','')).strip()
        if not narration or not math.isfinite(a) or not math.isfinite(b):
            continue
        a=max(0,a); b=min(movie_seconds,b)
        if b-a>=2.5:
            clean.append(Clip(round(a,2),round(b,2),narration[:500]))
    clean.sort(key=lambda x:x.start)
    result=[]
    right=-1.0
    for x in clean:
        if x.start<right:
            if x.end-right<2.5:continue
            x=Clip(right,x.end,x.narration)
        if x.duration>30:
            x=Clip(x.start,x.start+30,x.narration)
        right=x.end
        result.append(x)
    if not result:
        raise RecapError('Gemini trả các mốc thời gian không nằm trong phim.')
    # Preserve chronological coverage but cap total output length, with no fabricated clips.
    remaining=target_seconds
    capped=[]
    for clip in result:
        duration=min(clip.duration,remaining)
        if duration<2.5:break
        capped.append(Clip(clip.start,clip.start+duration,clip.narration))
        remaining-=duration
        if remaining<=0:break
    if not capped:
        raise RecapError('Không đủ cảnh hợp lệ để dựng.')
    return capped


def render_segments(source: Path, clips: list[Clip], folder: Path,
                    portrait: bool, ffmpeg: str, status: Callable[[str],None]) -> Path:
    parts=[]
    filt = ('scale=720:1280:force_original_aspect_ratio=decrease,'
            'pad=720:1280:(ow-iw)/2:(oh-ih)/2,fps=25,format=yuv420p' if portrait else
            'scale=1280:720:force_original_aspect_ratio=decrease,'
            'pad=1280:720:(ow-iw)/2:(oh-ih)/2,fps=25,format=yuv420p')
    for i,clip in enumerate(clips,1):
        part=folder/f'clip_{i:03}.mp4'
        args=[ffmpeg,'-hide_banner','-loglevel','error','-y','-ss',str(clip.start),
              '-i',str(source),'-t',str(round(clip.duration,3)),
              '-vf',filt,'-an','-c:v','libx264','-preset','veryfast','-crf','24',
              '-pix_fmt','yuv420p','-movflags','+faststart',str(part)]
        run(args,timeout=900)
        parts.append(part)
        status(f'Đã dựng cảnh {i}/{len(clips)}')
    concat_file=folder/'concat.txt'
    concat_file.write_text(''.join('file '+repr(p.as_posix())+'\n' for p in parts),encoding='utf-8')
    assembled=folder/'visual.mp4'
    run([ffmpeg,'-hide_banner','-loglevel','error','-y','-f','concat','-safe','0',
         '-i',str(concat_file),'-c','copy',str(assembled)],timeout=900)
    return assembled


def synthesize_voice(text: str, out: Path, language: str, status: Callable[[str],None]):
    try:
        import asyncio
        import edge_tts
    except ImportError as exc:
        raise RecapError('Bản đóng gói thiếu edge-tts.') from exc
    voice={'English':'en-US-AriaNeural','Tiếng Việt':'vi-VN-HoaiMyNeural'}.get(language,'en-US-AriaNeural')
    status('Đang tạo thuyết minh bằng Edge TTS (không cần API key)...')
    async def create():
        await edge_tts.Communicate(text,voice).save(str(out))
    asyncio.run(create())
    if not out.is_file() or out.stat().st_size<1000:
        raise RecapError('Không tạo được âm thanh thuyết minh.')


def combine_voice(visual: Path, voice: Path, target: Path, ffmpeg: str):
    video_seconds=media_duration(visual,ffmpeg)
    audio_seconds=media_duration(voice,ffmpeg)
    # Freeze the last frame if narration is longer; never cut off spoken sentences.
    padding=max(0, math.ceil(audio_seconds-video_seconds)+1)
    args=[ffmpeg,'-hide_banner','-loglevel','error','-y','-i',str(visual),'-i',str(voice),
          '-vf',f'tpad=stop_mode=clone:stop_duration={padding}',
          '-map','0:v:0','-map','1:a:0','-c:v','libx264','-preset','veryfast',
          '-crf','23','-af','apad','-c:a','aac','-b:a','160k',
          '-t',str(round(max(video_seconds,audio_seconds),3)),
          '-movflags','+faststart',str(target)]
    run(args,timeout=1200)


@dataclass
class Config:
    source: Path
    output_root: Path
    minutes: int
    language: str
    srt: Path | None = None
    portrait: bool = False
    whisper_model: str = 'tiny'
    concat_exe: Path | None = None
    send_to_concat: bool = False


def make_recap(config: Config, status: Callable[[str],None]) -> dict:
    source=config.source.expanduser().resolve()
    if not source.is_file():
        raise RecapError('Chưa chọn video gốc hợp lệ.')
    if config.minutes not in (1,3,5,8,10):
        raise RecapError('Thời lượng recap phải là 1, 3, 5, 8 hoặc 10 phút.')
    if config.language not in ('English','Tiếng Việt'):
        raise RecapError('Ngôn ngữ chưa được hỗ trợ.')
    ffmpeg=bundled_ffmpeg()
    duration=media_duration(source,ffmpeg)
    if duration<20:
        raise RecapError('Video nguồn quá ngắn (cần ít nhất 20 giây).')
    if config.srt:
        cues=read_srt(config.srt)
    else:
        cues=transcript_video(source,config.whisper_model,status)
    if not cues:
        raise RecapError('Không nhận diện được lời thoại phim.')
    root=config.output_root.expanduser().resolve()
    root.mkdir(parents=True,exist_ok=True)
    from datetime import datetime
    folder=root/('Recap-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
    folder.mkdir(parents=True,exist_ok=False)
    write_srt(cues,folder/'transcript.srt')
    status('Đang gửi transcript cho Gemini CLI (Google login)...')
    prompt=GEMINI_PROMPT.replace('SECONDS',str(config.minutes*60)).replace('LANGUAGE',config.language)
    draft=ask_gemini(prompt,condensed_transcript(cues),folder)
    clips=normalize_clips(draft,duration,config.minutes*60)
    (folder/'scene_plan.json').write_text(json.dumps({'title':draft.get('title'),
      'summary':draft.get('summary'),'source':str(source),
      'clips':[vars(x) for x in clips]},ensure_ascii=False,indent=2),encoding='utf-8')
    (folder/'kich_ban.txt').write_text(str(draft.get('summary',''))+'\n\n'+
      '\n'.join(x.narration for x in clips),encoding='utf-8')
    visual=render_segments(source,clips,folder,config.portrait,ffmpeg,status)
    narration=' '.join(x.narration for x in clips)
    mp3=folder/'voice.mp3'
    synthesize_voice(narration,mp3,config.language,status)
    output=folder/'LMK-RECAP.mp4'
    status('Đang ghép voice vào video...')
    combine_voice(visual,mp3,output,ffmpeg)
    project=None
    if config.send_to_concat:
        if not config.concat_exe:
            raise RecapError('Video đã xuất tại '+str(output)+' nhưng chưa tìm thấy Concat.exe để tạo project.')
        status('Đang tạo project độc lập bằng Concat MCP...')
        project=prepare_concat_project(config.concat_exe,output,root,
                                       str(draft.get('title') or 'LMK Recap'))
    result={'output':str(output),'project':str(project) if project else None,
            'plan':str(folder/'scene_plan.json'),'script':str(folder/'kich_ban.txt'),
            'seconds':media_duration(output,ffmpeg),'clips':len(clips)}
    (folder/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    status('HOÀN THÀNH: '+str(output))
    return result
