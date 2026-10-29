"""Timed transcript, opt-in ASR, translation and voice tools."""
from __future__ import annotations
import asyncio
import re
import subprocess
import shutil
from pathlib import Path
from .media import binary,execute, MediaError

def srt_stamp(sec:float)->str:
    ms=max(0,round(sec*1000)); h,r=divmod(ms,3600000);m,r=divmod(r,60000);s,ms=divmod(r,1000)
    return f'{h:02}:{m:02}:{s:02},{ms:03}'

def parse_stamp(x:str)->float:
    p=re.split(r'[:,.]',x.strip());p=(['0']*(4-len(p)))+p
    h,m,s,ms=map(int,p[-4:]);return h*3600+m*60+s+ms/1000

def read_srt(path: str|Path)->list[dict]:
    text=Path(path).read_text(encoding='utf-8-sig',errors='replace').replace('\r\n','\n')
    chunks=re.split(r'\n\s*\n',text.strip()); items=[]
    for block in chunks:
        lines=block.splitlines();idx=next((i for i,l in enumerate(lines) if '-->' in l),-1)
        if idx==-1:continue
        times=lines[idx].split('-->')
        try:
            a=parse_stamp(times[0]); b=parse_stamp(times[1].strip().split(' ')[0]); body=' '.join(lines[idx+1:]).strip()
        except Exception:continue
        if b>a and body:items.append({'start':a,'end':b,'text':re.sub('<[^>]+>','',body)})
    return items

def write_srt(items:list[dict],path:Path)->Path:
    path.parent.mkdir(parents=True,exist_ok=True)
    lines=[]
    for i,v in enumerate(items,1):
        if v['end']<=v['start']:continue
        lines.extend([str(i),f"{srt_stamp(v['start'])} --> {srt_stamp(v['end'])}",v['text'],''])
    path.write_text('\n'.join(lines),encoding='utf-8-sig');return path

def transcribe(video:str, model='tiny', language: str|None=None, progress=None)->list[dict]:
    try:from faster_whisper import WhisperModel
    except ImportError as exc:raise MediaError('Thiếu faster-whisper: pip install faster-whisper') from exc
    if progress:progress('Đang tải model Whisper / nhận diện lời thoại trên CPU...')
    model=WhisperModel(model,device='cpu',compute_type='int8',cpu_threads=4)
    segments,_=model.transcribe(video,language=language or None,beam_size=2,vad_filter=True,
                                condition_on_previous_text=False)
    out=[]
    for s in segments:
        if s.end>s.start and s.text.strip():out.append({'start':float(s.start),'end':float(s.end),'text':s.text.strip()})
    if progress:progress(f'Đã nhận diện {len(out)} đoạn lời thoại')
    return out

async def edge_speak(text:str, path:Path, voice='vi-VN-HoaiMyNeural'):
    try:import edge_tts
    except ImportError as exc:raise MediaError('Thiếu edge-tts: pip install edge-tts') from exc
    path.parent.mkdir(parents=True,exist_ok=True)
    await edge_tts.Communicate(text,voice).save(str(path))
    if not path.exists() or path.stat().st_size==0:raise MediaError('Dịch vụ TTS không tạo được tệp âm thanh')
    return path

