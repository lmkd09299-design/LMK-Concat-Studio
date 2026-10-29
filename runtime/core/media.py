"""Local FFmpeg primitives. No shell=True and no DRM circumvention."""
from __future__ import annotations
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

class MediaError(RuntimeError):
    pass

def binary(name: str) -> str:
    root = Path(__file__).resolve().parent.parent
    suffix = '.exe' if os.name == 'nt' else ''
    bundled = root / '.runtime' / 'ffmpeg' / 'bin' / (name + suffix)
    if bundled.is_file():
        return str(bundled)
    path = shutil.which(name)
    if not path:
        raise MediaError(f"Chưa tìm thấy {name}. Hãy cài FFmpeg và thêm thư mục bin vào PATH.")
    return path

def execute(args: list[str], *, timeout: int = 21600, progress=None) -> str:
    p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, errors="replace",
                         creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    try:
        stdout, stderr = p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        p.kill(); p.communicate()
        raise MediaError(f"Tiến trình hết thời gian: {Path(args[0]).name}")
    if p.returncode:
        raise MediaError((stderr or stdout)[-2500:])
    if progress: progress(Path(args[0]).name + " hoàn tất")
    return (stdout or "") + "\n" + (stderr or "")

def probe(path: str | Path) -> dict:
    src = Path(path).expanduser().resolve()
    if not src.is_file(): raise MediaError(f"Không tìm thấy media: {src}")
    r = subprocess.run([binary('ffprobe'), '-v','error','-show_format','-show_streams',
                         '-of','json',str(src)], capture_output=True, text=True,
                       creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),timeout=90)
    if r.returncode: raise MediaError(r.stderr[-1000:])
    data=json.loads(r.stdout)
    duration=float(data.get('format',{}).get('duration',0) or 0)
    videos=[x for x in data.get('streams',[]) if x.get('codec_type')=='video']
    audio=any(x.get('codec_type')=='audio' for x in data.get('streams',[]))
    if not videos or duration<=0: raise MediaError('Video thiếu luồng hình hoặc thời lượng.')
    return {'path':str(src),'duration':duration,'width':videos[0].get('width'),
            'height':videos[0].get('height'),'audio':audio,'size':src.stat().st_size}

def filter_video(aspect: str='9:16', title: str='', brightness: float=0., saturation: float=1.) -> str:
    w,h=(1080,1920) if aspect=='9:16' else ((1920,1080) if aspect=='16:9' else (1080,1080))
    # Use pad, not crop: preserve source footage; avoid fake copyright bypass.
    v=f'scale=w={w}:h={h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1'
    if brightness or saturation!=1: v+=f',eq=brightness={min(.5,max(-.5,brightness))}:saturation={min(3.,max(0.,saturation))}'
    return v + ',fps=25,format=yuv420p'

def subtitles_filter(srt_path: Path) -> str:
    # ffmpeg subtitles path escaping: Unicode Windows paths are best handled by copying into a temp ASCII folder.
    p=str(srt_path).replace('\\','/').replace(':','\\:').replace("'", "\\'").replace('[','\\[').replace(']','\\]')
    return "subtitles='"+p+"':force_style='FontSize=18,Outline=2,Shadow=1,MarginV=45'"

def render_segment(src: str, out: Path, start: float, end: float, aspect='9:16',
                   srt: Path | None=None, brightness=0., saturation=1., audio_gain=1., progress=None) -> Path:
    if end-start < .2: raise MediaError('Cảnh quá ngắn để dựng.')
    info=probe(src)
    end=min(end,info['duration']); start=max(0,start)
    out.parent.mkdir(parents=True,exist_ok=True)
    vf=filter_video(aspect,brightness=brightness,saturation=saturation)
    if srt: vf+=','+subtitles_filter(srt)
    args=[binary('ffmpeg'),'-hide_banner','-loglevel','error','-y','-ss',f'{start:.3f}',
          '-i',src,'-t',f'{end-start:.3f}','-vf',vf,'-c:v','libx264','-preset','veryfast',
          '-crf','23','-pix_fmt','yuv420p']
    if info['audio']:
        if audio_gain != 1.: args+=['-af',f'volume={max(0.,min(1.,audio_gain))}']
        args+=['-c:a','aac','-b:a','128k','-ar','44100']
    else: args+=['-f','lavfi','-t',f'{end-start:.3f}','-i','anullsrc=r=44100:cl=stereo',
                 '-map','0:v:0','-map','1:a:0','-c:a','aac','-shortest']
    execute(args+[str(out)],progress=progress)
    return out

def merge_clips(clips: list[Path], output: Path, progress=None) -> Path:
    if not clips: raise MediaError('Không có cảnh để ghép.')
    output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='lmk-list-') as temp:
        lst=Path(temp)/'concat.txt'
        # Concat demuxer allows escaped single quotes; clips are all rendered to same format.
        lst.write_text(''.join("file '"+str(p.resolve()).replace('\\','/').replace("'", "'\\''")+"'\n" for p in clips),encoding='utf-8')
        execute([binary('ffmpeg'),'-hide_banner','-loglevel','error','-y',
                 '-f','concat','-safe','0','-i',str(lst),'-c','copy',str(output)],progress=progress)
    return output

def remux_voice(video: Path, voice: Path, output: Path, original_gain: float=.12) -> Path:
    if not 0<=original_gain<=1: raise MediaError('Âm lượng gốc phải trong 0–1')
    info=probe(video)
    args=[binary('ffmpeg'),'-hide_banner','-loglevel','error','-y','-i',str(video),'-i',str(voice)]
    if info['audio']:
        args+=['-filter_complex',f'[0:a]volume={original_gain}[bg];[1:a]apad[nar];[bg][nar]amix=inputs=2:duration=first:dropout_transition=0[a]',
               '-map','0:v:0','-map','[a]']
    else: args+=['-map','0:v:0','-map','1:a:0']
    args+=['-c:v','copy','-c:a','aac','-b:a','160k','-t',f"{info['duration']:.3f}",str(output)]
    execute(args)
    return output

def generate_scenes(path: str, threshold: float=.31, max_cuts: int=2000, progress=None)->list[tuple[float,float]]:
    """Scene boundaries by FFmpeg histogram changes. Fastest on a small scaled stream."""
    info=probe(path)
    cmd=[binary('ffmpeg'),'-hide_banner','-nostats','-i',path,'-vf',
         f"fps=2,scale=320:-2,select='gt(scene,{min(.8,max(.05,threshold))})',showinfo",
         '-an','-f','null','-']
    p=subprocess.Popen(cmd,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True,
                       errors='replace',creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    boundaries=[0.0]
    try:
        assert p.stderr is not None
        for line in p.stderr:
            if 'showinfo' in line and 'pts_time:' in line:
                m=re.search(r'pts_time:\s*([\d.]+)',line)
                if m:
                    t=float(m.group(1))
                    if .3<t<info['duration']-.3 and t-boundaries[-1]>.5:
                        boundaries.append(t)
            if len(boundaries)>=max_cuts:
                p.kill();break
        p.wait(timeout=15)
    finally:
        if p.poll() is None: p.kill();p.wait()
    boundaries.append(info['duration'])
    result=list(zip(boundaries[:-1],boundaries[1:]))
    if progress: progress(f'Nhận diện {len(result)} cảnh')
    return result
