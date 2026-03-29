from __future__ import annotations

import io
import os
import sys
import threading
import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog
from typing import Callable, Dict, List, Optional

# Windows DPI awareness constant (PROCESS_SYSTEM_DPI_AWARE)
_DPI_AWARENESS_CONTEXT_SYSTEM_AWARE = 1

# Startup rendering timing constant (milliseconds)
_WINDOW_DEICONIFY_DELAY_MS = 100

# Tk scaling factor for DPI blur prevention
_TK_SCALING_FACTOR = 1.0

# Enable high-DPI awareness on Windows BEFORE importing customtkinter
# This prevents scaling blurriness and rendering artifacts
if sys.platform == "win32":
    import ctypes
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(_DPI_AWARENESS_CONTEXT_SYSTEM_AWARE)
    except (OSError, AttributeError):
        # DPI awareness API may not be available on older Windows versions
        pass

import customtkinter as ctk
try:
    from PIL import Image, ImageOps, ImageTk
except ImportError:
    Image = None
    ImageOps = None
    ImageTk = None

from tag_utils import (
    build_title_from_filename,
    CoverArt,
    MP3TreeEntry,
    apply_cover_to_files,
    fill_titles_from_filenames,
    get_cover_art,
    list_mp3_tree,
    load_mp3_tags,
    rename_mp3_file,
    remove_cover_from_files,
    save_tag_drafts_to_files,
)


ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


THAI_FONT_PRIORITY = ["Leelawadee UI", "Tahoma", "Segoe UI", "Arial Unicode MS"]
FIELDS = ["title", "artist", "album", "year", "track", "genre"]
FIELD_LAYOUT = [
    [("title", "Title", 4)],
    [("artist", "Artist", 2), ("album", "Album", 2)],
    [("year", "Year", 1), ("track", "Track", 1), ("genre", "Genre", 2)],
]
FIELD_LABELS = {
    "title": "Title",
    "artist": "Artist",
    "album": "Album",
    "year": "Year",
    "track": "Track",
    "genre": "Genre",
}

C_BG = ("#f1f5f9", "#0d1117")
C_SURFACE = ("#ffffff", "#161b22")
C_SURFACE_ALT = ("#f8fafc", "#1c2230")
C_BORDER = ("#e2e8f0", "#30363d")
C_TEXT = ("#0f172a", "#e6edf3")
C_MUTED = ("#64748b", "#8b949e")
C_ACCENT = ("#2563eb", "#3b82f6")
C_ACCENT_HOVER = ("#1d4ed8", "#60a5fa")
C_SUCCESS = ("#16a34a", "#22c55e")
C_SUCCESS_HOVER = ("#15803d", "#4ade80")
C_ROW_SELECTED = ("#dbeafe", "#1d3a6e")
C_ROW_HOVER = ("#eef4ff", "#1a2744")
C_DOT_OK = ("#22c55e", "#22c55e")
C_DOT_BUSY = ("#f59e0b", "#f59e0b")
C_DOT_ERROR = ("#ef4444", "#ef4444")


