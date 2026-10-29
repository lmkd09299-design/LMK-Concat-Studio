"""Editing, language conversion, independent copyright checklist."""
from __future__ import annotations
import re
import json
from pathlib import Path
from .media import MediaError,probe,render_segment,remux_voice
from .speech import read_srt,write_srt,transcribe,timed_voice
from .ai import AISettings,translated_segments

RIGHTS={'Tự quay / tự sở hữu','Được cấp phép','Public domain / CC phù hợp','Chưa xác minh'}

def audit_rights(source:str,license_status:str,commentary:bool=False)->dict:
    if license_status not in RIGHTS:raise MediaError('Loại quyền sử dụng không hợp lệ.')
    flags=[]
    if license_status=='Chưa xác minh':flags.append('Nguồn chưa được xác minh quyền sử dụng; tránh xuất bản trước khi rà soát.')
    if not commentary: flags.append('Video chưa bổ sung lời bình/phân tích; chỉnh sửa kỹ thuật đơn thuần không tạo quyền sử dụng.')
    flags.extend(['Dịch/lồng tiếng/cắt cảnh không tự động xoá bản quyền của chủ sở hữu.',
                  'Không thể cam kết tránh Content ID, khiếu nại YouTube hoặc TikTok.'])
    return {'file':str(Path(source).resolve()),'rights_status':license_status,'analysis_added':commentary,
            'checks':flags,'platform_clearance':'Chưa xác minh; cần người dùng kiểm tra giấy phép và quyền sử dụng.'}

def build_edited_video(video:str,outfolder:str,*,srt_path='',language='Giữ nguyên',
                       ai:AISettings|None=None,asr_model='tiny',aspect='9:16',
                       burn_subs=False,dubbing=False,voice_engine='edge',voice_name='vi-VN-HoaiMyNeural',
                       start=0.,end=0.,original_gain=.1,brightness=0.,saturation=1.,
                       rights_status='Chưa xác minh',commentary=False,analysis_text='',mute_original=False,progress=None)->dict:
    ai=ai or AISettings();out=Path(outfolder).expanduser().resolve();out.mkdir(parents=True,exist_ok=True)
    log=progress or (lambda s:None)
    info=probe(video); start=max(0.,float(start)); end=float(end) or info['duration']
    end=min(end,info['duration'])
    if end<=start+.2:raise MediaError('Khoảng cắt không hợp lệ.')
    transcript=[];sub=None
    if burn_subs or dubbing or language!='Giữ nguyên':
        log('Đang đọc phụ đề hoặc nhận diện giọng nói')
        transcript=read_srt(srt_path) if srt_path else transcribe(video,model=asr_model,progress=log)
        transcript=[{'start':max(0.,v['start']-start),'end':min(end-start,v['end']-start),
                     'text':v['text']} for v in transcript if v['end']>start and v['start']<end]
        if language!='Giữ nguyên':transcript=translated_segments(transcript,language,ai,log)
        if transcript:sub=write_srt(transcript,out/'phu_de.srt')
    # Real, user-written contribution. Make its on-screen display auditable.
    # This is editorial authorship, not a promise of any copyright clearance.
    notes = []
    analysis_text = analysis_text.strip()
    if analysis_text:
        words = re.split(r'\s+', analysis_text)
        chunks = []
        current = ''
        for word in words:
            if len(current) + len(word) + 1 > 95 and current:
                chunks.append(current)
                current = ''
            current = (current + ' ' + word).strip()
        if current:
            chunks.append(current)
        duration = end - start
        secs = min(7.0, duration / max(1, len(chunks)))
        for index, piece in enumerate(chunks):
            begin = index * secs
            if begin >= duration:
                break
            notes.append({'start':begin, 'end':min(duration, begin + secs), 'text':piece})
        (out/'loi_binh_goc.txt').write_text(analysis_text, encoding='utf-8-sig')
        write_srt(notes, out/'loi_binh_goc.srt')
    active_sub = sub if burn_subs else None
    if notes:
        # Prefer the original commentary on overlapping timestamps.
        source_cues = []
        if burn_subs and transcript:
            notes_end = notes[-1]['end']
            source_cues = [v for v in transcript if v['start'] >= notes_end]
        active_sub = write_srt(notes + source_cues, out/'phu_de_thanh_pham.srt')
    log('Đang xuất hình ảnh và âm thanh')
    raw=out/'video_da_bien_tap.mp4'
    render_segment(video,raw,start,end,aspect=aspect,srt=active_sub,
                   brightness=brightness,saturation=saturation,audio_gain=0. if mute_original else 1.)
    result=raw
    if dubbing:
        if not transcript:raise MediaError('Chưa có lời thoại để lồng tiếng.')
        voice=timed_voice(transcript,end-start,out,voice_name,voice_engine,progress=log)
        result=remux_voice(raw,voice,out/'video_long_tieng.mp4',original_gain)
    audit=audit_rights(video,rights_status,bool(analysis_text))
    audit['original_commentary_characters']=len(analysis_text)
    audit['original_commentary_subtitle_cues']=len(notes)
    (out/'kiem_tra_ban_quyen.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
    report={'output':str(result),'duration':probe(result)['duration'],'subtitles':str(sub) if sub else None,
            'rights':audit,'dubbed':dubbing,'mute_original_audio':mute_original,
            'commentary_captions':str(out/'loi_binh_goc.srt') if notes else None}
    (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    log('Xuất video thành công')
    return report