def speak(text:str,path:Path,voice='vi-VN-HoaiMyNeural',engine='edge')->Path:
    if not text.strip():raise MediaError('Thiếu nội dung đọc')
    if engine=='edge':return asyncio.run(edge_speak(text,path,voice))
    if engine!='system':raise MediaError('Chỉ hỗ trợ edge hoặc system TTS.')
    # Windows SAPI offline, no voice cloning. Quoting is managed by passing a .txt file path.
    if not shutil.which('powershell'):raise MediaError('Giọng hệ thống chỉ hỗ trợ Windows PowerShell')
    source=path.with_suffix('.txt');source.write_text(text,encoding='utf-8-sig')
    wav=path.with_suffix('.wav')
    script=path.with_suffix('.ps1')
    script.write_text(
        'param([string]$TextFile,[string]$WavFile)\n'
        'Add-Type -AssemblyName System.Speech\n'
        '$speaker=New-Object System.Speech.Synthesis.SpeechSynthesizer\n'
        '$speaker.SetOutputToWaveFile($WavFile)\n'
        '$speaker.Speak([System.IO.File]::ReadAllText($TextFile))\n'
        '$speaker.Dispose()\n',encoding='utf-8')
    proc=subprocess.run(['powershell','-NoProfile','-File',str(script),'-TextFile',str(source),
                         '-WavFile',str(wav)],capture_output=True,text=True)
    if proc.returncode:
        raise MediaError('Windows TTS thất bại: '+proc.stderr[-900:])
    execute([binary('ffmpeg'),'-hide_banner','-loglevel','error','-y','-i',str(wav),str(path)])
    wav.unlink(missing_ok=True);source.unlink(missing_ok=True);script.unlink(missing_ok=True)
    return path

def timed_voice(items:list[dict],duration:float,outdir:Path,voice='vi-VN-HoaiMyNeural',
                engine='edge',max_span=24.,progress=None)->Path:
    """Construct a 16kHz mono WAV soundtrack aligned with subtitle time ranges.

    Groups subtitle lines to keep TTS call count manageable. Each synthesized block
    is placed at its original timestamp, capped before the next block. This is a
    coarse dubbing track; it does not clone an actor or create lip synchronization.
    """
    import struct
    log=progress or (lambda s:None)
    outdir.mkdir(parents=True,exist_ok=True)
    items=sorted([x for x in items if x.get('text','').strip() and x['start']<duration],
                 key=lambda x:x['start'])
    if not items:raise MediaError('Chưa có lời thoại để tổng hợp voice.')
    groups=[];current=[];group_start=0.
    for x in items:
        if not current:group_start=max(0.,float(x['start']))
        if current and float(x['end'])-group_start>max_span:
            groups.append({'start':group_start,'end':max(y['end'] for y in current),
                           'text':' '.join(y['text'] for y in current)})
            current=[];group_start=max(0.,float(x['start']))
        current.append(x)
    if current:groups.append({'start':group_start,'end':max(y['end'] for y in current),
                              'text':' '.join(y['text'] for y in current)})
    rate=16000; samples=max(1,int(duration*rate));size=samples*2
    wav=outdir/'giong_doc_can_thoi_gian.wav'
    # Write 44-byte PCM WAVE header, then allocate zero-initialized samples.
    header=(b'RIFF'+struct.pack('<I',size+36)+b'WAVEfmt '+struct.pack('<IHHIIHH',
           16,1,1,rate,rate*2,2,16)+b'data'+struct.pack('<I',size))
    with wav.open('wb+') as dest:
        dest.write(header);dest.truncate(44+size)
        for index,g in enumerate(groups):
            next_start=groups[index+1]['start'] if index+1<len(groups) else duration
            allowed=max(0.,min(duration,next_start)-g['start'])
            if allowed<.1:continue
            spoken=outdir/f'tts_{index+1:04}.mp3'
            speak(g['text'],spoken,voice,engine)
            cmd=[binary('ffmpeg'),'-hide_banner','-loglevel','error','-i',str(spoken),
                 '-ar',str(rate),'-ac','1','-f','s16le','-']
            p=subprocess.run(cmd,capture_output=True,timeout=120,
               creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            if p.returncode:raise MediaError('Giọng nói không chuyển PCM được: '+p.stderr.decode(errors='replace')[-700:])
            dest.seek(44+int(g['start']*rate)*2)
            dest.write(p.stdout[:max(0,int(allowed*rate)*2)])
            log(f'Lồng tiếng {index+1}/{len(groups)} (mốc {g["start"]:.1f}s)')
    return wav