class App(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()

        # Prevent showing uninitialized window state during widget construction
        self.withdraw()

        # Disable DPI scaling to prevent blur/flicker on high-DPI displays
        self.tk.call('tk', 'scaling', _TK_SCALING_FACTOR)

        self.title("MP3 Tag Editor")
        self.geometry("1080x700")
        self.minsize(860, 560)
        self.configure(fg_color=C_BG)

        self._font_family = self._detect_font_family()
        self._font = ctk.CTkFont(family=self._font_family, size=13)
        self._font_small = ctk.CTkFont(family=self._font_family, size=12)
        self._font_xsmall = ctk.CTkFont(family=self._font_family, size=11)
        self._font_heading = ctk.CTkFont(
            family=self._font_family, size=13, weight="bold"
        )

        self._folder_path = ""
        self._selected_file: Optional[str] = None
        self._selected_cover: Optional[CoverArt] = None
        self._pending_cover_path: Optional[str] = None
        self._pending_cover_name = ""
        self._cover_preview_image = None
        self._cover_preview_photo = None
        self._rename_entry: Optional[ctk.CTkEntry] = None
        self._file_drafts: Dict[str, Dict[str, str]] = {}
        self._all_rows: List[_TreeRowBase] = []
        self._file_rows: List[_FileRow] = []
        self._folder_rows: Dict[str, _FolderRow] = {}
        self._folder_descendants: Dict[str, List[_FileRow]] = {}
        self._cancel_load = threading.Event()

        self._build_ui()

    def _detect_font_family(self) -> str:
        available_fonts = set(tkfont.families(self))
        for font_name in THAI_FONT_PRIORITY:
            if font_name in available_fonts:
                return font_name
        return "TkDefaultFont"

    def _build_ui(self) -> None:
        self._build_topbar()

        content = ctk.CTkFrame(self, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=12, pady=(8, 0))
        content.columnconfigure(0, weight=5, minsize=280)
        content.columnconfigure(1, weight=7, minsize=420)
        content.rowconfigure(0, weight=1)

        self._build_file_panel(content)
        self._build_editor_panel(content)
        self._build_status_bar()

    def _build_topbar(self) -> None:
        bar = ctk.CTkFrame(self, height=56, corner_radius=0, fg_color=C_SURFACE)
        bar.pack(fill="x")
        bar.pack_propagate(False)

        ctk.CTkLabel(
            bar,
            text="MP3 Tag Editor",
            font=self._font_heading,
            text_color=C_TEXT,
            anchor="w",
        ).pack(side="left", padx=(18, 0))

        ctk.CTkFrame(bar, width=1, fg_color=C_BORDER).pack(
            side="left", fill="y", padx=14, pady=10
        )

        ctk.CTkButton(
            bar,
            text="Open Folder",
            font=self._font_small,
            fg_color=C_ACCENT,
            hover_color=C_ACCENT_HOVER,
            text_color=("white", "white"),
            width=132,
            height=36,
            corner_radius=8,
            command=self._pick_folder,
        ).pack(side="left", pady=8)

        self._path_label = ctk.CTkLabel(
            bar,
            text="No folder selected",
            font=self._font_small,
            text_color=C_MUTED,
            anchor="w",
        )
        self._path_label.pack(side="left", fill="x", expand=True, padx=(12, 0))

        self._mode_button = ctk.CTkButton(
            bar,
            text="Light",
            font=self._font_small,
            fg_color="transparent",
            hover_color=C_SURFACE_ALT,
            text_color=C_MUTED,
            width=72,
            height=36,
            corner_radius=8,
            command=self._toggle_mode,
        )
        self._mode_button.pack(side="right", padx=(0, 14))

        ctk.CTkFrame(self, height=1, fg_color=C_BORDER, corner_radius=0).pack(fill="x")

    def _build_file_panel(self, parent: ctk.CTkFrame) -> None:
        panel = ctk.CTkFrame(
            parent,
            fg_color=C_SURFACE,
            corner_radius=12,
            border_width=1,
            border_color=C_BORDER,
        )
        panel.grid(row=0, column=0, sticky="nsew", padx=(0, 6), pady=(0, 8))
        panel.rowconfigure(2, weight=1)
        panel.columnconfigure(0, weight=1)

        header = ctk.CTkFrame(panel, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=14, pady=(12, 0))
        header.columnconfigure(1, weight=1)

        ctk.CTkLabel(
            header,
            text="Folder Tree",
            font=self._font_heading,
            text_color=C_TEXT,
        ).grid(row=0, column=0, sticky="w")

        self._tree_badge = ctk.CTkLabel(
            header,
            text="0 files",
            font=self._font_xsmall,
            text_color=C_MUTED,
            fg_color=C_SURFACE_ALT,
            corner_radius=8,
            width=64,
            height=22,
        )
        self._tree_badge.grid(row=0, column=1, sticky="w", padx=(8, 0))

        self._select_all_button = ctk.CTkButton(
            header,
            text="Select All",
            font=self._font_xsmall,
            fg_color="transparent",
            hover_color=C_SURFACE_ALT,
            text_color=C_MUTED,
            border_width=1,
            border_color=C_BORDER,
            width=96,
            height=28,
            corner_radius=7,
            command=self._toggle_all,
        )
        self._select_all_button.grid(row=0, column=2, sticky="e")

        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", lambda *_: self._apply_tree_visibility())

        ctk.CTkEntry(
            panel,
            textvariable=self._search_var,
            placeholder_text="Filter files or folders",
            font=self._font_small,
            fg_color=C_SURFACE_ALT,
            border_color=C_BORDER,
            text_color=C_TEXT,
            placeholder_text_color=C_MUTED,
            height=36,
            corner_radius=8,
        ).grid(row=1, column=0, sticky="ew", padx=12, pady=(8, 6))

        self._tree_frame = ctk.CTkScrollableFrame(
            panel,
            fg_color=C_SURFACE,
            scrollbar_button_color=C_BORDER,
            scrollbar_button_hover_color=C_MUTED,
            corner_radius=0,
        )
        self._tree_frame.grid(row=2, column=0, sticky="nsew", padx=6, pady=(0, 8))
        self._tree_frame.columnconfigure(0, weight=1)

    def _build_editor_panel(self, parent: ctk.CTkFrame) -> None:
        panel = ctk.CTkFrame(
            parent,
            fg_color=C_SURFACE,
            corner_radius=12,
            border_width=1,
            border_color=C_BORDER,
        )
        panel.grid(row=0, column=1, sticky="nsew", padx=(6, 0), pady=(0, 8))
        panel.rowconfigure(1, weight=1)
        panel.columnconfigure(0, weight=1)

        header = ctk.CTkFrame(panel, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=16, pady=(12, 0))
        header.columnconfigure(1, weight=1)

        ctk.CTkLabel(
            header,
            text="Tag Editor",
            font=self._font_heading,
            text_color=C_TEXT,
        ).grid(row=0, column=0, sticky="w")

        self._selected_label = ctk.CTkLabel(
            header,
            text="No file selected",
            font=self._font_xsmall,
            text_color=C_MUTED,
            anchor="e",
        )
        self._selected_label.grid(row=0, column=1, sticky="e")

        editor_body = ctk.CTkFrame(panel, fg_color="transparent")
        editor_body.grid(row=1, column=0, sticky="nsew")
        editor_body.rowconfigure(0, weight=1)
        editor_body.columnconfigure(0, weight=1)

        self._entries: Dict[str, ctk.CTkEntry] = {}
        self._build_fields(editor_body)

    def _build_fields(self, parent: ctk.CTkFrame) -> None:
        content = ctk.CTkFrame(parent, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=16, pady=(10, 0))
        content.rowconfigure(1, weight=1)
        content.columnconfigure(0, weight=3, uniform="editor")
        content.columnconfigure(1, weight=2, uniform="editor")

        fields_container = ctk.CTkFrame(content, fg_color="transparent")
        fields_container.grid(row=0, column=0, rowspan=2, sticky="nsew", padx=(0, 12))

        self._build_rename_row(fields_container)

        for group in FIELD_LAYOUT:
            row = ctk.CTkFrame(fields_container, fg_color="transparent")
            row.pack(fill="x", pady=(0, 8))

            for column_index, (_, _, span) in enumerate(group):
                row.columnconfigure(column_index, weight=span, uniform="fields")

            for column_index, (field_name, label, _) in enumerate(group):
                field_frame = ctk.CTkFrame(row, fg_color="transparent")
                field_frame.grid(
                    row=0,
                    column=column_index,
                    sticky="ew",
                    padx=(0, 8) if column_index < len(group) - 1 else (0, 0),
                )

                if field_name == "title":
                    self._build_title_action(field_frame)
                else:
                    ctk.CTkLabel(
                        field_frame,
                        text=label,
                        font=self._font_xsmall,
                        text_color=C_MUTED,
                        anchor="w",
                    ).pack(anchor="w", pady=(0, 4))

                entry = ctk.CTkEntry(
                    field_frame,
                    font=self._font,
                    fg_color=C_SURFACE_ALT,
                    border_color=C_BORDER,
                    text_color=C_TEXT,
                    placeholder_text_color=C_MUTED,
                    height=38,
                    corner_radius=8,
                )
                entry.pack(fill="x")
                self._entries[field_name] = entry

        self._build_cover_panel(content)

        action_bar = ctk.CTkFrame(parent, fg_color="transparent")
        action_bar.pack(fill="x", padx=16, pady=(16, 16), side="bottom")
        action_bar.columnconfigure(0, weight=3)
        action_bar.columnconfigure(1, weight=2)

        ctk.CTkButton(
            action_bar,
            text="Fill Title from Filename",
            font=self._font_small,
            fg_color="transparent",
            hover_color=C_SURFACE_ALT,
            text_color=C_MUTED,
            border_width=1,
            border_color=C_BORDER,
            height=42,
            corner_radius=8,
            command=self._fill_titles,
        ).grid(row=0, column=0, sticky="ew", padx=(0, 8))

        self._save_button = ctk.CTkButton(
            action_bar,
            text="Save Selected Files",
            font=self._font_heading,
            fg_color=C_SUCCESS,
            hover_color=C_SUCCESS_HOVER,
            text_color=("white", "white"),
            height=42,
            corner_radius=8,
            command=self._save,
        )
        self._save_button.grid(row=0, column=1, sticky="ew")

    def _build_rename_row(self, parent: ctk.CTkFrame) -> None:
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=(0, 8))
        row.columnconfigure(0, weight=1)
        row.columnconfigure(1, weight=0)

        field_frame = ctk.CTkFrame(row, fg_color="transparent")
        field_frame.grid(row=0, column=0, sticky="ew", padx=(0, 8))

        ctk.CTkLabel(
            field_frame,
            text="Rename",
            font=self._font_xsmall,
            text_color=C_MUTED,
            anchor="w",
        ).pack(anchor="w", pady=(0, 4))

        self._rename_entry = ctk.CTkEntry(
            field_frame,
            font=self._font,
            fg_color=C_SURFACE_ALT,
            border_color=C_BORDER,
            text_color=C_TEXT,
            placeholder_text="New filename without .mp3",
            placeholder_text_color=C_MUTED,
            height=38,
            corner_radius=8,
        )
        self._rename_entry.pack(fill="x")

        ctk.CTkButton(
            row,
            text="Rename File",
            font=self._font_small,
            fg_color="transparent",
            hover_color=C_SURFACE_ALT,
            text_color=C_MUTED,
            border_width=1,
            border_color=C_BORDER,
            height=38,
            width=112,
            corner_radius=8,
            command=self._rename_selected_file,
        ).grid(row=0, column=1, sticky="se")

    def _build_title_action(self, parent: ctk.CTkFrame) -> None:
        label_row = ctk.CTkFrame(parent, fg_color="transparent")
        label_row.pack(fill="x", pady=(0, 4))
        label_row.columnconfigure(0, weight=1)

        ctk.CTkLabel(
            label_row,
            text="Title",
            font=self._font_xsmall,
            text_color=C_MUTED,
            anchor="w",
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkButton(
            label_row,
            text="Use Rename",
            font=self._font_xsmall,
            fg_color="transparent",
            hover_color=C_SURFACE_ALT,
            text_color=C_ACCENT,
            border_width=1,
            border_color=C_BORDER,
            height=24,
            width=92,
            corner_radius=7,
            command=self._use_rename_as_title,
        ).grid(row=0, column=1, sticky="e")

    def _build_cover_panel(self, parent: ctk.CTkFrame) -> None:
        cover_panel = ctk.CTkFrame(
            parent,
            fg_color=C_SURFACE_ALT,
            border_width=1,
            border_color=C_BORDER,
            corner_radius=12,
        )
        cover_panel.grid(row=0, column=1, sticky="nsew")
        cover_panel.grid_columnconfigure(0, weight=1)
        cover_panel.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(
            cover_panel,
            text="Cover Art",
            font=self._font_heading,
            text_color=C_TEXT,
        ).grid(row=0, column=0, sticky="w", padx=14, pady=(14, 4))

        preview_shell = ctk.CTkFrame(
            cover_panel,
            fg_color=C_SURFACE,
            corner_radius=12,
            border_width=1,
            border_color=C_BORDER,
        )
        preview_shell.grid(row=1, column=0, sticky="nsew", padx=14, pady=(0, 10))
        preview_shell.grid_columnconfigure(0, weight=1)
        preview_shell.grid_rowconfigure(0, weight=1)
        preview_shell.grid_propagate(False)
        preview_shell.configure(width=220, height=220)

        self._cover_preview = ctk.CTkLabel(
            preview_shell,
            text="No cover art",
            font=self._font_small,
            text_color=C_MUTED,
            justify="center",
        )
        self._cover_preview.grid(row=0, column=0, sticky="nsew", padx=12, pady=12)

        self._cover_state_var = tk.StringVar(value="Current file has no embedded cover")
        self._cover_hint_var = tk.StringVar(value="Choose a JPG or PNG image to apply")

        ctk.CTkLabel(
            cover_panel,
            textvariable=self._cover_state_var,
            font=self._font_small,
            text_color=C_TEXT,
            anchor="w",
            justify="left",
            wraplength=220,
        ).grid(row=2, column=0, sticky="ew", padx=14)

        ctk.CTkLabel(
            cover_panel,
            textvariable=self._cover_hint_var,
            font=self._font_xsmall,
            text_color=C_MUTED,
            anchor="w",
            justify="left",
            wraplength=220,
        ).grid(row=3, column=0, sticky="ew", padx=14, pady=(4, 10))

        button_bar = ctk.CTkFrame(cover_panel, fg_color="transparent")
        button_bar.grid(row=4, column=0, sticky="ew", padx=14, pady=(0, 14))
        button_bar.columnconfigure(0, weight=1)
        button_bar.columnconfigure(1, weight=1)

        ctk.CTkButton(
            button_bar,
            text="Choose Image",
            font=self._font_small,
            fg_color="transparent",
            hover_color=C_SURFACE,
            text_color=C_MUTED,
            border_width=1,
            border_color=C_BORDER,
            height=38,
            corner_radius=8,
            command=self._choose_cover_image,
        ).grid(row=0, column=0, sticky="ew", padx=(0, 6), pady=(0, 8))

        ctk.CTkButton(
            button_bar,
            text="Clear Pending",
            font=self._font_small,
            fg_color="transparent",
            hover_color=C_SURFACE,
            text_color=C_MUTED,
            border_width=1,
            border_color=C_BORDER,
            height=38,
            corner_radius=8,
            command=self._clear_pending_cover,
        ).grid(row=0, column=1, sticky="ew", padx=(6, 0), pady=(0, 8))

        ctk.CTkButton(
            button_bar,
            text="Apply Cover",
            font=self._font_small,
            fg_color=C_ACCENT,
            hover_color=C_ACCENT_HOVER,
            text_color=("white", "white"),
            height=40,
            corner_radius=8,
            command=self._apply_cover,
        ).grid(row=1, column=0, sticky="ew", padx=(0, 6))

        ctk.CTkButton(
            button_bar,
            text="Remove Cover",
            font=self._font_small,
            fg_color="transparent",
            hover_color=C_SURFACE,
            text_color=C_MUTED,
            border_width=1,
            border_color=C_BORDER,
            height=40,
            corner_radius=8,
            command=self._remove_cover,
        ).grid(row=1, column=1, sticky="ew", padx=(6, 0))

    def _build_status_bar(self) -> None:
        ctk.CTkFrame(self, height=1, fg_color=C_BORDER, corner_radius=0).pack(
            fill="x", side="bottom"
        )

        bar = ctk.CTkFrame(self, height=34, corner_radius=0, fg_color=C_SURFACE)
        bar.pack(fill="x", side="bottom")
        bar.pack_propagate(False)

        self._status_dot = ctk.CTkFrame(
            bar, width=8, height=8, corner_radius=4, fg_color=C_DOT_OK
        )
        self._status_dot.pack(side="left", padx=(14, 8))
        self._status_dot.pack_propagate(False)

        self._status_var = tk.StringVar(value="Ready")
        ctk.CTkLabel(
            bar,
            textvariable=self._status_var,
            font=self._font_small,
            text_color=C_MUTED,
            anchor="w",
        ).pack(side="left", fill="x", expand=True)

        self._count_label = ctk.CTkLabel(
            bar,
            text="",
            font=self._font_xsmall,
            text_color=C_MUTED,
            anchor="e",
        )
        self._count_label.pack(side="right", padx=(0, 14))

    def _pick_folder(self) -> None:
        folder = filedialog.askdirectory(title="Select folder with MP3 files")
        if not folder:
            return

        self._folder_path = folder
        self._path_label.configure(text=self._shorten_path(folder))
        self._load_folder(folder)

    def _shorten_path(self, path: str) -> str:
        if len(path) <= 72:
            return path
        return "..." + path[-69:]

    def _load_folder(
        self,
        folder: str,
        *,
        selected_path: Optional[str] = None,
        checked_paths: Optional[set[str]] = None,
    ) -> None:
        self._cancel_load.set()
        self._cancel_load = threading.Event()

        for row in self._all_rows:
            row.destroy()

        self._all_rows.clear()
        self._file_rows.clear()
        self._folder_rows.clear()
        self._folder_descendants.clear()
        self._file_drafts.clear()
        self._selected_file = None
        self._selected_cover = None
        self._pending_cover_path = None
        self._pending_cover_name = ""
        self._selected_label.configure(text="No file selected")
        self._search_var.set("")
        self._clear_form()
        self._show_current_cover(None)

        entries = list_mp3_tree(folder)
        if not entries:
            self._tree_badge.configure(text="0 files")
            self._count_label.configure(text="")
            self._set_status("No MP3 files found in this folder", state="error")
            return

        for row_index, entry in enumerate(entries):
            if entry.kind == "folder":
                row = _FolderRow(
                    self._tree_frame,
                    row_index=row_index,
                    entry=entry,
                    font=self._font_small,
                    on_toggle=self._on_folder_toggle,
                    on_check=self._on_folder_check,
                )
                self._folder_rows[entry.relative_path] = row
            else:
                row = _FileRow(
                    self._tree_frame,
                    row_index=row_index,
                    entry=entry,
                    font=self._font_small,
                    on_select=self._on_file_select,
                    on_check=self._on_check_change,
                )
                self._file_rows.append(row)

            self._all_rows.append(row)

        if checked_paths is not None:
            for row in self._file_rows:
                row.set_checked(row.entry.path in checked_paths)

        self._build_folder_descendants()
        self._refresh_folder_selection_states()
        self._apply_tree_visibility()
        self._set_status(
            f"Loaded {len(self._file_rows)} MP3 files from subfolders",
            state="ok",
        )

        target_row = None
        if selected_path:
            target_row = next(
                (row for row in self._file_rows if row.entry.path == selected_path),
                None,
            )
        if target_row is None and self._file_rows:
            target_row = self._file_rows[0]
        if target_row is not None:
            self._on_file_select(target_row.entry.path, target_row)

    def _ancestor_paths(self, relative_path: str) -> List[str]:
        ancestors: List[str] = []
        current = os.path.dirname(relative_path)
        while current:
            ancestors.append(current)
            current = os.path.dirname(current)
        ancestors.reverse()
        return ancestors

    def _build_folder_descendants(self) -> None:
        self._folder_descendants = {path: [] for path in self._folder_rows}

        for file_row in self._file_rows:
            for ancestor in self._ancestor_paths(file_row.entry.relative_path):
                if ancestor in self._folder_descendants:
                    self._folder_descendants[ancestor].append(file_row)

    def _on_folder_toggle(self, _: str) -> None:
        self._apply_tree_visibility()

    def _on_folder_check(self, folder_relative_path: str, checked: bool) -> None:
        descendants = self._folder_descendants.get(folder_relative_path, [])
        for file_row in descendants:
            file_row.set_checked(checked)

        self._refresh_folder_selection_states()
        self._update_counts()

        if descendants:
            action = "Selected" if checked else "Deselected"
            self._set_status(
                f"{action} {len(descendants)} files in {os.path.basename(folder_relative_path)}",
                state="ok",
            )

    def _on_file_select(self, path: str, row: "_FileRow") -> None:
        self._store_current_file_draft()

        for file_row in self._file_rows:
            file_row.set_active(file_row is row)

        self._selected_file = path
        self._selected_label.configure(text=row.entry.relative_path.replace("\\", " / "))

        self._cancel_load.set()
        cancel_token = threading.Event()
        self._cancel_load = cancel_token
        self._set_status("Loading tags...", state="busy")

        def worker() -> None:
            tags = dict(self._file_drafts.get(path) or load_mp3_tags(path))
            cover = get_cover_art(path)
            if cancel_token.is_set():
                return

            def update_ui() -> None:
                self._file_drafts[path] = dict(tags)
                self._fill_form(tags)
                self._set_rename_value(path)
                self._selected_cover = cover
                if not self._pending_cover_path:
                    self._show_current_cover(cover)
                else:
                    self._show_pending_cover()
                self._set_status(os.path.basename(path), state="ok")

            self.after(0, update_ui)

        threading.Thread(target=worker, daemon=True).start()

    def _on_check_change(self) -> None:
        self._refresh_folder_selection_states()
        self._update_counts()

    def _clear_form(self) -> None:
        for entry in self._entries.values():
            entry.delete(0, "end")
        if self._rename_entry is not None:
            self._rename_entry.delete(0, "end")

    def _fill_form(self, tags: Dict[str, str]) -> None:
        for field_name, entry in self._entries.items():
            entry.delete(0, "end")
            value = tags.get(field_name, "")
            if value:
                entry.insert(0, value)

    def _store_current_file_draft(self) -> None:
        if not self._selected_file:
            return
        self._file_drafts[self._selected_file] = self._form_data()

    def _set_rename_value(self, file_path: Optional[str]) -> None:
        if self._rename_entry is None:
            return

        self._rename_entry.delete(0, "end")
        if not file_path:
            return

        self._rename_entry.insert(0, os.path.splitext(os.path.basename(file_path))[0])

    def _use_rename_as_title(self) -> None:
        if self._rename_entry is None:
            return

        rename_value = self._rename_entry.get().strip()
        if not rename_value:
            self._set_status("Enter a rename value first", state="error")
            return

        title_entry = self._entries["title"]
        title_entry.delete(0, "end")
        title_entry.insert(0, rename_value)
        self._store_current_file_draft()
        self._set_status("Copied Rename value to Title", state="ok")

    def _choose_cover_image(self) -> None:
        image_path = filedialog.askopenfilename(
            title="Choose cover image",
            filetypes=[
                ("Image files", "*.jpg;*.jpeg;*.png"),
                ("JPEG", "*.jpg;*.jpeg"),
                ("PNG", "*.png"),
            ],
        )
        if not image_path:
            return

        self._pending_cover_path = image_path
        self._pending_cover_name = os.path.basename(image_path)
        self._show_pending_cover()
        self._set_status(
            f"Selected cover image {self._pending_cover_name} for the checked files",
            state="ok",
        )

    def _clear_pending_cover(self) -> None:
        self._pending_cover_path = None
        self._pending_cover_name = ""
        self._show_current_cover(self._selected_cover)
        self._set_status("Cleared pending cover image", state="ok")

    def _show_pending_cover(self) -> None:
        if not self._pending_cover_path:
            self._show_current_cover(self._selected_cover)
            return

        try:
            with open(self._pending_cover_path, "rb") as image_file:
                image_data = image_file.read()
        except OSError as exc:
            self._pending_cover_path = None
            self._pending_cover_name = ""
            self._show_current_cover(self._selected_cover)
            self._set_status(f"Could not read selected cover image: {exc}", state="error")
            return

        self._cover_state_var.set("Selected image ready to apply")
        self._cover_hint_var.set(self._pending_cover_name)
        self._update_cover_preview(image_data, fallback_text="Selected cover image")

    def _show_current_cover(self, cover: Optional[CoverArt]) -> None:
        self._selected_cover = cover
        if cover is None:
            self._cover_state_var.set("Current file has no embedded cover")
            self._cover_hint_var.set("Choose a JPG or PNG image to apply")
            self._clear_cover_preview("No cover art")
            return

        self._cover_state_var.set("Embedded cover art found")
        self._cover_hint_var.set(cover.mime)
        self._update_cover_preview(cover.data, fallback_text="Embedded cover art")

    def _clear_cover_preview(self, text: str) -> None:
        self._cover_preview_image = None
        self._cover_preview_photo = None
        self._cover_preview._text = text
        self._cover_preview._image = None
        self._cover_preview._label.configure(image="", text=text)

    def _update_cover_preview(self, image_data: bytes, fallback_text: str) -> None:
        if Image is None or ImageOps is None or ImageTk is None:
            self._clear_cover_preview(f"{fallback_text}\nInstall Pillow for preview")
            return

        try:
            image = Image.open(io.BytesIO(image_data))
            image = ImageOps.contain(image.convert("RGB"), (180, 180))
        except Exception:
            self._clear_cover_preview(fallback_text)
            return

        self._cover_preview_image = image
        self._cover_preview_photo = ImageTk.PhotoImage(image)
        self._cover_preview._text = ""
        self._cover_preview._image = self._cover_preview_photo
        self._cover_preview._label.configure(image=self._cover_preview_photo, text="")

    def _form_data(self) -> Dict[str, str]:
        return {
            field_name: self._entries[field_name].get().strip() for field_name in FIELDS
        }

    def _build_save_drafts(self, paths: List[str]) -> Dict[str, Dict[str, str]]:
        self._store_current_file_draft()

        drafts: Dict[str, Dict[str, str]] = {}
        for path in paths:
            draft = self._file_drafts.get(path)
            if draft is None:
                draft = load_mp3_tags(path)
                self._file_drafts[path] = dict(draft)
            drafts[path] = dict(draft)

        return drafts

    def _confirm_rename(self, current_path: str, new_name: str) -> bool:
        dialog = _ConfirmDialog(
            self,
            title="Confirm Rename",
            message="Rename the selected MP3 file?",
            details=[
                f"Current: {os.path.basename(current_path)}",
                f"New name: {new_name}.mp3",
            ],
            confirm_text="Rename",
            cancel_text="Cancel",
            font=self._font_small,
            heading_font=self._font_heading,
        )
        return dialog.show()

    def _confirm_save(self, paths: List[str], drafts: Dict[str, Dict[str, str]]) -> bool:
        non_empty_fields = set()
        for draft in drafts.values():
            for key, value in draft.items():
                if value:
                    non_empty_fields.add(FIELD_LABELS[key])

        field_names = ", ".join(sorted(non_empty_fields)) if non_empty_fields else "No filled tag fields"
        lines = [
            "Mode: Save each file with its own current draft.",
            f"Fields found across selected files: {field_names}",
        ]

        if len(paths) > 1:
            lines.append("Current screen values will not be copied to every file automatically.")

        dialog = _ConfirmDialog(
            self,
            title="Confirm Save",
            message=f"Save tags to {len(paths)} selected file(s)?",
            details=lines,
            confirm_text="Save",
            cancel_text="Cancel",
            font=self._font_small,
            heading_font=self._font_heading,
        )
        return dialog.show()

    def _toggle_all(self) -> None:
        if not self._file_rows:
            self._set_status("No files available to select", state="error")
            return

        should_check = not all(row.checked for row in self._file_rows)
        for row in self._file_rows:
            row.set_checked(should_check)

        self._refresh_folder_selection_states()
        self._update_counts()
        if should_check:
            self._set_status(f"Selected {len(self._file_rows)} files", state="ok")
        else:
            self._set_status(f"Deselected {len(self._file_rows)} files", state="ok")

    def _rename_selected_file(self) -> None:
        self._store_current_file_draft()
        if not self._selected_file:
            self._set_status("Select a file before renaming", state="error")
            return
        if self._rename_entry is None:
            return

        new_name = self._rename_entry.get().strip()
        if not new_name:
            self._set_status("Enter a new filename before renaming", state="error")
            return

        current_name = os.path.splitext(os.path.basename(self._selected_file))[0]
        if new_name == current_name:
            self._set_status("Filename is unchanged", state="ok")
            return

        if not self._confirm_rename(self._selected_file, new_name):
            self._set_status("Rename canceled", state="ok")
            return

        old_path = self._selected_file
        checked_paths = {
            row.entry.path for row in self._file_rows if row.checked
        }

        self._set_status("Renaming file...", state="busy")

        def worker() -> None:
            try:
                new_path = rename_mp3_file(old_path, new_name)
            except Exception as exc:
                self.after(
                    0,
                    lambda: self._set_status(f"Could not rename file: {exc}", state="error"),
                )
                return

            restored_checked_paths = {
                new_path if path == old_path else path
                for path in checked_paths
            }

            def update_ui() -> None:
                if old_path in self._file_drafts:
                    self._file_drafts[new_path] = self._file_drafts.pop(old_path)
                self._load_folder(
                    self._folder_path,
                    selected_path=new_path,
                    checked_paths=restored_checked_paths,
                )
                self._set_status(f"Renamed file to {os.path.basename(new_path)}", state="ok")

            self.after(0, update_ui)

        threading.Thread(target=worker, daemon=True).start()

    def _checked_paths(self) -> List[str]:
        return [row.entry.path for row in self._file_rows if row.checked]

    def _search_matches(self, row: "_TreeRowBase", query: str) -> bool:
        search_text = row.entry.relative_path.replace("\\", "/").lower()
        return query in search_text

    def _apply_tree_visibility(self) -> None:
        query = self._search_var.get().strip().lower()

        if query:
            visible_paths = self._visible_paths_for_query(query)
            for row in self._all_rows:
                if row.entry.relative_path in visible_paths:
                    row.show()
                else:
                    row.hide()
        else:
            for row in self._all_rows:
                if self._has_collapsed_ancestor(row):
                    row.hide()
                else:
                    row.show()

        self._update_counts()

    def _visible_paths_for_query(self, query: str) -> set[str]:
        visible_paths: set[str] = set()
        separator = os.sep

        for folder_row in self._folder_rows.values():
            if not self._search_matches(folder_row, query):
                continue

            visible_paths.add(folder_row.entry.relative_path)
            visible_paths.update(self._ancestor_paths(folder_row.entry.relative_path))

            prefix = folder_row.entry.relative_path + separator
            for row in self._all_rows:
                if row.entry.relative_path == folder_row.entry.relative_path:
                    visible_paths.add(row.entry.relative_path)
                elif row.entry.relative_path.startswith(prefix):
                    visible_paths.add(row.entry.relative_path)

        for file_row in self._file_rows:
            if not self._search_matches(file_row, query):
                continue

            visible_paths.add(file_row.entry.relative_path)
            visible_paths.update(self._ancestor_paths(file_row.entry.relative_path))

        return visible_paths

    def _has_collapsed_ancestor(self, row: "_TreeRowBase") -> bool:
        for ancestor in self._ancestor_paths(row.entry.relative_path):
            ancestor_row = self._folder_rows.get(ancestor)
            if ancestor_row and not ancestor_row.expanded:
                return True
        return False

    def _update_counts(self) -> None:
        total_files = len(self._file_rows)
        visible_files = sum(1 for row in self._file_rows if row.is_visible)
        checked_files = sum(1 for row in self._file_rows if row.checked)

        if self._search_var.get().strip():
            badge_text = f"{visible_files}/{total_files} files"
        else:
            badge_text = f"{total_files} files"

        self._tree_badge.configure(text=badge_text)
        self._count_label.configure(
            text=f"{checked_files} selected" if checked_files else "0 selected"
        )
        self._save_button.configure(
            text=f"Save Selected Files ({checked_files})"
            if checked_files
            else "Save Selected Files"
        )

        if total_files and checked_files == total_files:
            self._select_all_button.configure(text="Deselect All")
        else:
            self._select_all_button.configure(text="Select All")

    def _refresh_folder_selection_states(self) -> None:
        for folder_path, folder_row in self._folder_rows.items():
            descendants = self._folder_descendants.get(folder_path, [])
            total_files = len(descendants)
            checked_files = sum(1 for row in descendants if row.checked)
            folder_row.set_selection_state(checked_files, total_files)

    def _fill_titles(self) -> None:
        paths = self._checked_paths()
        if not paths:
            self._set_status("No files selected", state="error")
            return

        self._set_status(
            f"Filling title from filename for {len(paths)} files...",
            state="busy",
        )

        def worker() -> None:
            updated_count, errors = fill_titles_from_filenames(paths)
            ok = not errors
            message = f"Filled {updated_count} title(s) from filename"
            if errors:
                message += f" | {len(errors)} error(s)"

            def update_ui() -> None:
                for path in paths:
                    draft = dict(self._file_drafts.get(path) or load_mp3_tags(path))
                    draft["title"] = build_title_from_filename(os.path.basename(path))
                    self._file_drafts[path] = draft
                self._set_status(message, state="ok" if ok else "error")
                if self._selected_file and self._selected_file in paths:
                    self._fill_form(self._file_drafts[self._selected_file])

            self.after(0, update_ui)

        threading.Thread(target=worker, daemon=True).start()

    def _apply_cover(self) -> None:
        paths = self._checked_paths()
        if not paths:
            self._set_status("No files selected", state="error")
            return
        if not self._pending_cover_path:
            self._set_status("Choose a cover image before applying", state="error")
            return

        cover_name = os.path.basename(self._pending_cover_path)
        self._set_status(f"Applying {cover_name} to {len(paths)} file(s)...", state="busy")

        def worker() -> None:
            try:
                updated_count, errors = apply_cover_to_files(paths, self._pending_cover_path or "")
            except Exception as exc:
                self.after(
                    0,
                    lambda: self._set_status(f"Could not apply cover image: {exc}", state="error"),
                )
                return

            ok = not errors
            message = f"Applied cover art to {updated_count} file(s)"
            if errors:
                message += f" | {len(errors)} error(s)"

            def update_ui() -> None:
                self._set_status(message, state="ok" if ok else "error")
                self._pending_cover_path = None
                self._pending_cover_name = ""
                if self._selected_file and self._selected_file in paths:
                    self._selected_cover = get_cover_art(self._selected_file)
                self._show_current_cover(self._selected_cover)

            self.after(0, update_ui)

        threading.Thread(target=worker, daemon=True).start()

    def _remove_cover(self) -> None:
        paths = self._checked_paths()
        if not paths:
            self._set_status("No files selected", state="error")
            return

        self._set_status(f"Removing cover art from {len(paths)} file(s)...", state="busy")

        def worker() -> None:
            removed_count, errors = remove_cover_from_files(paths)
            ok = not errors
            message = f"Removed cover art from {removed_count} file(s)"
            if errors:
                message += f" | {len(errors)} error(s)"

            def update_ui() -> None:
                self._pending_cover_path = None
                self._pending_cover_name = ""
                if self._selected_file and self._selected_file in paths:
                    self._selected_cover = get_cover_art(self._selected_file)
                self._show_current_cover(self._selected_cover)
                self._set_status(message, state="ok" if ok else "error")

            self.after(0, update_ui)

        threading.Thread(target=worker, daemon=True).start()

    def _save(self) -> None:
        paths = self._checked_paths()
        if not paths:
            self._set_status("No files selected", state="error")
            return

        drafts = self._build_save_drafts(paths)
        if not any(any(value for value in draft.values()) for draft in drafts.values()):
            self._set_status(
                "No tag data found to save for the selected files",
                state="error",
            )
            return

        if not self._confirm_save(paths, drafts):
            self._set_status("Save canceled", state="ok")
            return

        self._set_status(f"Saving {len(paths)} file(s) from individual drafts...", state="busy")

        def worker() -> None:
            saved_count, errors = save_tag_drafts_to_files(drafts)
            ok = not errors
            message = f"Saved {saved_count} file(s)"
            if errors:
                message += f" | {len(errors)} error(s)"
            self.after(0, lambda: self._set_status(message, state="ok" if ok else "error"))

        threading.Thread(target=worker, daemon=True).start()

    def _toggle_mode(self) -> None:
        is_dark = ctk.get_appearance_mode() == "Dark"
        ctk.set_appearance_mode("light" if is_dark else "dark")
        self._mode_button.configure(text="Dark" if is_dark else "Light")

    def _set_status(self, message: str, state: str = "ok") -> None:
        self._status_var.set(message)
        dot_color = {
            "ok": C_DOT_OK,
            "busy": C_DOT_BUSY,
            "error": C_DOT_ERROR,
        }.get(state, C_DOT_OK)
        self._status_dot.configure(fg_color=dot_color)


class _TreeRowBase(ctk.CTkFrame):
    def __init__(
        self,
        master,
        row_index: int,
        entry: MP3TreeEntry,
        *,
        font,
    ) -> None:
        super().__init__(master, fg_color="transparent", corner_radius=8)
        self.entry = entry
        self._row_index = row_index
        self._is_visible = True
        self._font = font
        self._indent_width = 14 + (entry.depth * 20)

        self.grid(row=row_index, column=0, sticky="ew", pady=(0, 3), padx=4)
        self.grid_columnconfigure(3, weight=1)

        self._indent = ctk.CTkFrame(
            self,
            width=self._indent_width,
            fg_color="transparent",
        )
        self._indent.grid(row=0, column=0, sticky="nsw")
        self._indent.grid_propagate(False)
        self._indent.configure(height=30)

    @property
    def is_visible(self) -> bool:
        return self._is_visible

    def show(self) -> None:
        if not self._is_visible:
            self.grid()
            self._is_visible = True

    def hide(self) -> None:
        if self._is_visible:
            self.grid_remove()
            self._is_visible = False


class _FolderRow(_TreeRowBase):
    def __init__(
        self,
        master,
        row_index: int,
        entry: MP3TreeEntry,
        *,
        font,
        on_toggle: Callable[[str], None],
        on_check: Callable[[str, bool], None],
    ) -> None:
        super().__init__(master, row_index, entry, font=font)
        self.expanded = True
        self._on_toggle = on_toggle
        self._on_check = on_check
        self._checked_var = tk.BooleanVar(value=True)
        self._syncing_state = False

        self._checkbox = ctk.CTkCheckBox(
            self,
            text="",
            variable=self._checked_var,
            width=24,
            checkbox_width=16,
            checkbox_height=16,
            fg_color=C_ACCENT,
            hover_color=C_ACCENT_HOVER,
            border_width=2,
            border_color=C_BORDER,
            command=self._checkbox_toggled,
        )
        self._checkbox.grid(row=0, column=0, padx=(10, 6), pady=4)
        self._checkbox.grid_configure(column=1, padx=(0, 6))

        self._button = ctk.CTkButton(
            self,
            text="",
            font=font,
            anchor="w",
            fg_color="transparent",
            hover_color=C_ROW_HOVER,
            text_color=C_TEXT,
            corner_radius=8,
            height=30,
            command=self._toggle,
        )
        self._button.grid(
            row=0,
            column=3,
            sticky="ew",
            padx=(0, 8),
            pady=2,
        )

        self._branch_label = ctk.CTkLabel(
            self,
            text="",
            font=font,
            text_color=C_MUTED,
            width=20,
        )
        self._branch_label.grid(row=0, column=2, sticky="w", padx=(0, 6))

        self._count_label = ctk.CTkLabel(
            self,
            text="0/0",
            font=font,
            text_color=C_MUTED,
            anchor="e",
            width=54,
        )
        self._count_label.grid(row=0, column=4, sticky="e", padx=(0, 8))
        self._refresh()

    def _checkbox_toggled(self) -> None:
        if self._syncing_state:
            return
        self._on_check(self.entry.relative_path, self._checked_var.get())

    def _toggle(self) -> None:
        self.expanded = not self.expanded
        self._refresh()
        self._on_toggle(self.entry.relative_path)

    def set_selection_state(self, checked_files: int, total_files: int) -> None:
        self._syncing_state = True
        self._checked_var.set(total_files > 0 and checked_files == total_files)
        self._syncing_state = False

        if total_files == 0:
            self._count_label.configure(text="0/0", text_color=C_MUTED)
        else:
            count_text = f"{checked_files}/{total_files}"
            if 0 < checked_files < total_files:
                text_color = C_ACCENT
            elif checked_files == total_files:
                text_color = C_TEXT
            else:
                text_color = C_MUTED
            self._count_label.configure(text=count_text, text_color=text_color)

    def _refresh(self) -> None:
        prefix = "▾" if self.expanded else "▸"
        self._branch_label.configure(text=prefix)
        self._button.configure(text=self.entry.name)


class _FileRow(_TreeRowBase):
    def __init__(
        self,
        master,
        row_index: int,
        entry: MP3TreeEntry,
        *,
        font,
        on_select: Callable[[str, "_FileRow"], None],
        on_check: Callable[[], None],
    ) -> None:
        super().__init__(master, row_index, entry, font=font)
        self._on_select = on_select
        self._on_check = on_check
        self._active = False
        self._hovered = False
        self._checked_var = tk.BooleanVar(value=True)

        self._checkbox = ctk.CTkCheckBox(
            self,
            text="",
            variable=self._checked_var,
            width=24,
            checkbox_width=16,
            checkbox_height=16,
            fg_color=C_ACCENT,
            hover_color=C_ACCENT_HOVER,
            border_width=2,
            border_color=C_BORDER,
            command=self._check_changed,
        )
        self._checkbox.grid(
            row=0,
            column=1,
            padx=(0, 6),
            pady=4,
        )

        self._branch_label = ctk.CTkLabel(
            self,
            text="•",
            font=font,
            text_color=C_MUTED,
            width=20,
        )
        self._branch_label.grid(row=0, column=2, sticky="w", padx=(0, 6))

        self._button = ctk.CTkButton(
            self,
            text=entry.name,
            font=font,
            anchor="w",
            fg_color="transparent",
            hover_color=C_ROW_HOVER,
            text_color=C_TEXT,
            corner_radius=8,
            height=30,
            command=lambda: self._on_select(entry.path, self),
        )
        self._button.grid(row=0, column=3, sticky="ew", padx=(0, 8), pady=2)

        for widget in (self, self._button):
            widget.bind("<Enter>", lambda _event: self._set_hover(True))
            widget.bind("<Leave>", lambda _event: self._set_hover(False))

    @property
    def checked(self) -> bool:
        return self._checked_var.get()

    def set_checked(self, value: bool) -> None:
        self._checked_var.set(value)

    def set_active(self, active: bool) -> None:
        self._active = active
        self._refresh()

    def _check_changed(self) -> None:
        self._on_check()

    def _set_hover(self, hovered: bool) -> None:
        self._hovered = hovered
        self._refresh()

    def _refresh(self) -> None:
        if self._active:
            self.configure(fg_color=C_ROW_SELECTED)
            self._button.configure(text_color=("#1d4ed8", "#93c5fd"))
        elif self._hovered:
            self.configure(fg_color=C_ROW_HOVER)
            self._button.configure(text_color=C_TEXT)
        else:
            self.configure(fg_color="transparent")
            self._button.configure(text_color=C_TEXT)


class _ConfirmDialog(ctk.CTkToplevel):
    def __init__(
        self,
        master,
        *,
        title: str,
        message: str,
        details: List[str],
        confirm_text: str,
        cancel_text: str,
        font,
        heading_font,
    ) -> None:
        super().__init__(master)
        self.withdraw()
        self.overrideredirect(True)
        self.geometry("520x360")
        self.resizable(False, False)
        self.configure(fg_color=C_BG)
        self.transient(master)
        self.result = False
        self._drag_offset_x = 0
        self._drag_offset_y = 0

        shell = ctk.CTkFrame(
            self,
            fg_color=C_BG,
            corner_radius=18,
            border_width=1,
            border_color=C_BORDER,
        )
        shell.pack(fill="both", expand=True, padx=10, pady=10)
        shell.grid_columnconfigure(0, weight=1)
        shell.grid_rowconfigure(1, weight=1)

        title_bar = ctk.CTkFrame(shell, fg_color="transparent")
        title_bar.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 8))
        title_bar.grid_columnconfigure(0, weight=1)

        title_label = ctk.CTkLabel(
            title_bar,
            text=title,
            font=heading_font,
            text_color=C_TEXT,
            anchor="w",
        )
        title_label.grid(row=0, column=0, sticky="w")

        close_button = ctk.CTkButton(
            title_bar,
            text="x",
            width=30,
            height=30,
            font=font,
            fg_color="transparent",
            hover_color=C_SURFACE_ALT,
            text_color=C_MUTED,
            corner_radius=8,
            command=self._cancel,
        )
        close_button.grid(row=0, column=1, sticky="e")

        for widget in (title_bar, title_label):
            widget.bind("<ButtonPress-1>", self._start_drag)
            widget.bind("<B1-Motion>", self._drag)

        card = ctk.CTkFrame(
            shell,
            fg_color=C_SURFACE,
            corner_radius=16,
            border_width=1,
            border_color=C_BORDER,
        )
        card.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(
            card,
            text="Confirm Save",
            font=heading_font,
            text_color=C_TEXT,
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", padx=18, pady=(18, 6))

        ctk.CTkLabel(
            card,
            text=message,
            font=font,
            text_color=C_TEXT,
            anchor="w",
            justify="left",
            wraplength=430,
        ).grid(row=1, column=0, sticky="ew", padx=18)

        detail_box = ctk.CTkScrollableFrame(
            card,
            fg_color=C_SURFACE_ALT,
            corner_radius=12,
            border_width=1,
            border_color=C_BORDER,
            scrollbar_button_color=C_BORDER,
            scrollbar_button_hover_color=C_MUTED,
        )
        detail_box.grid(row=2, column=0, sticky="nsew", padx=18, pady=(12, 16))
        detail_box.grid_columnconfigure(0, weight=1)

        for index, detail in enumerate(details):
            ctk.CTkLabel(
                detail_box,
                text=detail,
                font=font,
                text_color=C_MUTED if detail.endswith(":") or detail.startswith("Tip:") else C_TEXT,
                anchor="w",
                justify="left",
                wraplength=390,
            ).grid(row=index, column=0, sticky="ew", padx=14, pady=(12 if index == 0 else 6, 0))

        action_bar = ctk.CTkFrame(card, fg_color="transparent")
        action_bar.grid(row=3, column=0, sticky="ew", padx=18, pady=(0, 18))
        action_bar.columnconfigure(0, weight=1)
        action_bar.columnconfigure(1, weight=1)

        ctk.CTkButton(
            action_bar,
            text=cancel_text,
            font=font,
            fg_color="transparent",
            hover_color=C_SURFACE_ALT,
            text_color=C_MUTED,
            border_width=1,
            border_color=C_BORDER,
            height=40,
            corner_radius=10,
            command=self._cancel,
        ).grid(row=0, column=0, sticky="ew", padx=(0, 6))

        ctk.CTkButton(
            action_bar,
            text=confirm_text,
            font=font,
            fg_color=C_ACCENT,
            hover_color=C_ACCENT_HOVER,
            text_color=("white", "white"),
            height=40,
            corner_radius=10,
            command=self._confirm,
        ).grid(row=0, column=1, sticky="ew", padx=(6, 0))

        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.bind("<Escape>", lambda _event: self._cancel())
        self.bind("<Return>", lambda _event: self._confirm())

    def _confirm(self) -> None:
        self.result = True
        self.destroy()

    def _cancel(self) -> None:
        self.result = False
        self.destroy()

    def _start_drag(self, event) -> None:
        self._drag_offset_x = event.x_root - self.winfo_x()
        self._drag_offset_y = event.y_root - self.winfo_y()

    def _drag(self, event) -> None:
        x = event.x_root - self._drag_offset_x
        y = event.y_root - self._drag_offset_y
        self.geometry(f"+{x}+{y}")

    def _center_on_parent(self) -> None:
        self.update_idletasks()
        parent = self.master
        parent.update_idletasks()

        parent_x = parent.winfo_rootx()
        parent_y = parent.winfo_rooty()
        parent_width = parent.winfo_width()
        parent_height = parent.winfo_height()

        width = self.winfo_width()
        height = self.winfo_height()

        x = parent_x + max((parent_width - width) // 2, 20)
        y = parent_y + max((parent_height - height) // 2, 20)
        self.geometry(f"{width}x{height}+{x}+{y}")

    def show(self) -> bool:
        self.deiconify()
        self._center_on_parent()
        self.lift()
        self.update_idletasks()
        self.grab_set()
        self.focus_force()
        self.wait_window()
        return self.result


if __name__ == "__main__":
    app = App()
    # Show window after event loop is ready and all widgets are laid out
    # Delay allows Tkinter to process layout before rendering visible window
    app.after(_WINDOW_DEICONIFY_DELAY_MS, app.deiconify)
    app.mainloop()
