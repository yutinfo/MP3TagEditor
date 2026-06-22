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

# Debounce delay for the file/folder filter so tree visibility is not
# recomputed on every keystroke (milliseconds)
_SEARCH_DEBOUNCE_MS = 200

# Tk scaling factor for DPI blur prevention
_TK_SCALING_FACTOR = 1.0

# Fixed height (px) of a single tree row. The folder tree is virtualized: only
# the rows in the current viewport are rendered, so a constant row height lets us
# map a scroll offset directly to a model index range. Keep this in sync with the
# row's internal widget heights (checkbox 16px / name button 30px sit inside it).
_TREE_ROW_HEIGHT = 33

# How many model rows a single mouse-wheel notch scrolls.
_TREE_WHEEL_ROWS = 3

# Resizable layout: folder-tree (left) panel width bounds and splitter, in pixels
_LEFT_PANEL_DEFAULT_WIDTH = 340
_LEFT_PANEL_MIN_WIDTH = 260
_EDITOR_PANEL_MIN_WIDTH = 380
_SPLITTER_WIDTH = 10

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
C_ROW_SELECTED_TEXT = ("#1d4ed8", "#93c5fd")
C_ROW_HOVER = ("#eef4ff", "#1a2744")
C_DOT_OK = ("#22c55e", "#22c55e")
C_DOT_BUSY = ("#f59e0b", "#f59e0b")
C_DOT_ERROR = ("#ef4444", "#ef4444")


