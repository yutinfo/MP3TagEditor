# AI Handoff

## Current Status
- Project: `MP3TagEditor`
- Latest committed version: `0f61268` (`Initial version`)
- Current uncommitted work exists in:
  - `main.py`
  - `tag_utils.py`
  - `requirements.txt`

## What Is Implemented
- Desktop app with `customtkinter`
- Recursive MP3 loading from nested folders
- Tree view on the left with:
  - collapsible folders
  - folder checkbox to select all files in that branch
  - file checkbox per MP3
  - file count per folder branch
- Tag editing for:
  - `Title`
  - `Artist`
  - `Album`
  - `Year`
  - `Track`
  - `Genre`
- Bulk `Fill Title from Filename`
- Cover art support (`APIC`)
  - preview current embedded cover
  - choose JPG/PNG
  - apply cover to checked files
  - remove cover from checked files
- Rename support
  - `Rename` field above `Title`
  - `Rename File` button for selected file
  - `Use Rename` button to copy rename text into title
- Custom themed confirm popup using `customtkinter`

## Important Save Logic
- Save behavior was changed from "broadcast current visible form to all checked files"
- Current design now uses **per-file drafts**
- Each file keeps its own draft in memory via `self._file_drafts` in `main.py`
- When switching selected file:
  - current form is stored into that file's draft
  - next file loads from its draft if available, otherwise from disk
- When clicking `Save Selected Files`:
  - app saves each checked file using that file's own draft
  - it does **not** copy the current screen values to every checked file automatically

## Important Rename Logic
- Rename changes only the filename, not tags automatically
- Rename keeps `.mp3` extension
- Rename blocks invalid Windows filename characters
- After rename:
  - tree reloads
  - selection tries to follow the renamed file
  - checked-state is restored as much as possible

## Important Cover Logic
- Cover art uses ID3 `APIC`
- Preview uses `Pillow`
- `requirements.txt` now includes `Pillow`
- If preview-related issues happen, inspect `_update_cover_preview()` in `main.py`

## Main Files
- `main.py`
  - UI
  - tree behavior
  - per-file draft handling
  - rename flow
  - confirm dialog
- `tag_utils.py`
  - MP3 tree scanning
  - ID3 read/write
  - cover art helpers
  - rename helper
- `requirements.txt`
  - includes `customtkinter`, `mutagen`, `pyinstaller`, `Pillow`

## Key Methods To Know
- `main.py`
  - `_load_folder(...)`
  - `_on_file_select(...)`
  - `_store_current_file_draft()`
  - `_build_save_drafts(...)`
  - `_save()`
  - `_rename_selected_file()`
  - `_fill_titles()`
  - `_apply_cover()`
  - `_remove_cover()`
- `tag_utils.py`
  - `list_mp3_tree(...)`
  - `load_mp3_tags(...)`
  - `save_tags(...)`
  - `save_tag_drafts_to_files(...)`
  - `fill_titles_from_filenames(...)`
  - `get_cover_art(...)`
  - `apply_cover_to_files(...)`
  - `remove_cover_from_files(...)`
  - `rename_mp3_file(...)`

## Known Design Direction
- App is moving toward:
  - file-explorer-like tree
  - per-file editing
  - explicit bulk actions instead of hidden broadcast behavior

## Things To Be Careful About Next
- If adding new editable fields, update:
  - `FIELDS`
  - `FIELD_LAYOUT`
  - `FIELD_LABELS`
  - tag read/write helpers in `tag_utils.py`
- If changing save logic, preserve per-file draft behavior unless intentionally redesigning it
- If changing rename behavior, check interactions with:
  - selected file
  - checked files
  - `_file_drafts`
- If changing tree behavior, verify:
  - folder selection state
  - collapsed visibility
  - restored selection after reload

## Suggested Next Improvement
- Add an explicit bulk-apply mode such as:
  - `Apply current field to checked files`
- Reason:
  - current save is now safe for per-file data
  - but there is no clean explicit bulk-edit path for non-title fields yet
