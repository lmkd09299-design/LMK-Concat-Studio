# LMK Concat Studio v4 — native fork with Windows GitHub Actions

**Mục tiêu:** biến Concat thành một ứng dụng Windows có sẵn hai tab *Biên tập & quyền sử dụng* và *Movie Recap AI*, ngoài editor gốc. **Dự án này chưa có file EXE đã kiểm thử.** GitHub Actions sẽ biên dịch bản Windows từ mã nguồn Concat sạch, kiểm tra khởi chạy, rồi mới tạo bản tải về nếu cả hai việc thành công.

## Anh làm gì?

1. Không dùng bản `BUILD_LMK_FORK.cmd` v3 nữa; giữ nguyên Concat đã cài.
2. Cài [Git for Windows](https://git-scm.com/download/win) và [GitHub CLI](https://cli.github.com/) nếu máy chưa có. **Không cần cài lại Rust, LLVM, CMake, FFmpeg hoặc Visual Studio.**
3. Đăng nhập GitHub trên trình duyệt khi được yêu cầu; giải nén ZIP dự án này vào một thư mục mới (không chạy bên trong ZIP).
4. Chạy **`PUBLISH_TO_GITHUB.cmd`**, chọn repo riêng tư hoặc công khai, gõ `YES` để xác nhận tạo repo và tải mã nguồn lên GitHub.
5. Mở repo trên GitHub → **Actions** → workflow **LMK Concat Studio — Windows build and checks**. Trạng thái **màu xanh** mới có file ZIP chương trình ở mục **Artifacts** của lượt chạy. Nếu màu đỏ, file log cho biết lỗi và **chưa phát hành**.

GitHub Actions có định mức phút sử dụng và có thể tính phí theo gói tài khoản; riêng tư và công khai có chế độ tính khác nhau. Kiểm tra mục Billing/Actions trước khi chạy lại nhiều lần. Không lưu khóa API trên GitHub.

## Từ mã nguồn đến ứng dụng

- CI checkout **Concat tại commit cố định** `f0c0169628c61de7311f7fc15ee5be82dd611d2e`.
- Sửa mã gốc `app.slint`, `lib.rs` và `build.rs` bằng `apply_fork.py`. Thêm component native `lmk-tools.slint` và command bridge `lmk.rs` **ngay trong cửa sổ Concat**. Không dùng Electron, Tkinter hoặc MCP để mở ứng dụng thứ hai.
- Chạy Python backend tests và kiểm tra bản vá trước bước build Windows.
- CI lấy các dependency được pin trong `upstream/scripts/ci/deps.lock`, tách thư viện Sherpa `.lib` khỏi `.dll`, dùng Rust `1.93.1` và profile **release**.
- Chỉ upload Windows artifact sau khi `concat.exe --version` và `--smoke` thành công. Nếu thất bại, xuất log trong Actions và không tạo gói cài đặt giả.

## Sử dụng bản dựng (chỉ sau khi GitHub Actions xanh)

1. Tải artifact `LMK-Concat-Studio-Windows-x64` từ Actions, giải nén.
2. Chạy **`START_LMK.cmd`**. Lần đầu yêu cầu Python 3.12 trên Windows và kết nối Internet để cài thư viện nhận dạng giọng nói; có thể cài [Python](https://www.python.org/downloads/) trước.
3. Trong Concat, mở project → chọn tab **Biên tập & quyền sử dụng** hoặc **Movie Recap AI**, nhập đường dẫn file video và thư mục output.
4. Lấy MP4/CSV/SRT/TXT được tạo trong thư mục output. **Chưa tự thêm output trở lại timeline**; sau khi xuất, dùng nút Import có sẵn của Concat.

## Những chức năng và giới hạn

- **Biên tập & quyền sử dụng**: chuyển định dạng 9:16/16:9/1:1, cắt ghép, SRT, dịch phụ đề với model tuỳ chọn, voice-over/TTS khi cấu hình, chèn lời bình và báo cáo tình trạng quyền sử dụng do người dùng xác nhận.
- **Movie Recap AI**: đọc SRT/timecode, tìm điểm cắt, chọn các cảnh tiêu biểu bằng heuristic hoặc model AI cấu hình riêng, tạo script, CSV, SRT, MP4. Kết quả không bảo đảm nhận biết đúng toàn bộ nội dung phim nếu không có model và transcript.
- **Không có cơ chế phá DRM, đánh lừa Content ID, xóa watermark của người khác hay bảo đảm tránh claim/strike trên YouTube/TikTok.** Việc dịch, lồng tiếng, thay khung hình không tự tạo quyền phát hành.
- Không có cơ chế tự tải hoặc sao chép phim từ dịch vụ streaming; nhập nội dung anh sở hữu hoặc được phép sử dụng.
- API do người dùng cấu hình tại máy chạy, không được đưa vào repository hoặc build artifacts.

## Đã kiểm thử và chưa kiểm thử

- Đã kiểm thử trên môi trường Linux: 10 unit tests gốc (2 patch, 8 backend) và kiểm tra `ScrollView` import. **Chưa biên dịch Slint/Rust native trong môi trường này.**
- Workflow GitHub Actions chưa được thực thi trên tài khoản GitHub của anh do GitHub connector không liệt kê repository có thể ghi. **Không có xác nhận `BUILD SUCCESS` hoặc binary Windows ở thời điểm đóng gói.**
- Trước khi gọi là bản release, cần Actions xanh và thử một MP4 thực tế trên Windows.

## Cấu trúc

```text
.github/workflows/windows-build.yml   # validate, native compile, smoke, artifact
apply_fork.py                          # patch pinned upstream; chống ghi đè
native/ui/lmk-tools.slint              # Slint 3-tab native UI
native/rust/lmk.rs                     # xử lý tác vụ nền
runtime/                               # FFmpeg/Whisper/recap backend
scripts/START_LMK.cmd                 # khởi chạy bản đã build
scripts/check_integration.py          # preflight tests
PUBLISH_TO_GITHUB.cmd                 # tự tạo repo (cần xác nhận GitHub)
```

**License:** mã gốc Concat theo AGPL-3.0-or-later; bảo toàn tác giả, LICENSE và THIRD_PARTY_NOTICES. Phần fork phải tuân thủ các nghĩa vụ giấy phép liên quan khi phân phối. Xem https://github.com/jub0t/Concat và file upstream/license tương ứng.


## Đề xuất v5 — tab BẢN QUYỀN & AUDIO (chưa phát hành)

Nhánh `feature/copyright-review-v5` thêm tab **BAN QUYEN & AUDIO** độc lập bên cạnh Biên tập video và Movie Recap AI. Tab cung cấp báo cáo JSON/CSV về các hạng mục cần kiểm tra quyền, tắt âm thanh gốc, hoặc thay bằng file nhạc đã được cấp phép trong video MP4, giữ nguyên hình ảnh gốc.

**Không có công cụ né Content ID/TikTok hoặc cơ chế tự xác nhận quyền phát hành.** Chỉnh sửa âm thanh không tạo quyền sử dụng hình ảnh phim. Giấy phép/nguồn nhạc do người dùng nhập không được tự động xác thực.

Dùng CLI trong bản v5:
- Chỉ xuất báo cáo: `python runtime/cli.py rights --input video.mp4 --out out`
- Tắt âm gốc: thêm `--mute-original`
- Thay nhạc: thêm `--replacement-audio licensed.wav --license-note "nguon/giay phep"`

Đầu ra gồm `report.json`, `bao_cao_quyen_su_dung.json`, `danh_sach_can_kiem_tra.csv`, và MP4 nếu có chỉnh sửa âm thanh. MP4 đang tồn tại sẽ không bị ghi đè.

Bản v4 hiện có đã build xanh và không bị sửa. Chỉ dùng v5 sau khi pull request qua kiểm thử GitHub Actions Windows.


## Movie Recap: chọn file, chọn AI, tự cắt ghép (bản v5 PR)

- Trên tab Movie Recap, nhấn **CHON** cạnh ô video để mở hộp chọn `mp4/mkv/mov`; phụ đề SRT và thư mục lưu có nút CHON riêng. Video đã nhập vào Concat Editor không tự gán cho tab Movie Recap.
- **Whisper CPU** biến lời thoại phim thành transcript. Chọn `tiny`, `base` hoặc `small` khi không có file SRT. Phụ đề SRT có sẵn là lựa chọn nhanh hơn, tránh transcribe lại.
- **Bat AI viet kich ban va chon canh**: bật và nhập `API URL`, `AI Model ID`, `API key` của **dịch vụ text AI tương thích OpenAI Chat Completions**. AI được gọi để viết recap và chọn timecode từ transcript; không có nhà cung cấp/model được cấp sẵn. Key chỉ truyền qua biến môi trường của tiến trình Python, không ghi xuống file cấu hình.
- Nếu tắt AI, phần mềm dùng điểm cảnh theo lời thoại/keyword và trích xuất văn bản: **không phải AI hiểu phim**.
- **FFmpeg** phát hiện chuyển cảnh, cắt các đoạn, ghép theo trật tự cốt truyện, tạo MP4, TXT/CSV/SRT và có thể tạo tiếng đọc qua Edge TTS. Hình ảnh không được AI nhìn hay hiểu ở phiên bản này. Cần quyền sử dụng phim và soundtrack phù hợp trước khi xuất bản.
- **Chưa tự nhập MP4 output vào timeline Concat**, muốn chỉnh sửa tiếp thì dùng Import trong Editor. Lần đầu chạy có thể tải model Whisper trên CPU.


## LMK Concat Studio v6 — Automatic One-Import Recap (proposal / CI validation)

**Workflow:** Create/Open Concat project → Import 1 movie in the native **CONCAT EDITOR** media bin → go to **MOVIE RECAP AI** → click **TU DONG RECAP**. No second file path and no output-folder prompt. If multiple videos are imported, select exactly one movie tile before starting. The existing project and source timeline are left untouched.

- Native Rust bridge resolves the already-imported media source from the active Concat project and creates an isolated `lmk-recaps/recap-<timestamp>` output inside it.
- Local CPU Whisper transcribes movie speech; FFmpeg detects scene cuts and creates a condensed MP4 automatically, plus `kich_ban.txt`, `scene_plan.json`, `canh_chon.csv`, `loi_binh.srt`, and `voice_script.txt`.
- Real AI-authored scripts require a configured **OpenAI-compatible text model** (for example, an independently obtained provider API). Enter URL/model/key in AI controls or configure `LMK_AI_BASE_URL`, `LMK_AI_MODEL`, `LMK_AI_KEY` in the launch environment once; no API keys are committed to the repo. When AI is explicitly switched off, the system uses transcript heuristics and labels that mode honestly.
- For **English** recap narration, uses Concat's existing native **Kokoro/Pocket** TTS model (last suitable selected voice; defaults to Kokoro `af_heart`). If no suitable model is installed, automatically downloads the supported compact Kokoro voice model on first use, then synthesizes WAV and mixes it with the recap automatically. A saved/sample-clone requiring a reference recording is not auto-selected. Download and CPU processing may be substantial.
- For Vietnamese/Thai recap, Concat's built-in TTS model does **not** reliably support those languages; the existing locale-specific Edge TTS is used instead. The English voice is not applied blindly to Vietnamese or Thai.
- On completion, the finished MP4 is automatically imported back to the **Concat media bin**. The source timeline is not replaced. The recap MP4 is ready to preview/export or edit further; it does **not** automatically construct a native editable multi-track timeline out of every clip.
- Even when automated, visual plot understanding remains limited to video scene boundaries and transcript. The tool cannot independently certify publishing rights for the source movie or music.

**Testing status:** implementation pushed to PR #1, awaiting completed Windows Rust/Slint build and smoke test. Do not download pre-release source as a functioning v6 installer until CI passes.
