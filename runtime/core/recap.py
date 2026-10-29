"""Movie overview/scene ranking: chronology-first, transcript-grounded."""
from __future__ import annotations
import csv
import json
import math
import re
from pathlib import Path
from .media import MediaError, probe, generate_scenes, render_segment, merge_clips, remux_voice
from .speech import read_srt, write_srt, transcribe, timed_voice
from .ai import AISettings, synopsis

KEYWORDS={'but','however','suddenly','discover','kill','die','escape','secret','betray','save','truth',
          'unexpected','police','murder','attack','why','because','wait','no','never','danger',
          'nhưng','bỗng','phát hiện','giết','chết','chạy','bí mật','phản bội','cứu','sự thật',
          'cảnh sát','nguy hiểm','tại sao','không','đừng','thật ra','cuối cùng','bất ngờ',
          'love','hate','family','father','mother','sister','brother','promise','find','help'}

def overlap(items:list[dict],a:float,b:float)->list[dict]:
    return [s for s in items if float(s['end'])>a and float(s['start'])<b]

def clips_from_scenes(scenes:list[tuple[float,float]], items:list[dict], max_length=15.,
                      min_length=3.)->list[dict]:
    """Build candidate windows from scene changes while avoiding 0.5-second microcuts."""
    if not scenes:return []
    total=scenes[-1][1]
    boundaries=[scenes[0][0]]+[s[1] for s in scenes]
    candidates=[]
    t=0.
    while t<total-.5:
        # Prefer last scene change up to 15s; otherwise split long shots.
        changes=[x for x in boundaries if t+min_length<=x<=t+max_length]
        end=max(changes) if changes else min(total,t+max_length)
        if end-t<min_length and candidates:
            candidates[-1]['end']=end
            break
        texts=overlap(items,t,end)
        words=' '.join(x['text'] for x in texts)
        terms=re.findall(r'\w+',words.lower()); kw=sum(w in KEYWORDS for w in terms)
        # Purely heuristic rank, not a determination of genuine cinematic quality.
        score=1+min(3,len(terms)/18)+min(3,kw)*1.35
        if '?' in words or '!' in words:score+=1.25
        if total and .72<t/total<.93:score+=.3
        candidates.append({'start':round(t,3),'end':round(end,3),'score':round(score,2),
                           'transcript':words[:750],'narration':'','duration':round(end-t,3)})
        t=end
    return candidates

def choose_clips(candidates:list[dict],target:int, min_count:int=4)->list[dict]:
    """Timeline coverage: distribute picks across story, not just viral words."""
    if not candidates:return []
    avg=sum(v['duration'] for v in candidates)/len(candidates)
    count=max(1,min(len(candidates), max(min_count,int(target/max(4,avg)))))
    # Limit spend for 2h films, but honor shorter inputs.
    count=min(count,100)
    if count>=len(candidates):return [dict(x) for x in candidates]
    groups=[]
    for i in range(count):
        lo=round(len(candidates)*i/count);hi=max(lo+1,round(len(candidates)*(i+1)/count))
        group=candidates[lo:hi]
        if group:groups.append(max(group,key=lambda x:(x['score'],x['duration'])))
    return sorted((dict(x) for x in groups),key=lambda x:x['start'])

