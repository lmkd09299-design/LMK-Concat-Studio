"""Use Google's official Gemini CLI with cached Google sign-in. No API keys."""
from __future__ import annotations
import json
import os
import re
import shutil
import subprocess
from pathlib import Path


class GeminiError(RuntimeError):
    pass


def gemini_executable() -> str:
    executable = shutil.which('gemini') or shutil.which('gemini.cmd')
    if not executable:
        raise GeminiError('Chưa có Gemini CLI. Cài Node.js, rồi chạy: npm install -g @google/gemini-cli')
    return executable


def google_only_env() -> dict[str, str]:
    env = os.environ.copy()
    for item in ('GEMINI_API_KEY', 'GOOGLE_API_KEY', 'GOOGLE_GENAI_USE_VERTEXAI',
                 'GOOGLE_CLOUD_PROJECT', 'GOOGLE_CLOUD_LOCATION'):
        env.pop(item, None)
    return env


def open_login() -> None:
    exe = gemini_executable()
    # The login remains an explicitly interactive, first-party Google flow.
    if os.name == 'nt':
        subprocess.Popen(['cmd.exe', '/k', exe], creationflags=subprocess.CREATE_NEW_CONSOLE,
                         env=google_only_env())
    else:
        raise GeminiError('Đăng nhập Gemini CLI trên terminal bằng lệnh: gemini')


def extract_json(response: str) -> dict:
    text = response.strip()
    if text.startswith('```'):
        text = re.sub(r'^```(?:json)?\s*|\s*```$', '', text, flags=re.IGNORECASE).strip()
    try:
        answer = json.loads(text)
    except json.JSONDecodeError as exc:
        # Often Gemini encloses structured output in prose; only accept a JSON object.
        start, end = text.find('{'), text.rfind('}')
        if start < 0 or end <= start:
            raise GeminiError('Gemini không trả JSON kịch bản hợp lệ. Nội dung: ' + text[:220]) from exc
        try:
            answer = json.loads(text[start:end+1])
        except json.JSONDecodeError as inner:
            raise GeminiError('Gemini trả JSON sai định dạng: ' + str(inner)) from inner
    if not isinstance(answer, dict):
        raise GeminiError('Gemini phải trả một đối tượng JSON.')
    return answer


def ask_gemini(prompt: str, transcript: str, cwd: Path, timeout: int = 300) -> dict:
    exe = gemini_executable()
    cmd = [exe, '-p', prompt, '--output-format', 'json']
    # Keeping the transcript on stdin prevents Windows' command-line length limit.
    try:
        completed = subprocess.run(cmd, input=transcript, text=True,
                                   encoding='utf-8', errors='replace',
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   cwd=str(cwd), env=google_only_env(), timeout=timeout,
                                   shell=False)
    except subprocess.TimeoutExpired as exc:
        raise GeminiError('Gemini CLI quá thời gian phản hồi (5 phút).') from exc
    except OSError as exc:
        raise GeminiError('Không khởi chạy được Gemini CLI: ' + str(exc)) from exc
    if completed.returncode:
        message = (completed.stderr or completed.stdout)[-900:]
        raise GeminiError('Gemini CLI lỗi. Hãy đăng nhập Google trước. ' + message)
    try:
        envelope = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise GeminiError('Gemini CLI không trả envelope JSON hợp lệ.') from exc
    if envelope.get('error'):
        raise GeminiError('Gemini từ chối yêu cầu: ' + str(envelope['error'])[:400])
    return extract_json(envelope.get('response', ''))
