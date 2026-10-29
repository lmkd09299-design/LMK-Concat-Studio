"""Patch a pinned Concat source checkout into the native LMK Concat fork.

No dependency other than Python stdlib. Fails closed if upstream changed.
This is NOT an MCP launcher or a second GUI.
"""
from pathlib import Path
import argparse
import hashlib
import shutil
import sys

ROOT = Path(__file__).resolve().parent
MARKER = '// LMK-NATIVE-FORK-v4'


def replace_once(data: str, needle: str, value: str, source: str) -> str:
    matches = data.count(needle)
    if matches != 1:
        raise RuntimeError(f'{source}: expected one anchor {needle[:70]!r}, found {matches}')
    return data.replace(needle, value, 1)


def patch(source: Path):
    source = source.resolve()
    app_path = source / 'src/crates/concat/ui/app.slint'
    lib_path = source / 'src/crates/concat/src/lib.rs'
    build_path = source / 'src/crates/concat/build.rs'
    if not (app_path.is_file() and lib_path.is_file()):
        raise RuntimeError('Expected complete Concat source checkout under vendor/Concat')

    app = app_path.read_text(encoding='utf-8')
    lib = lib_path.read_text(encoding='utf-8')
    build = build_path.read_text(encoding='utf-8')
    if MARKER in app and MARKER in lib:
        print('LMK native fork already applied. Nothing overwritten.')
        return
    if MARKER in app or MARKER in lib:
        raise RuntimeError('Partial fork detected: restore clean upstream source before retrying')

    app = replace_once(
        app, 'import { Editor } from "editor.slint";',
        'import { Editor } from "editor.slint";\nimport { LmkNav, LmkTools, LmkRequest } from "lmk-tools.slint";',
        'app.slint import')
    app = replace_once(app, '    title: "Concat";',
                       '    title: "LMK Concat Studio";', 'app.slint product title')
    app = replace_once(
        app, 'export component App inherits Window {',
        'export component App inherits Window {\n'
        '    // LMK-NATIVE-FORK-v4: native integrated tools.\n'
        '    in-out property <int> lmk-page: 0;\n'
        '    in property <bool> lmk-busy: false;\n'
        '    in property <string> lmk-status: "Ready to process files you may use";\n'
        '    callback lmk-run(request: LmkRequest);',
        'app.slint root')
    editor = '''            if !root.on-start && !root.phone: Workspace {
                vertical-stretch: 1;
            }'''
    injected = '''            // LMK-NATIVE-FORK-v4: Concat timeline and LMK tools share the same window.
            if !root.on-start && !root.phone: HorizontalLayout {
                vertical-stretch: 1;
                spacing: 0px;
                Workspace {
                    horizontal-stretch: 1;
                }
                if root.lmk-page != 0: LmkTools {
                    width: 428px;
                    page: root.lmk-page;
                    busy: root.lmk-busy;
                    job-status: root.lmk-status;
                    run-job(request) => { root.lmk-run(request); }
                }
            }'''
    app = replace_once(app, editor, injected, 'app.slint workspace')
    app = replace_once(app, 'export {\n    Curves,',
                       'export {\n    LmkRequest,\n    Curves,',
                       'app.slint request struct export')
    toolbar_marker = '            if root.on-start: StartScreen {'
    toolbar = '''            if !root.on-start && !root.phone: LmkNav {
                active: root.lmk-page;
                select(page) => { root.lmk-page = page; }
            }

'''+toolbar_marker
    app = replace_once(app, toolbar_marker, toolbar, 'app.slint toolbar')

    lib = replace_once(lib, 'mod keymap;', 'mod keymap;\n// LMK-NATIVE-FORK-v4: native editor integration.\nmod lmk;', 'lib.rs module')
    lib = replace_once(lib, '    let app = App::new()?;',
                       '    let app = App::new()?;\n    lmk::bind(&app);',
                       'lib.rs hook')

    build = replace_once(build, '.set("ProductName", "Concat")',
                         '.set("ProductName", "LMK Concat Studio")',
                         'build.rs product name')
    build = replace_once(build, '.set("FileDescription", "Concat")',
                         '.set("FileDescription", "LMK Concat Studio")',
                         'build.rs executable description')

    # Write only after all source anchors were verified.
    ui_dest = source / 'src/crates/concat/ui/lmk-tools.slint'
    rust_dest = source / 'src/crates/concat/src/lmk.rs'
    for dest in (ui_dest, rust_dest):
        if dest.exists():
            raise RuntimeError(f'Won\'t overwrite existing fork source: {dest}')
    ui_dest.write_bytes((ROOT / 'native/ui/lmk-tools.slint').read_bytes())
    rust_dest.write_bytes((ROOT / 'native/rust/lmk.rs').read_bytes())
    app_path.write_text(app, encoding='utf-8')
    lib_path.write_text(lib, encoding='utf-8')
    build_path.write_text(build, encoding='utf-8')
    print('Native LMK Slint tab panels and Rust command bridge merged into Concat source.')
    print('Patched paths:', app_path, lib_path, ui_dest, rust_dest, sep='\n  ')


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--source', default='vendor/Concat')
    args = p.parse_args()
    patch(Path(args.source))


if __name__ == '__main__':
    main()
