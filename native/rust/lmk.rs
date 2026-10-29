// SPDX-License-Identifier: AGPL-3.0-or-later
//! Native Concat UI integration for LMK Video Studio, desktop only.
//! The window remains Concat's Slint window. Processing runs on a worker
//! using the bundled Python runtime and FFmpeg, never on the UI thread.

use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::Arc;
use std::time::{SystemTime, UNIX_EPOCH};

use concat_speech::tts::{self, SpeakRequest, Speech};
use crate::host::Shell;

use crate::ui::App;
use slint::ComponentHandle;

#[derive(Clone, Debug)]
struct Job {
    mode: i32,
    source: PathBuf,
    subtitle: Option<PathBuf>,
    output: PathBuf,
    aspect: String,
    language: String,
    rights: String,
    voice: bool,
    burn: bool,
    mute: bool,
    minutes: i32,
    analysis: String,
    replacement_audio: Option<PathBuf>,
    license_note: String,
    use_ai: bool,
    ai_url: String,
    ai_model: String,
    ai_key: String,
    asr_model: String,
}

struct VoiceContext {
    speech: Arc<Speech>,
    dirs: concat_host::AppDirs,
    project: PathBuf,
    preferred_voice: i32,
}

fn recap_source_from_project() -> Result<(PathBuf, PathBuf, VoiceContext), String> {
    let mut found = Err("Open a Concat project and import a video first".to_owned());
    Shell::with(|shell, _| {
        let studio = shell.studio.borrow();
        let Some(session) = studio.session.as_ref() else {
            return;
        };
        let video_items: Vec<_> = studio.project().media.iter()
            .filter(|item| item.kind == concat_project::model::MediaKind::Video)
            .collect();
        let selected: Vec<_> = video_items.iter()
            .filter(|item| studio.media.selected.contains(&item.id))
            .collect();
        let source = if selected.len() == 1 {
            selected[0]
        } else if selected.is_empty() && video_items.len() == 1 {
            &video_items[0]
        } else {
            found = Err(if video_items.is_empty() {
                "No imported video. Use Concat Editor > Import first".into()
            } else {
                "Multiple videos imported: select ONE video tile on the left before automatic recap".into()
            });
            return;
        };
        let id = SystemTime::now()
            .duration_since(UNIX_EPOCH).map_or(0, |t| t.as_millis());
        let project_path = session.path().to_owned();
        let out = project_path.join("lmk-recaps").join(format!("recap-{id}"));
        found = Ok((
            PathBuf::from(&source.path),
            out,
            VoiceContext {
                speech: Arc::clone(&studio.host.speech),
                dirs: studio.host.dirs.clone(),
                project: project_path,
                preferred_voice: studio.prefs.tts_voice.unwrap_or(3),
            },
        ));
    });
    found
}

fn speak_with_concat(ctx: &VoiceContext, text: &str) -> Result<PathBuf, String> {
    if text.trim().is_empty() {
        return Err("AI narration script is empty; no voice can be synthesized".into());
    }
    let mut voice = ctx.preferred_voice;
    if tts::is_clone(voice) || tts::voice_family(voice).is_none() {
        // A saved/sample-clone requires a separate reference recording.
        voice = 3; // Kokoro af_heart, built into Concat's available voices.
    }
    let mut status = Speech::status(&ctx.dirs)?;
    let mut found = status.models.iter().find(|model| {
        model.downloaded && tts::voice_family(voice) == Some(model.family)
    }).map(|model| model.id.clone());
    if found.is_none() {
        voice = 3;
        let compact = "kokoro-int8-multi-lang-v1_0";
        ctx.speech.download_model(&ctx.dirs, compact, |_progress| {})?;
        status = Speech::status(&ctx.dirs)?;
        found = status.models.iter().find(|model| model.downloaded &&
            model.id == compact).map(|model| model.id.clone());
    }
    let model_id = found.ok_or("Concat speech model unavailable after download")?;
    let request = SpeakRequest {
        model_id,
        voice,
        reference: None,
        text: text.to_owned(),
        speed: 1.0,
        pauses: Some(0.2),
        steps: None,
        project: ctx.project.to_string_lossy().into_owned(),
    };
    let result = ctx.speech.speak(&ctx.dirs, &request, |_progress| {})?;
    Ok(PathBuf::from(result.path))
}