class _LoadingOverlay(ctk.CTkFrame):
    """Animated loading overlay for file tree."""

    _SPINNER_FRAMES = ["◐", "◓", "◑", "◒"]
    _ANIM_INTERVAL_MS = 120

    def __init__(
        self,
        parent: ctk.CTkFrame,
        font: ctk.CTkFont,
        font_small: ctk.CTkFont,
        **kwargs,
    ) -> None:
        super().__init__(
            parent,
            fg_color=C_SURFACE,
            corner_radius=0,
            **kwargs,
        )
        self.grid(row=2, column=0, sticky="nsew", padx=6, pady=(0, 8))

        # Center container
        inner = ctk.CTkFrame(self, fg_color="transparent")
        inner.place(relx=0.5, rely=0.5, anchor="center")

        # Spinner label
        self._spinner_label = ctk.CTkLabel(
            inner,
            text="◐",
            font=ctk.CTkFont(family=font.cget("family"), size=32),
            text_color=C_ACCENT,
        )
        self._spinner_label.pack(pady=(0, 8))

        # Loading text
        ctk.CTkLabel(
            inner,
            text="กำลังโหลดไฟล์...",
            font=font_small,
            text_color=C_MUTED,
        ).pack()

        self._frame_idx = 0
        self._job: Optional[str] = None

    def show(self) -> None:
        """Show the loading overlay and start animation."""
        self.tkraise()
        self._animate()

    def hide(self) -> None:
        """Hide the loading overlay and stop animation."""
        if self._job is not None:
            self.after_cancel(self._job)
            self._job = None
        self.grid_remove()

    def _animate(self) -> None:
        """Animate the spinner."""
        self._frame_idx = (self._frame_idx + 1) % len(self._SPINNER_FRAMES)
        self._spinner_label.configure(text=self._SPINNER_FRAMES[self._frame_idx])
        self._job = self.after(self._ANIM_INTERVAL_MS, self._animate)


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
        self._font_small_bold = ctk.CTkFont(
            family=self._font_family, size=12, weight="bold"
        )
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

        # Tree data model — STATE lives here, not inside widgets. The view
        # (`self._tree`, a virtualized widget pool) renders only what is visible.
        # `_tree_entries` is the full ordered scan; the derived collections below
        # are rebuilt on every folder load. (Note: `self._entries`, set later in
        # `_build_editor_panel`, is the unrelated tag-editor form-field map.)
        self._tree_entries: List[MP3TreeEntry] = []
        self._file_entries: List[MP3TreeEntry] = []
        self._folder_entries: Dict[str, MP3TreeEntry] = {}
        self._checked: Dict[str, bool] = {}            # file abs path -> checked
        self._expanded: Dict[str, bool] = {}           # folder rel path -> expanded
        self._folder_descendants: Dict[str, List[MP3TreeEntry]] = {}
        self._visible_entries: List[MP3TreeEntry] = []
        self._cancel_load = threading.Event()
        self._search_job: Optional[str] = None
        self._left_width = _LEFT_PANEL_DEFAULT_WIDTH
        self._splitter_dragging = False

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
        self._content = content
        # Column 0 = folder tree (fixed width, adjusted by the splitter drag),
        # column 1 = draggable splitter, column 2 = tag editor (absorbs slack).
        content.columnconfigure(0, weight=0, minsize=self._left_width)
        content.columnconfigure(1, weight=0)
        content.columnconfigure(2, weight=1, minsize=_EDITOR_PANEL_MIN_WIDTH)
        content.rowconfigure(0, weight=1)

        self._build_file_panel(content)
        self._build_splitter(content)
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
        self._file_panel = ctk.CTkFrame(
            parent,
            fg_color=C_SURFACE,
            corner_radius=12,
            border_width=1,
            border_color=C_BORDER,
        )
        self._file_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 0), pady=(0, 8))
        self._file_panel.rowconfigure(2, weight=1)
        self._file_panel.columnconfigure(0, weight=1)

        header = ctk.CTkFrame(self._file_panel, fg_color="transparent")
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
        self._search_var.trace_add("write", lambda *_: self._schedule_tree_filter())

        ctk.CTkEntry(
            self._file_panel,
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

        self._tree = _VirtualTree(
            self._file_panel,
            bind_row=self._bind_tree_row,
            on_check=self._on_row_check,
            on_click=self._on_row_click,
            font=self._font_small,
            font_bold=self._font_small_bold,
        )
        self._tree.grid(row=2, column=0, sticky="nsew", padx=6, pady=(0, 8))

        # Create and set up loading overlay
        self._loading_overlay = _LoadingOverlay(
            self._file_panel,
            font=self._font,
            font_small=self._font_small,
        )

    def _build_splitter(self, parent: ctk.CTkFrame) -> None:
        """Draggable divider that resizes the folder-tree panel."""
        grip = ctk.CTkFrame(parent, width=_SPLITTER_WIDTH, fg_color="transparent")
        grip.grid(row=0, column=1, sticky="ns", pady=(0, 8))
        grip.grid_propagate(False)
        grip.configure(cursor="sb_h_double_arrow")

        # Centered handle that highlights on hover/drag.
        self._splitter_handle = ctk.CTkFrame(
            grip, width=4, fg_color=C_BORDER, corner_radius=2
        )
        self._splitter_handle.place(relx=0.5, rely=0.5, anchor="center", relheight=0.4)
        self._splitter_handle.configure(cursor="sb_h_double_arrow")

        for widget in (grip, self._splitter_handle):
            widget.bind("<Enter>", lambda _e: self._set_splitter_active(True))
            widget.bind("<Leave>", lambda _e: self._set_splitter_active(False))
            widget.bind("<ButtonPress-1>", self._start_splitter_drag)
            widget.bind("<B1-Motion>", self._on_splitter_drag)
            widget.bind("<ButtonRelease-1>", self._end_splitter_drag)

    def _set_splitter_active(self, active: bool) -> None:
        color = C_ACCENT if (active or self._splitter_dragging) else C_BORDER
        self._splitter_handle.configure(fg_color=color)

    def _start_splitter_drag(self, event) -> None:
        self._splitter_dragging = True
        self._drag_origin_x = event.x_root
        self._drag_origin_width = self._left_width
        self._set_splitter_active(True)

    def _on_splitter_drag(self, event) -> None:
        if not self._splitter_dragging:
            return
        delta = event.x_root - self._drag_origin_x
        available = self._content.winfo_width() - _SPLITTER_WIDTH - _EDITOR_PANEL_MIN_WIDTH
        max_width = max(_LEFT_PANEL_MIN_WIDTH, available)
        new_width = max(
            _LEFT_PANEL_MIN_WIDTH, min(self._drag_origin_width + delta, max_width)
        )
        if new_width != self._left_width:
            self._left_width = new_width
            self._content.columnconfigure(0, minsize=new_width)

    def _end_splitter_drag(self, _event) -> None:
        self._splitter_dragging = False
        self._set_splitter_active(False)

    def _build_editor_panel(self, parent: ctk.CTkFrame) -> None:
        panel = ctk.CTkFrame(
            parent,
            fg_color=C_SURFACE,
            corner_radius=12,
            border_width=1,
            border_color=C_BORDER,
        )
        panel.grid(row=0, column=2, sticky="nsew", padx=(0, 0), pady=(0, 8))
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
        folder = self._ask_directory()
        if not folder:
            return

        self._folder_path = folder
        self._path_label.configure(text=self._shorten_path(folder))
        self._load_folder(folder)

    def _ask_directory(self) -> str:
        """Open the folder picker, guarding against the intermittent Windows
        'Unspecified error' from the native shell directory dialog.

        Passing an explicit parent window and a valid initial directory avoids
        the most common triggers; a single retry covers transient COM/shell
        races. On repeated failure we surface a status message instead of
        crashing the app with an unhandled TclError.
        """
        initial_dir = self._folder_path or os.path.expanduser("~")
        last_error: Optional[tk.TclError] = None
        for _attempt in range(2):
            try:
                return filedialog.askdirectory(
                    parent=self,
                    title="Select folder with MP3 files",
                    initialdir=initial_dir,
                    mustexist=True,
                )
            except tk.TclError as exc:
                last_error = exc
        self._set_status(
            f"Could not open the folder dialog ({last_error}). Please try again.",
            state="error",
        )
        return ""

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
        # Cancel any in-progress load
        self._cancel_load.set()
        self._cancel_load = threading.Event()
        cancel_event = self._cancel_load

        # Clear the model immediately. The view reuses its recycled widget pool,
        # so we only blank out the data — no per-row widget destruction.
        self._tree_entries = []
        self._file_entries = []
        self._folder_entries = {}
        self._checked = {}
        self._expanded = {}
        self._folder_descendants = {}
        self._visible_entries = []
        self._tree.set_items([], reset=True)
        self._file_drafts.clear()
        self._selected_file = None
        self._selected_cover = None
        self._pending_cover_path = None
        self._pending_cover_name = ""
        self._selected_label.configure(text="No file selected")
        self._search_var.set("")
        self._clear_form()
        self._show_current_cover(None)

        # Show loading overlay and set busy status
        self._loading_overlay.show()
        self._set_status("กำลังโหลดไฟล์...", state="busy")

        def _do_load() -> Optional[list]:
            """Load entries in background thread."""
            entries = list_mp3_tree(folder)
            if cancel_event.is_set():
                return None
            return entries

        def _finish(entries: Optional[list]) -> None:
            """Finish loading on main thread."""
            self._loading_overlay.hide()

            if entries is None or not entries:
                self._tree_badge.configure(text="0 files")
                self._count_label.configure(text="")
                self._set_status("No MP3 files found in this folder", state="error")
                return

            # Build the data model from the scan results.
            self._tree_entries = entries
            self._file_entries = [e for e in entries if e.kind == "file"]
            self._folder_entries = {
                e.relative_path: e for e in entries if e.kind == "folder"
            }
            # Files start checked (preserving the prior default); folders start
            # expanded. A rename reload passes the previously-checked set instead.
            if checked_paths is not None:
                self._checked = {
                    e.path: (e.path in checked_paths) for e in self._file_entries
                }
            else:
                self._checked = {e.path: True for e in self._file_entries}
            self._expanded = {rel: True for rel in self._folder_entries}

            # Finalize tree structure and render the visible window.
            self._build_folder_descendants()
            self._refresh_tree(reset_scroll=True)
            self._set_status(
                f"Loaded {len(self._file_entries)} MP3 files from subfolders",
                state="ok",
            )

            # Select target entry
            target_entry = None
            if selected_path:
                target_entry = next(
                    (e for e in self._file_entries if e.path == selected_path),
                    None,
                )
            if target_entry is None and self._file_entries:
                target_entry = self._file_entries[0]
            if target_entry is not None:
                self._on_file_select(target_entry.path, target_entry)

        # Start background load
        def worker() -> None:
            try:
                entries = _do_load()
                self.after(0, lambda: _finish(entries))
            except Exception as e:
                self._loading_overlay.hide()
                self._set_status(f"Error loading folder: {e}", state="error")

        threading.Thread(target=worker, daemon=True).start()

    def _ancestor_paths(self, relative_path: str) -> List[str]:
        ancestors: List[str] = []
        current = os.path.dirname(relative_path)
        while current:
            ancestors.append(current)
            current = os.path.dirname(current)
        ancestors.reverse()
        return ancestors

    def _build_folder_descendants(self) -> None:
        self._folder_descendants = {path: [] for path in self._folder_entries}

        for file_entry in self._file_entries:
            for ancestor in self._ancestor_paths(file_entry.relative_path):
                if ancestor in self._folder_descendants:
                    self._folder_descendants[ancestor].append(file_entry)

    def _on_row_check(self, entry: MP3TreeEntry, checked: bool) -> None:
        """A checkbox was toggled in the tree view (folder or file)."""
        if entry.kind == "folder":
            descendants = self._folder_descendants.get(entry.relative_path, [])
            for file_entry in descendants:
                self._checked[file_entry.path] = checked
            self._tree.refresh_visible()
            self._update_counts()
            if descendants:
                action = "Selected" if checked else "Deselected"
                self._set_status(
                    f"{action} {len(descendants)} files in "
                    f"{os.path.basename(entry.relative_path)}",
                    state="ok",
                )
        else:
            self._checked[entry.path] = checked
            # Re-render so the row's ancestor folders update their tri-state count.
            self._tree.refresh_visible()
            self._update_counts()

    def _on_row_click(self, entry: MP3TreeEntry) -> None:
        """A row's name was clicked: folders expand/collapse, files get selected."""
        if entry.kind == "folder":
            self._expanded[entry.relative_path] = not self._expanded.get(
                entry.relative_path, True
            )
            self._refresh_tree()
        else:
            self._on_file_select(entry.path, entry)

    def _on_file_select(self, path: str, entry: MP3TreeEntry) -> None:
        self._store_current_file_draft()

        self._selected_file = path
        # Re-render visible rows so the active-row highlight follows the selection,
        # then make sure the selected row is scrolled into view.
        self._tree.refresh_visible()
        self._tree.scroll_to(path)
        self._selected_label.configure(text=entry.relative_path.replace("\\", " / "))

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
        if not self._file_entries:
            self._set_status("No files available to select", state="error")
            return

        should_check = not all(
            self._checked.get(e.path) for e in self._file_entries
        )
        for entry in self._file_entries:
            self._checked[entry.path] = should_check

        self._tree.refresh_visible()
        self._update_counts()
        if should_check:
            self._set_status(f"Selected {len(self._file_entries)} files", state="ok")
        else:
            self._set_status(f"Deselected {len(self._file_entries)} files", state="ok")

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
        checked_paths = set(self._checked_paths())

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
        return [e.path for e in self._file_entries if self._checked.get(e.path)]

    def _schedule_tree_filter(self) -> None:
        """Debounce filter input so visibility recomputes once typing settles.

        Each keystroke reschedules a single ``after`` job instead of running the
        O(folders x rows) visibility pass immediately, keeping typing smooth on
        large folder trees.
        """
        if self._search_job is not None:
            self.after_cancel(self._search_job)
        self._search_job = self.after(_SEARCH_DEBOUNCE_MS, self._run_tree_filter)

    def _run_tree_filter(self) -> None:
        self._search_job = None
        self._refresh_tree()

    def _refresh_tree(self, *, reset_scroll: bool = False) -> None:
        """Recompute the flattened visible-row list and hand it to the view.

        This is the single entry point that turns the data model (expanded /
        collapsed folders + the search filter) into the ordered list of rows the
        virtualized view renders.
        """
        self._recompute_visible()
        self._tree.set_items(self._visible_entries, reset=reset_scroll)
        self._update_counts()

    def _recompute_visible(self) -> None:
        query = self._search_var.get().strip().lower()
        if query:
            visible_paths = self._visible_paths_for_query(query)
            self._visible_entries = [
                e for e in self._tree_entries if e.relative_path in visible_paths
            ]
        else:
            self._visible_entries = [
                e for e in self._tree_entries if not self._has_collapsed_ancestor(e)
            ]

    def _visible_paths_for_query(self, query: str) -> set[str]:
        visible_paths: set[str] = set()
        separator = os.sep

        for folder in self._folder_entries.values():
            if query not in folder.relative_path.replace("\\", "/").lower():
                continue

            visible_paths.add(folder.relative_path)
            visible_paths.update(self._ancestor_paths(folder.relative_path))

            prefix = folder.relative_path + separator
            for entry in self._tree_entries:
                if entry.relative_path == folder.relative_path:
                    visible_paths.add(entry.relative_path)
                elif entry.relative_path.startswith(prefix):
                    visible_paths.add(entry.relative_path)

        for file_entry in self._file_entries:
            if query not in file_entry.relative_path.replace("\\", "/").lower():
                continue

            visible_paths.add(file_entry.relative_path)
            visible_paths.update(self._ancestor_paths(file_entry.relative_path))

        return visible_paths

    def _has_collapsed_ancestor(self, entry: MP3TreeEntry) -> bool:
        for ancestor in self._ancestor_paths(entry.relative_path):
            if ancestor in self._folder_entries and not self._expanded.get(
                ancestor, True
            ):
                return True
        return False

    def _bind_tree_row(self, row: "_PooledRow", entry: MP3TreeEntry) -> None:
        """View callback: render a recycled pooled row for ``entry``.

        Pulls all per-row state from the data model (checked / expanded /
        active / folder tri-state count) — the row widgets hold no state of
        their own, which is what lets the pool be recycled during scroll.
        """
        indent = 14 + entry.depth * 20
        if entry.kind == "folder":
            descendants = self._folder_descendants.get(entry.relative_path, [])
            total = len(descendants)
            checked = sum(1 for e in descendants if self._checked.get(e.path))
            if total == 0:
                count_text, count_color = "0/0", C_MUTED
            else:
                count_text = f"{checked}/{total}"
                if 0 < checked < total:
                    count_color = C_ACCENT
                elif checked == total:
                    count_color = C_TEXT
                else:
                    count_color = C_MUTED
            row.bind_folder(
                entry,
                indent=indent,
                checked_all=total > 0 and checked == total,
                count_text=count_text,
                count_color=count_color,
                expanded=self._expanded.get(entry.relative_path, True),
            )
        else:
            row.bind_file(
                entry,
                indent=indent,
                checked=self._checked.get(entry.path, False),
                active=entry.path == self._selected_file,
            )

    def _update_counts(self) -> None:
        total_files = len(self._file_entries)
        visible_files = sum(1 for e in self._visible_entries if e.kind == "file")
        checked_files = sum(1 for e in self._file_entries if self._checked.get(e.path))

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


class _PooledRow(ctk.CTkFrame):
    """A single recycled tree row.

    The view keeps a small pool of these and re-points them at different model
    entries as the user scrolls, so the widget count stays constant (about one
    screen's worth) regardless of library size. The row holds no persistent
    state of its own: ``bind_folder`` / ``bind_file`` push everything in from the
    model, which is what makes the pool safe to recycle.
    """

    def __init__(
        self,
        master,
        *,
        font,
        font_bold,
        on_check: Callable[["_PooledRow"], None],
        on_click: Callable[["_PooledRow"], None],
        on_wheel: Callable,
    ) -> None:
        super().__init__(master, fg_color="transparent", corner_radius=8)
        self.entry: Optional[MP3TreeEntry] = None
        self._model_index = -1
        self._kind: Optional[str] = None
        self._active = False
        self._hovered = False
        self._font = font
        self._font_bold = font_bold
        self._on_check = on_check
        self._on_click = on_click

        self.grid_columnconfigure(3, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._indent = ctk.CTkFrame(
            self, width=14, height=_TREE_ROW_HEIGHT, fg_color="transparent"
        )
        self._indent.grid(row=0, column=0, sticky="nsw")
        self._indent.grid_propagate(False)

        self._checked_var = tk.BooleanVar(value=False)
        self._checkbox = ctk.CTkCheckBox(
            self,
            text="",
            variable=self._checked_var,
            width=18,
            checkbox_width=16,
            checkbox_height=16,
            fg_color=C_ACCENT,
            hover_color=C_ACCENT_HOVER,
            border_width=2,
            border_color=C_BORDER,
            command=lambda: self._on_check(self),
        )
        self._checkbox.grid(row=0, column=1, padx=(0, 2))

        # The branch arrow (folders only) and the right-aligned tri-state count
        # (folders only) are gridded / ungridded by ``_layout_for`` per kind.
        self._branch_label = ctk.CTkLabel(
            self, text="", font=font_bold, text_color=C_MUTED, width=14
        )
        self._count_label = ctk.CTkLabel(
            self, text="", font=font_bold, text_color=C_MUTED, anchor="e", width=54
        )
        self._button = ctk.CTkButton(
            self,
            text="",
            font=font,
            anchor="w",
            fg_color="transparent",
            hover_color=C_ROW_HOVER,
            text_color=C_TEXT,
            corner_radius=6,
            height=30,
            command=lambda: self._on_click(self),
        )

        # Hover highlight (file rows only) mirrors the original _FileRow.
        for widget in (self, self._button):
            widget.bind("<Enter>", lambda _e: self._set_hover(True))
            widget.bind("<Leave>", lambda _e: self._set_hover(False))

        # Wheel events anywhere on the row drive the virtualized scroll.
        for widget in (
            self,
            self._indent,
            self._checkbox,
            self._branch_label,
            self._count_label,
            self._button,
        ):
            widget.bind("<MouseWheel>", on_wheel)

    @property
    def checked(self) -> bool:
        return self._checked_var.get()

    def _layout_for(self, kind: str) -> None:
        """(Re)grid the name / branch / count for the given kind.

        Folders show a branch arrow before the name and a tri-state count after
        it; files keep the name tight against the checkbox (spanning the branch
        column) with no count. We only re-grid when the slot's kind actually
        changes, so steady scrolling over same-kind rows pays nothing here.
        """
        if self._kind == kind:
            return
        self._kind = kind
        self._button.grid_forget()
        self._branch_label.grid_forget()
        self._count_label.grid_forget()
        if kind == "folder":
            self._branch_label.grid(row=0, column=2, sticky="w", padx=(0, 2))
            self._button.grid(row=0, column=3, sticky="ew", padx=(0, 8))
            self._count_label.grid(row=0, column=4, sticky="e", padx=(0, 8))
        else:
            self._button.grid(
                row=0, column=2, columnspan=2, sticky="ew", padx=(2, 8)
            )

    def bind_folder(
        self,
        entry: MP3TreeEntry,
        *,
        indent: int,
        checked_all: bool,
        count_text: str,
        count_color,
        expanded: bool,
    ) -> None:
        self.entry = entry
        self._active = False
        self._hovered = False
        self._layout_for("folder")
        self._indent.configure(width=indent)
        self._checked_var.set(checked_all)
        self._branch_label.configure(text="▾" if expanded else "▸")
        self._count_label.configure(text=count_text, text_color=count_color)
        self._button.configure(
            text=entry.name, font=self._font_bold, text_color=C_TEXT
        )
        self.configure(fg_color="transparent")

    def bind_file(
        self,
        entry: MP3TreeEntry,
        *,
        indent: int,
        checked: bool,
        active: bool,
    ) -> None:
        self.entry = entry
        self._active = active
        self._hovered = False
        self._layout_for("file")
        self._indent.configure(width=indent)
        self._checked_var.set(checked)
        self._button.configure(text=entry.name, font=self._font)
        self._apply_file_colors()

    def _set_hover(self, hovered: bool) -> None:
        if self._kind != "file":
            return
        self._hovered = hovered
        self._apply_file_colors()

    def _apply_file_colors(self) -> None:
        if self._active:
            self.configure(fg_color=C_ROW_SELECTED)
            self._button.configure(text_color=C_ROW_SELECTED_TEXT)
        elif self._hovered:
            self.configure(fg_color=C_ROW_HOVER)
            self._button.configure(text_color=C_TEXT)
        else:
            self.configure(fg_color="transparent")
            self._button.configure(text_color=C_TEXT)


class _VirtualTree(ctk.CTkFrame):
    """Virtualized folder-tree view.

    Renders only the rows in the current viewport using a recycled pool of
    ``_PooledRow`` widgets placed at absolute y-positions. With a fixed row
    height a scroll offset maps directly to a model-index range, so widget count
    and redraw cost stay flat whether the library has 50 files or 50,000.

    All row STATE (checked / expanded / active / counts) lives in the owner
    (``App``); this view only knows the ordered list of currently-visible
    entries and asks ``bind_row`` to paint each pooled widget.
    """

    def __init__(
        self,
        master,
        *,
        bind_row: Callable[["_PooledRow", MP3TreeEntry], None],
        on_check: Callable[[MP3TreeEntry, bool], None],
        on_click: Callable[[MP3TreeEntry], None],
        font,
        font_bold,
    ) -> None:
        super().__init__(master, fg_color=C_SURFACE, corner_radius=0)
        self._bind_row = bind_row
        self._on_check_cb = on_check
        self._on_click_cb = on_click
        self._font = font
        self._font_bold = font_bold

        self._items: List[MP3TreeEntry] = []
        self._item_index: Dict[str, int] = {}
        self._pool: List[_PooledRow] = []
        self._offset = 0
        self._last_body_h = 0

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._body = ctk.CTkFrame(self, fg_color=C_SURFACE, corner_radius=0)
        self._body.grid(row=0, column=0, sticky="nsew")

        self._scrollbar = ctk.CTkScrollbar(
            self,
            command=self._on_scrollbar,
            button_color=C_BORDER,
            button_hover_color=C_MUTED,
        )
        self._scrollbar.grid(row=0, column=1, sticky="ns", padx=(2, 0))

        self._body.bind("<Configure>", self._on_body_configure)
        for widget in (self, self._body):
            widget.bind("<MouseWheel>", self._on_wheel)

    # ---- public API used by App -------------------------------------------

    def set_items(self, items: List[MP3TreeEntry], *, reset: bool = False) -> None:
        self._items = items
        self._item_index = {entry.path: i for i, entry in enumerate(items)}
        if reset:
            self._offset = 0
        # Content changed: invalidate every slot so it rebinds.
        for slot in self._pool:
            slot._model_index = -1
        self._redraw(force=True)

    def refresh_visible(self) -> None:
        """Rebind the currently-visible rows (state changed, list did not)."""
        self._redraw(force=True)

    def scroll_to(self, path: str) -> None:
        idx = self._item_index.get(path)
        if idx is None:
            return
        height = self._body_height()
        top = idx * _TREE_ROW_HEIGHT
        bottom = top + _TREE_ROW_HEIGHT
        if top < self._offset:
            self._offset = top
        elif bottom > self._offset + height:
            self._offset = bottom - height
        self._redraw()

    # ---- scroll plumbing ---------------------------------------------------

    def _body_height(self) -> int:
        height = self._body.winfo_height()
        if height <= 1:
            height = self._last_body_h or 400
        return height

    def _on_body_configure(self, event) -> None:
        self._last_body_h = event.height
        self._redraw()

    def _on_wheel(self, event) -> str:
        if not self._items:
            return "break"
        if event.delta:
            steps = -int(event.delta / 120) or (-1 if event.delta > 0 else 1)
        else:
            steps = 0
        self._offset += steps * _TREE_ROW_HEIGHT * _TREE_WHEEL_ROWS
        self._redraw()
        return "break"

    def _on_scrollbar(self, *args) -> None:
        if not self._items:
            return
        total_h = len(self._items) * _TREE_ROW_HEIGHT
        height = self._body_height()
        if args[0] == "moveto":
            self._offset = int(float(args[1]) * total_h)
        elif args[0] == "scroll":
            amount = int(args[1])
            unit = args[2]
            if unit == "units":
                self._offset += amount * _TREE_ROW_HEIGHT * _TREE_WHEEL_ROWS
            else:
                self._offset += amount * height
        self._redraw()

    def _handle_check(self, row: "_PooledRow") -> None:
        if row.entry is not None:
            self._on_check_cb(row.entry, row.checked)

    def _handle_click(self, row: "_PooledRow") -> None:
        if row.entry is not None:
            self._on_click_cb(row.entry)

    def _ensure_pool(self, size: int) -> None:
        while len(self._pool) < size:
            row = _PooledRow(
                self._body,
                font=self._font,
                font_bold=self._font_bold,
                on_check=self._handle_check,
                on_click=self._handle_click,
                on_wheel=self._on_wheel,
            )
            row._model_index = -1
            self._pool.append(row)

    # ---- the core redraw ---------------------------------------------------

    def _redraw(self, force: bool = False) -> None:
        total = len(self._items)
        height = self._body_height()
        total_h = total * _TREE_ROW_HEIGHT
        max_offset = max(0, total_h - height)
        self._offset = max(0, min(self._offset, max_offset))
        offset = self._offset

        if total == 0:
            for slot in self._pool:
                if slot._model_index != -1:
                    slot.place_forget()
                    slot._model_index = -1
            self._scrollbar.set(0.0, 1.0)
            return

        first = offset // _TREE_ROW_HEIGHT
        window = height // _TREE_ROW_HEIGHT + 2
        last = min(total - 1, first + window)

        # Pool must exceed the window so distinct visible indices never collide
        # under the modulo slot assignment below.
        self._ensure_pool(window + 2)
        pool_size = len(self._pool)

        used = set()
        for m in range(first, last + 1):
            slot_index = m % pool_size
            slot = self._pool[slot_index]
            used.add(slot_index)
            if force or slot._model_index != m:
                self._bind_row(slot, self._items[m])
                slot._model_index = m
            slot.place(
                x=0,
                y=m * _TREE_ROW_HEIGHT - offset,
                relwidth=1.0,
                height=_TREE_ROW_HEIGHT,
            )

        for slot_index, slot in enumerate(self._pool):
            if slot_index not in used and slot._model_index != -1:
                slot.place_forget()
                slot._model_index = -1

        self._scrollbar.set(offset / total_h, min(1.0, (offset + height) / total_h))

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