def narrate_selected(selected:list[dict],ai:AISettings,target_language='Tiếng Việt',style='Kịch tính'):
    if not ai.ready():
        for x in selected:
            x['narration']=x['transcript'][:200] if x['transcript'] else 'Chuyển cảnh không có lời thoại.'
        return False
    # Batch to avoid token limits and force one-to-one grounding.
    for i in range(0,len(selected),18):
        chunk=selected[i:i+18]
        payload=[{'id':j,'at_seconds':int(v['start']),'dialogue':v['transcript'][:450]} for j,v in enumerate(chunk)]
        answer=ai.chat(
            'Là người viết lời bình review phim. Trả về JSON ARRAY [{"id":0,"narration":"..."},...]. '
            'Viết một câu lời bình 15–30 từ mỗi đoạn. Chỉ dựa trên hội thoại đã cung cấp, '
            'không bịa diễn biến hoặc nhân vật. Những đoạn không có lời thoại ghi "Cảnh chuyển tiếp". '
            'Nội dung mới phải có bình luận/phân tích, không chép y nguyên hội thoại.',
            f'Ngôn ngữ: {target_language}; phong cách: {style}\n'+json.dumps(payload,ensure_ascii=False),
            max_tokens=2200)
        raw=answer[answer.find('['):answer.rfind(']')+1]
        try:
            result=json.loads(raw)
            if len(result)!=len(chunk):raise ValueError('size mismatch')
            mapped={int(v['id']):str(v['narration']).strip() for v in result}
            for j,x in enumerate(chunk):x['narration']=mapped[j]
        except Exception as e:raise MediaError('Kịch bản AI sai định dạng JSON ở nhóm '+str(i//18+1)) from e
    return True

def save_plan(selected:list[dict], outdir:Path, summary:str,source:str,target:int,ai_generated:bool)->None:
    outdir.mkdir(parents=True,exist_ok=True)
    (outdir/'kich_ban.txt').write_text(summary+'\n\n--- LỜI BÌNH THEO CẢNH ---\n'+
      '\n'.join(f"[{x['start']:.1f}s-{x['end']:.1f}s] {x['narration']}" for x in selected),encoding='utf-8-sig')
    # Plain commentary script used directly by Concat's Kokoro/Pocket TTS.
    # No subtitles/timecodes in the speech input.
    narration = ' '.join(x['narration'].strip() for x in selected if x['narration'].strip())
    (outdir/'voice_script.txt').write_text(narration, encoding='utf-8')
    (outdir/'scene_plan.json').write_text(json.dumps({'source':source,'requested_seconds':target,
       'ai_generated':ai_generated,'segments':selected},ensure_ascii=False,indent=2),encoding='utf-8')
    with (outdir/'canh_chon.csv').open('w',newline='',encoding='utf-8-sig') as f:
        writer=csv.writer(f);writer.writerow(['STT','Bắt đầu (nguồn)','Kết thúc (nguồn)','Điểm','Lời bình'])
        for i,x in enumerate(selected,1):writer.writerow([i,x['start'],x['end'],x['score'],x['narration']])
    cursor=0.; captions=[]
    for x in selected:
        captions.append({'start':cursor,'end':cursor+x['duration'],'text':x['narration'][:260]})
        cursor+=x['duration']
    write_srt(captions,outdir/'loi_binh.srt')

def build_recap(video:str,output_folder:str,*,srt_path:str='',ai:AISettings|None=None,
                target_minutes:int=3,language='Tiếng Việt',style='Kịch tính',
                aspect='9:16',scene_threshold=.30,model='tiny',voice=False,
                voice_engine='edge',voice_name='vi-VN-HoaiMyNeural',
                progress=None)->dict:
    ai=ai or AISettings();outdir=Path(output_folder).expanduser().resolve();outdir.mkdir(parents=True,exist_ok=True)
    log=progress or (lambda s:None)
    info=probe(video)
    log(f"Film {info['duration']/60:.1f} phút; bắt đầu chuẩn bị transcript")
    items=read_srt(srt_path) if srt_path else transcribe(video,model=model,progress=log)
    if not items:raise MediaError('Không có lời thoại để tóm tắt. Dùng SRT hoặc kiểm tra Whisper.')
    write_srt(items,outdir/'transcript_nguon.srt')
    log('Đang tìm điểm chuyển cảnh')
    scenes=generate_scenes(video,threshold=scene_threshold,progress=log)
    candidates=clips_from_scenes(scenes,items,max_length=15.)
    target=max(30,target_minutes*60)
    chosen=choose_story_clips(candidates,items,target,ai,language,log)
    # Reduce final running time to requested duration, preserve chronological coverage.
    total=sum(x['duration'] for x in chosen)
    if total>target:
        ratio=target/total
        for x in chosen:
            newdur=max(2.,x['duration']*ratio)
            x['end']=round(x['start']+newdur,3);x['duration']=round(newdur,3)
    log(f'Chọn {len(chosen)} cảnh (tổng {sum(x["duration"] for x in chosen):.0f}s)')
    script=synopsis(items,ai,language,style)
    generated=narrate_selected(chosen,ai,language,style)
    save_plan(chosen,outdir,script,video,target,generated)
    pieces=[]; work=outdir/'clips';work.mkdir(exist_ok=True)
    for index,x in enumerate(chosen,1):
        clip=work/f'scene_{index:03}.mp4'
        render_segment(video,clip,x['start'],x['end'],aspect=aspect)
        pieces.append(clip)
        log(f'Dựng cảnh {index}/{len(chosen)}')
    combined=merge_clips(pieces,outdir/'recap_video.mp4')
    output=combined
    if voice:
        cursor=0.; cues=[]
        for x in chosen:
            cues.append({'start':cursor,'end':cursor+x['duration'],'text':x['narration']})
            cursor+=x['duration']
        voicefile=timed_voice(cues,probe(combined)['duration'],outdir,voice_name,voice_engine,
                             max_span=15.,progress=log)
        output=remux_voice(combined,voicefile,outdir/'recap_long_tieng.mp4')
    report={'source':str(Path(video).resolve()),'output':str(output),
            'segments':len(chosen),'source_duration':info['duration'],'output_duration':probe(output)['duration'],
            'script_ai':generated,'transcript_count':len(items),'scene_files':[str(x) for x in pieces]}
    (outdir/'report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    log('Đã xuất MP4, kịch bản TXT, phân cảnh CSV/JSON và phụ đề SRT')
    return report

def choose_story_clips(candidates:list[dict],items:list[dict],target:int,ai:AISettings,
                       language:str,progress=None)->list[dict]:
    """Use AI-informed plot points, with deterministic fallback and time coverage."""
    baseline=choose_clips(candidates,target)
    if not ai.ready() or not candidates:return baseline
    from .ai import story_beats
    log=progress or (lambda s:None)
    try:
        anchors=story_beats(items,len(baseline),ai,language)
    except MediaError as e:
        log('Lựa chọn cốt truyện bằng AI lỗi; dùng chọn cảnh dự phòng: '+str(e))
        return baseline
    selected={}
    for at in anchors:
        nearest=min(candidates,key=lambda c:abs((c['start']+c['end'])/2-at))
        selected[nearest['start']]=dict(nearest)
    # Fill remaining from baseline, preserving story coverage and count.
    for c in baseline:
        if len(selected)>=len(baseline):break
        selected.setdefault(c['start'],dict(c))
    chosen=sorted(selected.values(),key=lambda c:c['start'])
    if len(chosen)>len(baseline):
        # Keep a roughly evenly spaced selection.
        chosen=choose_clips(chosen,target,min_count=min(len(baseline),4))[:len(baseline)]
    log(f'AI chọn {len(chosen)} mốc cốt truyện trên toàn phim')
    return chosen
