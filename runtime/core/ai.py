"""OpenAI-compatible text API, optional; nothing stored outside process memory."""
from __future__ import annotations
import json
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass
from .media import MediaError

@dataclass
class AISettings:
    base_url: str = ''
    model: str = ''
    api_key: str = ''
    timeout: int = 180
    def ready(self)->bool:return bool(self.base_url and self.model)
    def chat(self,system:str,user:str,max_tokens=4000)->str:
        if not self.ready():raise MediaError('Chưa cấu hình AI API. Dùng chế độ trích xuất nguyên văn hoặc điền API.')
        root=self.base_url.strip().rstrip('/')
        p=urllib.parse.urlsplit(root)
        if p.scheme!='https' and not(p.scheme=='http' and p.hostname in ('localhost','127.0.0.1','::1')):
            raise MediaError('API phải dùng HTTPS, trừ máy cục bộ 127.0.0.1.')
        url=(root if root.endswith('/chat/completions') else root+'/chat/completions')
        body=json.dumps({'model':self.model,'messages':[{'role':'system','content':system},
                {'role':'user','content':user}], 'temperature':.35,'max_tokens':max_tokens}).encode()
        headers={'Content-Type':'application/json'}
        if self.api_key:headers['Authorization']='Bearer '+self.api_key
        try:
            with urllib.request.urlopen(urllib.request.Request(url,body,headers), timeout=self.timeout) as r:
                x=json.load(r)
            return x['choices'][0]['message']['content'].strip()
        except Exception as e:
            raise MediaError('Lỗi API văn bản: '+str(e)[:350]) from e

def translated_segments(items:list[dict],target:str,ai:AISettings,progress=None)->list[dict]:
    if target=='Giữ nguyên':return [dict(x) for x in items]
    if not ai.ready():raise MediaError('Dịch tự động cần API text OpenAI-compatible. Có thể dùng localhost Ollama.')
    result=[];step=24
    for i in range(0,len(items),step):
        part=items[i:i+step]
        raw=json.dumps([{'id':j,'text':v['text']} for j,v in enumerate(part)],ensure_ascii=False)
        answer=ai.chat('Dịch phụ đề chính xác, tự nhiên. Chỉ xuất JSON array các object {id, text}. '
                       'Giữ nguyên số lượng, thứ tự, tên riêng. Không thêm nội dung.',
                      f'Ngôn ngữ đích: {target}\n{raw}',max_tokens=1800)
        answer=answer[answer.find('['):answer.rfind(']')+1]
        try:
            trans=json.loads(answer)
            if len(trans)!=len(part):raise ValueError('Số dòng không khớp')
            for j,v in enumerate(part):result.append({**v,'text':str(trans[j]['text'])})
        except Exception as e:raise MediaError('AI trả phụ đề sai cấu trúc tại nhóm '+str(i//step+1)) from e
        if progress:progress(f'Đã dịch {len(result)}/{len(items)} dòng')
    return result

def synopsis(items:list[dict],ai:AISettings,target='Tiếng Việt',style='Kịch tính')->str:
    if not items:return 'Không có lời thoại. Chỉ tạo được bản ghép cảnh trực quan.'
    # Grounded extractive fallback; never invent a plot unseen in the transcript.
    if not ai.ready():
        selected=[items[round(i*(len(items)-1)/min(11,len(items)-1))]['text'] for i in range(min(12,len(items)))] if len(items)>1 else [items[0]['text']]
        return 'BẢN TRÍCH XUẤT (chưa có AI phân tích):\n'+'\n'.join(selected)
    # Spread excerpts across movie rather than just the beginning.
    stride=max(1,len(items)//160)
    slim=[{'t':round(x['start']),'text':x['text'][:210]} for x in items[::stride][:160]]
    return ai.chat('Bạn viết kịch bản REVIEW phim dựa DUY NHẤT trên transcript được cung cấp. '
                   'Nêu cốt truyện, nhân vật, diễn biến chính, cao trào, kết thúc nếu nguồn có; '
                   'không đoán tình tiết; thiếu dữ kiện thì ghi rõ. Tránh sao chép lời thoại dài. '
                   'Viết thuyết minh độc lập, biến đổi mang tính bình luận/phân tích.',
                   f'Ngôn ngữ: {target}. Phong cách: {style}. Transcript theo thời gian:\n'+
                   json.dumps(slim,ensure_ascii=False),max_tokens=2200)

def story_beats(items:list[dict],count:int,ai:AISettings,language='Tiếng Việt')->list[float]:
    """Request chronological important timestamps from the provided transcript.

    Returned timestamps are hints, not factual evidence; chosen video remains source-grounded.
    """
    if not ai.ready() or not items:return []
    stride=max(1,len(items)//180)
    sample=[{'at':round(v['start'],1),'speech':v['text'][:160]} for v in items[::stride][:180]]
    reply=ai.chat('Phân tích toàn bộ diễn biến phim từ phụ đề theo thời gian. '
      'Chỉ trả JSON array các timestamp số thực (giây) tại những đoạn chứa mốc truyện QUAN TRỌNG. '
      'Chọn các điểm phân bố từ mở đầu tới kết thúc, ưu tiên hành động, nguyên nhân, tiết lộ, '
      'cao trào, kết thúc. Dựa trên nguồn, không bịa nội dung hoặc timestamp.',
      f'Chọn khoảng {count} mốc, ngôn ngữ {language}. Dữ liệu: '+json.dumps(sample,ensure_ascii=False),
      max_tokens=800)
    try:
        times=json.loads(reply[reply.find('['):reply.rfind(']')+1])
        tmax=max(v['end'] for v in items)
        return sorted({round(float(t),2) for t in times if isinstance(t,(int,float)) and 0<=float(t)<=tmax})
    except Exception as e:
        raise MediaError('AI trả danh sách mốc truyện sai định dạng.') from e
