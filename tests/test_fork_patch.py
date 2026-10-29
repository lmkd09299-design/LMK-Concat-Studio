from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from apply_fork import patch


class TestNativeForkPatch(unittest.TestCase):
    def mock_upstream(self, folder: Path):
        ui = folder / 'src/crates/concat/ui'
        src = folder / 'src/crates/concat/src'
        ui.mkdir(parents=True)
        src.mkdir(parents=True)
        (ui/'app.slint').write_text('''import { Editor } from "editor.slint";
export {
    Curves,
}
export component App inherits Window {
    title: "Concat";
            if root.on-start: StartScreen {
            }
            if !root.on-start && !root.phone: Workspace {
                vertical-stretch: 1;
            }
}
''')
        (src/'lib.rs').write_text('''mod keymap;
fn build() {
    let app = App::new()?;
}
''')
        (folder/'src/crates/concat/build.rs').write_text('''.set("ProductName", "Concat")
.set("FileDescription", "Concat")
''')
        return ui, src

    def test_patch_inserts_native_tabs_and_is_idempotent(self):
        with TemporaryDirectory() as d:
            root = Path(d)
            ui, src = self.mock_upstream(root)
            patch(root)
            app=(ui/'app.slint').read_text()
            rust=(src/'lib.rs').read_text()
            self.assertIn('LmkTools',app)
            self.assertIn('LmkRequest } from',app)
            self.assertIn('callback lmk-run(request: LmkRequest);',app)
            self.assertIn('LmkNav',app)
            self.assertIn('lmk::bind(&app)',rust)
            self.assertTrue((src/'lmk.rs').exists())
            self.assertTrue((ui/'lmk-tools.slint').exists())
            patch(root) # should neither change source nor duplicate content
            self.assertEqual(app,(ui/'app.slint').read_text())

    def test_wrong_upstream_does_not_edit_anything(self):
        with TemporaryDirectory() as d:
            root=Path(d)
            ui, src = self.mock_upstream(root)
            source=(ui/'app.slint').read_text().replace('Editor }','Other }')
            (ui/'app.slint').write_text(source)
            with self.assertRaises(RuntimeError): patch(root)
            self.assertEqual(source,(ui/'app.slint').read_text())
            self.assertFalse((src/'lmk.rs').exists())

if __name__ == '__main__': unittest.main()
