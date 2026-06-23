# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Project

**MP3 Tag Editor** — a Windows desktop app for batch-editing MP3 (ID3) metadata.
GUI is built with **customtkinter**; tag I/O uses **mutagen**; cover-art preview uses **Pillow**.
The app supports Thai filenames/tags, dark/light themes, a recursive folder tree, and
per-file editing with explicit bulk actions.

UI strings and user-facing docs are mostly Thai; code, identifiers, and comments are English.

## Commands

This project uses a local virtualenv at `.venv/`. Prefer the venv interpreter.

```bash
# Run the app
.venv/Scripts/python.exe main.py

# Syntax-check after edits (fast, no GUI)
.venv/Scripts/python.exe -m py_compile main.py tag_utils.py

# Install / update deps
.venv/Scripts/pip.exe install -r requirements.txt

# Build a single-file Windows EXE -> dist/MP3TagEditor.exe
pyinstaller --onefile --windowed --name=MP3TagEditor main.py   # or: build.bat
```

There are no automated tests. After changing UI or tag logic, `py_compile` then launch the
app to verify behavior manually. If a previous run is stuck, kill stray interpreters with
`taskkill /F /IM python.exe` before relaunching.

## Architecture

Two modules, clean separation:

- **`tag_utils.py`** — pure logic, no UI. Filesystem scanning + ID3 read/write/cover/rename
  helpers. Everything here should stay importable and side-effect-free at module load. Key
  pieces: `FRAME_MAP` (field → ID3 frame), `list_mp3_tree()` (recursive scan →
  `MP3TreeEntry` list), `load_mp3_tags()` / `save_tags()`, cover helpers, `rename_mp3_file()`,
  and `_try_fix_thai_encoding()`.
- **`main.py`** — all UI. `App(ctk.CTk)` is the root; `_LoadingOverlay`, `_VirtualTree` /
  `_PooledRow`, and `_ConfirmDialog` are the widgets. `App` owns window setup, the folder
  tree, per-file drafts, and every user action (`_save`, `_rename_selected_file`,
  `_fill_titles`, `_apply_cover`, `_remove_cover`).

`AI-HANDOFF.md` and the `README.md` carry additional context on intended behavior — read them
when a change touches save/rename/tree logic.

## Conventions & invariants — keep these intact

**1. Background threading for all disk I/O.** Tag loading, saving, fill, cover, and folder
scans run on a daemon thread; UI updates marshal back via `self.after(0, ...)`. Never call
`load_mp3_tags`/`save_*` directly on the Tk main thread. Long loads use a cancel token
(`threading.Event`) so a newer selection aborts the previous one. Reuse this pattern for any
new long-running action, and show `self._loading_overlay` for folder-scale work.

**2. Per-file drafts — no broadcast.** Each file keeps its own in-memory draft in
`self._file_drafts`. Switching files stores the current form into the active file's draft and
loads the next file's draft (or disk). `Save Selected Files` writes **each file's own draft**
via `_build_save_drafts()` — it must **not** copy the visible form onto every checked file.
Preserve this unless deliberately adding an explicit "apply to all checked" action.

**3. Adding a new editable tag field touches several places** — update all of them:
- `tag_utils.py`: `FRAME_MAP` (add the ID3 frame class + import it from `mutagen.id3`),
  and the dict in `load_mp3_tags()`.
- `main.py`: `FIELDS`, `FIELD_LAYOUT` (grid placement + colspan), `FIELD_LABELS`.
- Verify `save_tags()` handles it (it iterates `form_data` against `FRAME_MAP`).

**4. Colors are theme tuples, never hardcoded hex.** Use the `C_*` tokens (e.g. `C_ACCENT`,
`C_SURFACE`, `C_TEXT`) defined at the top of `main.py`. Each is `("#light", "#dark")` so
customtkinter auto-switches with the appearance mode. New UI must use these tokens, not raw
colors.

**5. Thai support is load-bearing.** `save_tags()` always writes `encoding=3` (UTF-8).
`_try_fix_thai_encoding()` repairs legacy cp874/TIS-620 tags mis-stored as Latin-1 — don't
strip it. Fonts are chosen from `THAI_FONT_PRIORITY` via `_detect_font_family()`; keep using
the detected `CTkFont` for any text that may contain Thai.

**6. Reads never write.** `load_mp3_tags()` catches `ID3NoHeaderError` and returns empty
strings rather than creating an ID3 header. Keep reads side-effect-free; only explicit
save/cover/rename actions touch disk.

**7. The folder tree is virtualized — state lives in the model, not widgets.** The tree
renders only the rows in the viewport via a recycled pool (`_VirtualTree` + `_PooledRow`),
so it stays smooth for 1000+ files. Per-row state is plain data on `App`
(`self._tree_entries`, `self._file_entries`, `self._folder_entries`, `self._checked` keyed by
file path, `self._expanded` keyed by folder relpath, `self._folder_descendants`). The pooled
row widgets are stateless: `App._bind_tree_row()` paints each one from the model on demand, so
**never store per-entry state on a row** (it gets recycled during scroll). After any model
change, call `self._tree.refresh_visible()` (re-paint visible rows) or `self._refresh_tree()`
(recompute the flattened visible list — for expand/collapse and search). Row height is fixed
(`_TREE_ROW_HEIGHT`); the offset↔index math depends on it. The fill-containers
(`content`/`_file_panel`/`_VirtualTree`/`_body`) have geometry propagation disabled via
`_lock_fill_layout()` once the window is mapped — without it the place()d rows (no requested
height) let the panel collapse; don't re-enable propagation on them.

## Gotchas

- `save_tags()` skips empty values (`if not value: continue`), so saving cannot *clear* an
  existing tag by blanking the field. If clearing is ever needed, that logic must change
  explicitly.
- Layout grids rely on `columnconfigure(weight=...)`; when adding fields keep colspans in
  `FIELD_LAYOUT` consistent with the 4-column grid.
- `rename_mp3_file()` blocks the Windows-invalid characters `<>:"/\|?*` and refuses to clobber
  an existing file — preserve those guards.
- DPI awareness is set on Windows *before* importing customtkinter (top of `main.py`); don't
  move that block.
