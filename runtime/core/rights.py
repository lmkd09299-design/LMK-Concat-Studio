"""Copyright provenance checklist and licensed audio replacement.

No matching against YouTube/TikTok Content ID or remote licensing databases.
A rights declaration is user-supplied and never amounts to clearance.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

from .media import MediaError, binary, execute, probe

RIGHTS = {'Tự quay / tự sở hữu', 'Được cấp phép', 'Public domain / CC phù hợp', 'Chưa xác minh'}


def audit_and_transform(video: str, outfolder: str, *, license_status: str = 'Chưa xác minh',
                        replacement_audio: str = '', license_note: str = '',
                        remove_original: bool = False, progress=None) -> dict:
    """Write an honest rights audit; optionally mute/replace source audio.

    For any third-party video, both video rights AND soundtrack rights must be
    addressed independently. This operation never certifies platform safety.
    """
    if license_status not in RIGHTS:
        raise MediaError('Tình trạng quyền sử dụng không hợp lệ.')
    info = probe(video)
    replacement = Path(replacement_audio).expanduser().resolve() if replacement_audio else None
    if replacement:
        if not replacement.is_file():
            raise MediaError('Không tìm thấy file âm thanh thay thế.')
        if not license_note.strip():
            raise MediaError('Cần ghi chú nguồn/giấy phép của âm thanh thay thế.')
        if replacement == Path(video).expanduser().resolve():
            raise MediaError('Video nguồn không phải file âm thanh thay thế.')
    out = Path(outfolder).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    checks = [
        ('Quyền hình ảnh/phim', 'Chưa xác minh độc lập',
         'Kiểm tra chủ sở hữu, điều khoản sử dụng và phạm vi cấp phép'),
        ('Quyền nhạc và âm thanh gốc', 'Cần rà soát' if info['audio'] else 'Không có audio trong nguồn',
         'Thay âm thanh không tự cho phép sử dụng hình ảnh gốc'),
        ('Quyền âm thanh thay thế', 'Người dùng khai báo' if replacement else 'Không áp dụng',
         'Kiểm tra giấy phép, tác giả, lãnh thổ và nền tảng'),
        ('Content ID / TikTok', 'Chưa kiểm tra',
         'Không có truy cập hệ thống đối chiếu bản quyền của nền tảng'),
    ]
    output = None
    if replacement or remove_original:
        output = out / 'video_ra_soat_am_thanh.mp4'
        if output.exists():
            raise MediaError(f'File đích đã tồn tại; hãy đổi thư mục xuất: {output}')
        cmd = [binary('ffmpeg'), '-hide_banner', '-loglevel', 'error', '-n',
               '-i', info['path']]
        if replacement:
            # Loop a licensed soundtrack if shorter than video, keep original video stream.
            cmd.extend(['-stream_loop', '-1', '-i', str(replacement),
                        '-map', '0:v:0', '-map', '1:a:0',
                        '-c:v', 'copy', '-c:a', 'aac', '-b:a', '160k',
                        '-t', f"{info['duration']:.3f}"])
        else:
            cmd.extend(['-map', '0:v:0', '-an', '-c:v', 'copy'])
        cmd.extend(['-movflags', '+faststart', str(output)])
        execute(cmd, progress=progress)
    audit = {
        'source_video': info['path'],
        'source_duration_seconds': info['duration'],
        'source_has_audio': info['audio'],
        'user_declared_video_rights': license_status,
        'user_supplied_audio_license_note': license_note.strip() if replacement else '',
        'audio_replacement_file': str(replacement) if replacement else None,
        'original_audio_removed': bool(replacement or remove_original),
        'output_video': str(output) if output else None,
        'platform_clearance': 'CHƯA XÁC MINH: không truy cập Content ID/TikTok hoặc dữ liệu chủ sở hữu',
        'rights_warning': 'Biên tập kỹ thuật, bỏ nhạc, dịch và lồng tiếng không tự tạo quyền phát hành.',
        'checklist': [dict(item=i, status=status, action=action) for i,status,action in checks],
    }
    (out/'bao_cao_quyen_su_dung.json').write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding='utf-8')
    with (out/'danh_sach_can_kiem_tra.csv').open('w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(['Mục', 'Trạng thái', 'Việc cần làm'])
        writer.writerows(checks)
    report = {'output': str(output) if output else None, 'rights': audit,
              'audit_report': str(out/'bao_cao_quyen_su_dung.json'),
              'checklist_csv': str(out/'danh_sach_can_kiem_tra.csv')}
    (out/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    if progress:
        progress('Đã xuất báo cáo quyền sử dụng' + (' và MP4 đã thay audio' if output else ''))
    return report
