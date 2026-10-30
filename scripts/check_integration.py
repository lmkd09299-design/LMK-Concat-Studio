"""Fast CI guards. Native Rust/Slint still require the Windows compilation job."""
from pathlib import Path
import argparse

ROOT = Path(__file__).resolve().parents[1]


def check(path: Path | None):
    ui = (ROOT / "native/ui/lmk-tools.slint").read_text(encoding="utf-8")
    rust = (ROOT / "native/rust/lmk.rs").read_text(encoding="utf-8")
    patch = (ROOT / "apply_fork.py").read_text(encoding="utf-8")
    assert 'import { ScrollView } from "std-widgets.slint";' in ui, "Missing Slint ScrollView import"
    assert 'ScrollView {' in ui
    assert "callback run-job(request: LmkRequest);" in ui
    assert 'label: "BAN QUYEN & AUDIO";' in ui
    assert 'root.active == 3' in ui
    assert 'replacement_audio:' in ui
    assert 'replacement_audio:' in rust or 'replacement_audio' in rust
    assert '"rights".into()' in rust
    assert 'callback browse(kind: int) -> string;' in ui
    assert 'root.browse(1)' in ui
    assert 'Oxion Model ID' in ui
    assert 'https://www.oxionai.com/v1' in ui
    assert 'remember_oxion_key:' in ui
    assert 'remember_oxion_key:' in rust
    assert 'remember-oxion-key' in rust
    assert 'remember-oxion-key' in (ROOT / 'runtime/cli.py').read_text(encoding='utf-8')
    assert 'CryptProtectData' in (ROOT / 'runtime/core/oxion_keys.py').read_text(encoding='utf-8')
    assert 'app.on_lmk_pick' in rust
    assert 'LMK_AI_KEY' in rust
    assert 'recap_source_from_project' in rust
    assert 'studio.project().media.iter()' in rust
    assert 'Speech::status' in rust
    assert 'speak_with_concat' in rust
    assert 'recap_concat_voice.mp4' in (ROOT / 'runtime/cli.py').read_text(encoding='utf-8')
    assert 'voice_script.txt' in (ROOT / 'runtime/core/recap.py').read_text(encoding='utf-8')
    assert 'TU DONG RECAP' in ui
    assert 'callback lmk-pick(kind: int) -> string;' in patch
    assert "app.on_lmk_run" in rust
    assert "LMK-NATIVE-FORK-v4" in patch
    if path:
        app = (path / 'src/crates/concat/ui/app.slint').read_text(encoding='utf-8')
        lib = (path / 'src/crates/concat/src/lib.rs').read_text(encoding='utf-8')
        assert 'import { LmkNav, LmkTools, LmkRequest } from "lmk-tools.slint";' in app
        assert 'lmk::bind(&app)' in lib
        assert 'mod lmk;' in lib
        assert 'title: "LMK Concat Studio";' in app
    print('Fast integration checks passed. Full native validation happens in GitHub Actions.')


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--patched', type=Path)
    check(p.parse_args().patched)