impl Job {
    fn validate(&self) -> Result<(), String> {
        if self.mode != 1 && self.mode != 2 && self.mode != 3 {
            return Err("Unsupported LMK tab".into());
        }
        if !self.source.is_file() {
            return Err(format!("Video not found: {}", self.source.display()));
        }
        if let Some(srt) = &self.subtitle {
            if !srt.is_file() {
                return Err(format!("Subtitle file not found: {}", srt.display()));
            }
        }
        if self.mode == 2 && self.use_ai {
            let url = if self.ai_url.trim().is_empty() {
                std::env::var("LMK_AI_BASE_URL").unwrap_or_default()
            } else { self.ai_url.clone() };
            let model = if self.ai_model.trim().is_empty() {
                std::env::var("LMK_AI_MODEL").unwrap_or_default()
            } else { self.ai_model.clone() };
            if url.is_empty() || model.is_empty() {
                return Err("Configure a text AI provider once (API URL + Model ID) to auto-write movie scripts".into());
            }
            if !(url.starts_with("https://") ||
                url.starts_with("http://127.0.0.1:") ||
                url.starts_with("http://localhost:")) {
                return Err("API URL must be HTTPS except localhost".into());
            }
        }
        if self.mode == 3 {
            if let Some(audio) = &self.replacement_audio {
                if !audio.is_file() { return Err(format!("Replacement audio not found: {}", audio.display())); }
                if self.license_note.trim().is_empty() {
                    return Err("Add an audio license/source note before using replacement audio".into());
                }
            }
        }
        if self.output.is_file() {
            return Err("Output must be a folder, not a file".into());
        }
        Ok(())
    }

    fn runtime_dir() -> Result<PathBuf, String> {
        if let Some(folder) = std::env::var_os("LMK_TOOLS_HOME") {
            let dir = PathBuf::from(folder);
            if dir.join("cli.py").is_file() { return Ok(dir); }
        }
        let exe = std::env::current_exe().map_err(|e| e.to_string())?;
        let parent = exe.parent().ok_or("Cannot resolve application folder")?;
        for ancestor in parent.ancestors() {
            for candidate in [ancestor.join("lmk-runtime"), ancestor.join("runtime")] {
                if candidate.join("cli.py").is_file() { return Ok(candidate); }
            }
        }
        Err("LMK backend missing. Set LMK_TOOLS_HOME to the runtime directory".into())
    }

    fn python(runtime: &Path) -> PathBuf {
        if let Some(path) = std::env::var_os("LMK_PYTHON") {
            return PathBuf::from(path);
        }
        let local = runtime.join(".venv").join("Scripts").join("python.exe");
        if local.is_file() { local } else { PathBuf::from("python") }
    }

