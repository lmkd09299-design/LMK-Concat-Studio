# LMK Recap Bridge — Windows EXE độc lập

Ứng dụng **không sửa Concat**. Dùng Gemini CLI chính thức để đăng nhập bằng Google (OAuth) và gọi AI bằng phiên đã đăng nhập; dùng Concat MCP chính thức để tạo project mới chứa MP4 hoàn thiện.

## Chuẩn bị một lần

1. Cài **Concat bản gốc** của `jub0t/Concat`, lưu đường dẫn `concat.exe`. Concat cần phiên bản hỗ trợ `--mcp headless`.
2. Cài **Node.js** và Gemini CLI chính thức: `npm install -g @google/gemini-cli`. Mở `gemini`, chọn **Sign in with Google** và đăng nhập trình duyệt. LMK không yêu cầu API key. Đây là một công cụ CLI riêng, không được đóng gói trong EXE LMK.
3. Chạy **LMK-Recap-Bridge.exe**. Gemini CLI cần internet; lần đầu Whisper CPU tải model (có thể lâu). Giao diện LMK là EXE độc lập, không cần cài Python/FFmpeg riêng nếu bản GitHub EXE đã đóng gói đầy đủ.
4. Chọn video (và file SRT có sẵn nếu muốn xử lý nhanh), chọn thời lượng, ngôn ngữ. Nhấn **TỰ ĐỘNG RECAP**.
5. Kết quả có `LMK-RECAP.mp4`, `scene_plan.json`, `kich_ban.txt`, `voice.mp3`, `transcript.srt`. Nếu bật điều khiển Concat, LMK tạo project Concat trong thư mục `Concat-Projects` và thêm MP4 lên timeline để mở/edit bằng Concat gốc.

## Trách nhiệm của từng phần

- **Gemini CLI OAuth:** viết kịch bản và chọn mốc truyện từ *transcript*, không có API key. Gọi `gemini -p ... --output-format json` với lời thoại gửi qua stdin. Phụ thuộc hạn mức, chính sách và hỗ trợ account của Gemini CLI; Google AI Pro web không bảo đảm vô hạn CLI.
- **Whisper CPU:** chuyển giọng phim thành transcript bằng `faster-whisper`. Nên dùng SRT khi đã có để không mất thời gian trên laptop không GPU.
- **FFmpeg:** tự cắt và ghép những cảnh được Gemini chọn. Dựng 720p (dọc) hoặc 1280x720 (ngang) bằng CPU. Video dài có thể mất nhiều thời gian.
- **Edge TTS:** giọng thuyết minh online tiếng Anh/Việt không dùng API key. **Không phải giọng nội bộ Concat**: Concat MCP hiện chưa có công cụ tổng hợp giọng đọc riêng; nói như vậy sẽ gây hiểu lầm.
- **Concat MCP:** tạo project riêng, import MP4 recap, thêm nó vào timeline, save project. **Không sửa project đang mở trên giao diện Concat**; đây là giới hạn chính thức của MCP. Người dùng mở project mới ở Concat sau khi xuất.

## Giới hạn kiểm thử

CI build EXE và chạy unit tests mock. Không có quyền truy cập tài khoản Google, session Concat, hoặc phim của người dùng trên GitHub; các chức năng hoàn chỉnh **chưa được kiểm thử thực tế** cho tới khi tự xác nhận một test video ngắn thành công. Bản EXE không bảo đảm vượt Content ID/DRM/bản quyền; nguồn phim phải có quyền sử dụng phù hợp.

## Mở code tại repo

Thư mục `standalone/` của repo LMK Concat Studio là app hoàn toàn riêng. Workflow build độc lập `build-standalone.yml`, **không chạy Rust/Slint**, không sửa mã nguồn Concat.

### Kiểm thử local

```shell
python -m unittest discover -s tests -v
python -m compileall -q main.py standalone
```

**Docs**: https://geminicli.com/docs/get-started/authentication/ ; https://geminicli.com/docs/cli/headless/ ; https://github.com/jub0t/Concat/blob/main/docs/MCP.md