    fn arguments(&self, runtime: &Path) -> Result<Vec<String>, String> {
        let mut args = vec![
            runtime.join("cli.py").to_string_lossy().into_owned(),
            if self.mode == 1 { "edit".into() } else if self.mode == 2 { "recap".into() } else { "rights".into() },
            "--input".into(), self.source.to_string_lossy().into_owned(),
            "--out".into(), self.output.to_string_lossy().into_owned(),
            "--aspect".into(), self.aspect.clone(),
            "--language".into(), self.language.clone(),
            "--model".into(), self.asr_model.clone(),
        ];
        if let Some(srt) = &self.subtitle {
            args.push("--srt".into());
            args.push(srt.to_string_lossy().into_owned());
        }
        // For English recap, generate narration with Concat's native Kokoro/Pocket
        // voices after FFmpeg has assembled the picture. Other languages
        // use the existing locale-aware speech backend.
        if self.voice && !(self.mode == 2 && self.language == "English") {
            args.push("--voice".into());
        }
        if self.mode == 1 {
            args.extend(["--rights".into(), self.rights.clone()]);
            if self.burn { args.push("--burn-subs".into()); }
            if self.mute { args.push("--mute-original".into()); }
            if !self.analysis.trim().is_empty() {
                std::fs::create_dir_all(&self.output).map_err(|e| e.to_string())?;
                let file = self.output.join("loi_binh_tu_viet.txt");
                // Prevent silently rewriting someone's existing text.
                if file.exists() {
                    return Err(format!("Original commentary file already exists: {}", file.display()));
                }
                std::fs::write(&file, &self.analysis).map_err(|e| e.to_string())?;
                args.push("--analysis-file".into());
                args.push(file.to_string_lossy().into_owned());
            }
        } else if self.mode == 2 {
            if self.use_ai {
                if !self.ai_url.is_empty() {
                    args.extend(["--api-url".into(), self.ai_url.clone()]);
                }
                if !self.ai_model.is_empty() {
                    args.extend(["--api-model".into(), self.ai_model.clone()]);
                }
            } else {
                // The CLI must not silently call an AI model from ambient env
                // when heuristic mode was explicitly selected.
                args.push("--no-ai".into());
            }
            args.push("--minutes".into());
            args.push(self.minutes.clamp(1, 10).to_string());
        } else {
            args.extend(["--rights".into(), self.rights.clone()]);
            if self.mute { args.push("--mute-original".into()); }
            if let Some(audio) = &self.replacement_audio {
                args.push("--replacement-audio".into());
                args.push(audio.to_string_lossy().into_owned());
                args.push("--license-note".into());
                args.push(self.license_note.clone());
            }
        }
        Ok(args)
    }

    fn run(self, voice_ctx: Option<VoiceContext>) -> Result<PathBuf, String> {
        self.validate()?;
        let runtime = Self::runtime_dir()?;
        let args = self.arguments(&runtime)?;
        let python = Self::python(&runtime);
        let mut cmd = Command::new(&python);
        cmd.args(&args);
        if self.mode == 2 && self.use_ai && !self.ai_key.is_empty() {
            cmd.env("LMK_AI_KEY", &self.ai_key);
        }
        let result = cmd
            .current_dir(&runtime)
            .stdin(Stdio::null())
            .output()
            .map_err(|e| format!("Could not start Python {}: {e}", python.display()))?;
        if !result.status.success() {
            let stderr = String::from_utf8_lossy(&result.stderr);
            let stdout = String::from_utf8_lossy(&result.stdout);
            let combined = format!("{stderr}\n{stdout}");
            let tail: String = combined.chars().rev().take(1300).collect::<String>()
                .chars().rev().collect();
            return Err(format!("LMK processing failed: {tail}"));
        }
        if self.mode == 2 && self.voice && self.language == "English" {
            let ctx = voice_ctx.ok_or("Concat voice context missing")?;
            let script = self.output.join("voice_script.txt");
            let text = std::fs::read_to_string(&script)
                .map_err(|e| format!("Cannot read AI narration script: {e}"))?;
            let wav = speak_with_concat(&ctx, &text)?;
            let result = Command::new(&python)
                .arg(runtime.join("cli.py"))
                .arg("mix")
                .arg("--input").arg(self.output.join("recap_video.mp4"))
                .arg("--out").arg(&self.output)
                .arg("--voice-file").arg(&wav)
                .current_dir(&runtime)
                .stdin(Stdio::null())
                .output()
                .map_err(|e| format!("Cannot merge Concat narration: {e}"))?;
            if !result.status.success() {
                return Err(format!("Cannot merge Concat voice into recap: {}",
                    String::from_utf8_lossy(&result.stderr)));
            }
        }
        let report = self.output.join("report.json");
        if !report.is_file() {
            return Err("Processing returned success but report.json was not produced".into());
        }
        Ok(report)
    }
}

pub fn bind(app: &App) {
    #[cfg(not(any(target_os = "android", target_os = "ios")))]
    app.on_lmk_pick(|kind| {
        let picked = match kind {
            1 => rfd::FileDialog::new()
                .add_filter("Video files", &["mp4", "mkv", "mov", "webm", "avi"])
                .pick_file(),
            2 => rfd::FileDialog::new().add_filter("Subtitles", &["srt"]).pick_file(),
            3 => rfd::FileDialog::new().pick_folder(),
            _ => None,
        };
        picked.map(|p| p.to_string_lossy().to_string()).unwrap_or_default().into()
    });
    #[cfg(any(target_os = "android", target_os = "ios"))]
    app.on_lmk_pick(|_| "".into());
    let weak = app.as_weak();
    app.on_lmk_run(move |form| {
        let mut job = Job {
            mode: form.mode,
            source: PathBuf::from(form.source.trim()),
            subtitle: (!form.subtitle.trim().is_empty()).then(|| PathBuf::from(form.subtitle.trim())),
            output: PathBuf::from(form.output.trim()),
            aspect: form.aspect.to_string(),
            language: form.language.to_string(),
            rights: form.rights.to_string(),
            voice: form.voice,
            burn: form.burn,
            mute: form.mute,
            minutes: form.minutes,
            analysis: form.analysis.to_string(),
            replacement_audio: (!form.replacement_audio.trim().is_empty())
                .then(|| PathBuf::from(form.replacement_audio.trim())),
            license_note: form.license_note.to_string(),
            use_ai: form.use_ai,
            ai_url: form.ai_url.to_string(),
            ai_model: form.ai_model.to_string(),
            ai_key: form.ai_key.to_string(),
            asr_model: form.asr_model.to_string(),
        };
        let mut voice_ctx = None;
        if job.mode == 2 {
            match recap_source_from_project() {
                Ok((source, output, context)) => {
                    job.source = source;
                    job.output = output;
                    job.subtitle = None;
                    voice_ctx = Some(context);
                }
                Err(error) => {
                    if let Some(app) = weak.upgrade() {
                        app.set_lmk_status(error.into());
                    }
                    return;
                }
            }
        }
        if let Err(error) = job.validate() {
            if let Some(app) = weak.upgrade() { app.set_lmk_status(error.into()); }
            return;
        }
        if let Some(app) = weak.upgrade() {
            if app.get_lmk_busy() { return; }
            app.set_lmk_busy(true);
            app.set_lmk_status("Processing video in the background...".into());
        }
        let callback = weak.clone();
        std::thread::spawn(move || {
            let result = job.run(voice_ctx);
            let _ = slint::invoke_from_event_loop(move || {
                if let Some(app) = callback.upgrade() {
                    app.set_lmk_busy(false);
                    match result {
                        Ok(report) => {
                            let dest = std::fs::read_to_string(&report).ok()
                                .and_then(|raw| serde_json::from_str::<serde_json::Value>(&raw).ok())
                                .and_then(|v| v.get("output").and_then(|p| p.as_str()).map(PathBuf::from));
                            if let Some(video) = dest.filter(|path| path.is_file()) {
                                // Import finished video back into the currently open Concat
                                // project. The original media and its timeline are untouched.
                                Shell::with(|shell, _| {
                                    shell.studio.borrow_mut().handle(crate::panes::Msg::Media(
                                        crate::panes::media_bin::MediaMsg::Import(vec![video])
                                    ));
                                });
                            }
                            app.set_lmk_status(
                                format!("Recap completed and imported. Report: {}", report.display()).into());
                        },
                        Err(error) => app.set_lmk_status(format!("Error: {error}").into()),
                    }
                }
            });
        });
    });
}
