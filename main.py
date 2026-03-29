"""MP3 Tag Editor — Modern Tailwind-inspired UI"""

from __future__ import annotations

import os
import threading
from typing import Dict, List, Optional, Tuple

import customtkinter as ctk
import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog

from tag_utils import (
    fill_titles_from_filenames,
    list_mp3_files,
    load_mp3_tags,
    save_tags_to_files,
)

# ── Thai font detection ───────────────────────────────────────────────────────
_THAI_FONT_PRIORITY = ["Leelawadee UI", "Tahoma", "Segoe UI", "Arial Unicode MS"]

# ── Design tokens: (light_value, dark_value) — CTk auto-switches on mode change
C_BG         = ("#f1f5f9", "#0d1117")    # window background
C_SURFACE    = ("#ffffff", "#161b22")    # card / panel
C_SURFACE_B  = ("#f8fafc", "#1c2230")   # recessed input / badge bg
C_BORDER     = ("#e2e8f0", "#30363d")   # default border
C_TEXT       = ("#0f172a", "#e6edf3")   # primary text
C_MUTED      = ("#64748b", "#8b949e")   # secondary / placeholder text
C_ACCENT     = ("#2563eb", "#3b82f6")   # primary action (blue)
C_ACCENT_H   = ("#1d4ed8", "#60a5fa")   # primary hover
C_SUCCESS    = ("#16a34a", "#22c55e")   # save button (green)
C_SUCCESS_H  = ("#15803d", "#4ade80")   # save button hover
C_ROW_SEL    = ("#dbeafe", "#1d3a6e")   # selected file row
C_ROW_HOV    = ("#f0f7ff", "#1a2744")   # hovered file row
C_DOT_OK     = ("#22c55e", "#22c55e")   # status dot — ready/ok
C_DOT_ERR    = ("#ef4444", "#ef4444")   # status dot — error
C_DOT_BUSY   = ("#f59e0b", "#f59e0b")   # status dot — working

# ── Field groups: (field_key, label, columns_out_of_4) ───────────────────────
# 4-column grid inside the form. each entry occupies N of those columns.
_FIELD_GROUPS: List[List[Tuple[str, str, int]]] = [
    [("title",  "Title",  4)],
    [("artist", "Artist", 2), ("album", "Album",  2)],
    [("year",   "Year",   1), ("track", "Track",  1), ("genre", "Genre", 2)],
]
FIELDS = ["title", "artist", "album", "year", "track", "genre"]


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  App                                                                        ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

class App(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.title("MP3 Tag Editor")
        self.geometry("1060x680")
        self.minsize(800, 520)
        self.configure(fg_color=C_BG)

        ff = self._detect_thai_font()
        self._fn    = ctk.CTkFont(family=ff, size=13)
        self._fn_sm = ctk.CTkFont(family=ff, size=12)
        self._fn_xs = ctk.CTkFont(family=ff, size=11)
        self._fn_h  = ctk.CTkFont(family=ff, size=13, weight="bold")

        self._rows: List[_FileRow] = []
        self._selected: Optional[str] = None
        self._cancel_load = threading.Event()

        self._build_ui()

    # ── Font detection ────────────────────────────────────────────────────────

    def _detect_thai_font(self) -> str:
        available = set(tkfont.families(self))
        for name in _THAI_FONT_PRIORITY:
            if name in available:
                return name
        return "TkDefaultFont"

    # ── UI Construction ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        self._build_topbar()

        content = ctk.CTkFrame(self, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=12, pady=(8, 0))
        content.columnconfigure(0, weight=5, minsize=260)
        content.columnconfigure(1, weight=7, minsize=400)
        content.rowconfigure(0, weight=1)

        self._build_file_panel(content)
        self._build_tag_panel(content)
        self._build_statusbar()

    # ── Top bar ───────────────────────────────────────────────────────────────

    def _build_topbar(self) -> None:
        bar = ctk.CTkFrame(self, height=50, corner_radius=0, fg_color=C_SURFACE)
        bar.pack(fill="x")
        bar.pack_propagate(False)

        # App name
        ctk.CTkLabel(
            bar, text="♫  MP3 Tag Editor",
            font=self._fn_h, text_color=C_TEXT, anchor="w",
        ).pack(side="left", padx=(18, 0))

        # Thin separator
        ctk.CTkFrame(bar, width=1, fg_color=C_BORDER).pack(
            side="left", fill="y", padx=14, pady=10
        )

        # Open folder button
        ctk.CTkButton(
            bar, text="📁  Open Folder",
            font=self._fn_sm,
            fg_color=C_ACCENT, hover_color=C_ACCENT_H,
            text_color=("white", "white"),
            width=130, height=34, corner_radius=6,
            command=self._pick_folder,
        ).pack(side="left", pady=8)

        # Current path (truncated)
        self._lbl_path = ctk.CTkLabel(
            bar, text="No folder selected",
            font=self._fn_sm, text_color=C_MUTED, anchor="w",
        )
        self._lbl_path.pack(side="left", fill="x", expand=True, padx=(10, 0))

        # Mode toggle (icon button, right side)
        self._btn_mode = ctk.CTkButton(
            bar, text="☀",
            font=ctk.CTkFont(size=16),
            fg_color="transparent", hover_color=C_SURFACE_B,
            text_color=C_MUTED,
            width=38, height=38, corner_radius=8,
            command=self._toggle_mode,
        )
        self._btn_mode.pack(side="right", padx=(0, 14))

        # Bottom hairline border
        ctk.CTkFrame(self, height=1, fg_color=C_BORDER, corner_radius=0).pack(fill="x")

    # ── File panel (left) ─────────────────────────────────────────────────────

    def _build_file_panel(self, parent) -> None:
        panel = ctk.CTkFrame(
            parent, fg_color=C_SURFACE,
            corner_radius=10, border_width=1, border_color=C_BORDER,
        )
        panel.grid(row=0, column=0, sticky="nsew", padx=(0, 6), pady=(0, 8))
        panel.rowconfigure(2, weight=1)
        panel.columnconfigure(0, weight=1)

        # Header row: "Files" label + badge + All/None toggle
        hdr = ctk.CTkFrame(panel, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew", padx=14, pady=(12, 0))
        hdr.columnconfigure(1, weight=1)

        ctk.CTkLabel(
            hdr, text="Files",
            font=self._fn_h, text_color=C_TEXT,
        ).grid(row=0, column=0, sticky="w")

        self._badge = ctk.CTkLabel(
            hdr, text="",
            font=self._fn_xs, text_color=C_MUTED,
            fg_color=C_SURFACE_B, corner_radius=8,
            width=42, height=20,
        )
        self._badge.grid(row=0, column=1, sticky="w", padx=(8, 0))

        self._btn_all = ctk.CTkButton(
            hdr, text="All",
            font=self._fn_xs,
            fg_color="transparent", hover_color=C_SURFACE_B,
            text_color=C_MUTED, border_width=1, border_color=C_BORDER,
            width=40, height=24, corner_radius=5,
            command=self._toggle_all,
        )
        self._btn_all.grid(row=0, column=2, sticky="e")

        # Search / filter box
        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", lambda *_: self._filter_rows())

        ctk.CTkEntry(
            panel, textvariable=self._search_var,
            placeholder_text="🔍  Filter files…",
            font=self._fn_sm,
            fg_color=C_SURFACE_B, border_color=C_BORDER,
            text_color=C_TEXT, placeholder_text_color=C_MUTED,
            height=34, corner_radius=7,
        ).grid(row=1, column=0, sticky="ew", padx=12, pady=(8, 4))

        # Scrollable file list
        self._scroll = ctk.CTkScrollableFrame(
            panel,
            fg_color=C_SURFACE,
            scrollbar_button_color=C_BORDER,
            scrollbar_button_hover_color=C_MUTED,
            corner_radius=0,
        )
        self._scroll.grid(row=2, column=0, sticky="nsew", padx=6, pady=(0, 8))
        self._scroll.columnconfigure(0, weight=1)

    # ── Tag editor panel (right) ───────────────────────────────────────────────

    def _build_tag_panel(self, parent) -> None:
        panel = ctk.CTkFrame(
            parent, fg_color=C_SURFACE,
            corner_radius=10, border_width=1, border_color=C_BORDER,
        )
        panel.grid(row=0, column=1, sticky="nsew", padx=(6, 0), pady=(0, 8))
        panel.rowconfigure(1, weight=1)
        panel.columnconfigure(0, weight=1)

        # Header row: "Tag Editor" + selected filename
        hdr = ctk.CTkFrame(panel, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew", padx=16, pady=(12, 0))
        hdr.columnconfigure(1, weight=1)

        ctk.CTkLabel(
            hdr, text="Tag Editor",
            font=self._fn_h, text_color=C_TEXT,
        ).grid(row=0, column=0, sticky="w")

        self._lbl_selected = ctk.CTkLabel(
            hdr, text="No file selected",
            font=self._fn_xs, text_color=C_MUTED, anchor="e",
        )
        self._lbl_selected.grid(row=0, column=1, sticky="e")

        # Inner form frame (not scrollable — fields are compact)
        inner = ctk.CTkFrame(panel, fg_color="transparent")
        inner.grid(row=1, column=0, sticky="nsew")

        self._entries: Dict[str, ctk.CTkEntry] = {}
        self._build_fields(inner)

    def _build_fields(self, parent) -> None:
        """Build grouped field rows inside the tag panel."""
        fields_container = ctk.CTkFrame(parent, fg_color="transparent")
        fields_container.pack(fill="x", padx=16, pady=(10, 0))

        for group in _FIELD_GROUPS:
            row_frame = ctk.CTkFrame(fields_container, fg_color="transparent")
            row_frame.pack(fill="x", pady=(0, 6))
            n = len(group)
            for i in range(n):
                row_frame.columnconfigure(i, weight=group[i][2], uniform="flds")

            for col_i, (field, label, _) in enumerate(group):
                col = ctk.CTkFrame(row_frame, fg_color="transparent")
                col.grid(
                    row=0, column=col_i, sticky="ew",
                    padx=(0, 8) if col_i < n - 1 else (0, 0),
                )
                ctk.CTkLabel(
                    col, text=label,
                    font=self._fn_xs, text_color=C_MUTED, anchor="w",
                ).pack(anchor="w", pady=(0, 3))
                entry = ctk.CTkEntry(
                    col, font=self._fn,
                    fg_color=C_SURFACE_B, border_color=C_BORDER,
                    text_color=C_TEXT, placeholder_text_color=C_MUTED,
                    height=36, corner_radius=7,
                )
                entry.pack(fill="x")
                self._entries[field] = entry

        # ── Action buttons ─────────────────────────────────────────────────────
        action_bar = ctk.CTkFrame(parent, fg_color="transparent")
        action_bar.pack(fill="x", padx=16, pady=(16, 16), side="bottom")
        action_bar.columnconfigure(0, weight=3)
        action_bar.columnconfigure(1, weight=2)

        ctk.CTkButton(
            action_bar, text="◈  Fill Title from Filename",
            font=self._fn_sm,
            fg_color="transparent", hover_color=C_SURFACE_B,
            text_color=C_MUTED, border_width=1, border_color=C_BORDER,
            height=40, corner_radius=8,
            command=self._fill_titles,
        ).grid(row=0, column=0, sticky="ew", padx=(0, 8))

        self._btn_save = ctk.CTkButton(
            action_bar, text="💾  Save",
            font=self._fn_h,
            fg_color=C_SUCCESS, hover_color=C_SUCCESS_H,
            text_color=("white", "white"),
            height=40, corner_radius=8,
            command=self._save,
        )
        self._btn_save.grid(row=0, column=1, sticky="ew")

    # ── Status bar (bottom) ───────────────────────────────────────────────────

    def _build_statusbar(self) -> None:
        ctk.CTkFrame(self, height=1, fg_color=C_BORDER, corner_radius=0).pack(fill="x", side="bottom")

        bar = ctk.CTkFrame(self, height=32, corner_radius=0, fg_color=C_SURFACE)
        bar.pack(fill="x", side="bottom")
        bar.pack_propagate(False)

        # Status dot (small colored circle via CTkFrame)
        self._status_dot = ctk.CTkFrame(
            bar, width=8, height=8, corner_radius=4, fg_color=C_DOT_OK,
        )
        self._status_dot.pack(side="left", padx=(14, 8))
        self._status_dot.pack_propagate(False)

        self._status_var = tk.StringVar(value="Ready")
        ctk.CTkLabel(
            bar, textvariable=self._status_var,
            font=self._fn_sm, text_color=C_MUTED, anchor="w",
        ).pack(side="left", fill="x", expand=True)

        # Right-side: selection count
        self._lbl_count = ctk.CTkLabel(
            bar, text="",
            font=self._fn_xs, text_color=C_MUTED, anchor="e",
        )
        self._lbl_count.pack(side="right", padx=(0, 14))

    # ── Folder ────────────────────────────────────────────────────────────────

    def _pick_folder(self) -> None:
        folder = filedialog.askdirectory(title="Select folder with MP3 files")
        if not folder:
            return
        display = folder if len(folder) <= 65 else "…" + folder[-62:]
        self._lbl_path.configure(text=display)
        self._load_folder(folder)

    def _load_folder(self, folder: str) -> None:
        for row in self._rows:
            row.destroy()
        self._rows.clear()
        self._selected = None
        self._clear_form()
        self._lbl_selected.configure(text="No file selected")
        self._search_var.set("")

        files = list_mp3_files(folder)
        if not files:
            self._set_status("No MP3 files found in this folder", state="error")
            self._badge.configure(text="0")
            return

        for path in files:
            row = _FileRow(
                self._scroll, path,
                font=self._fn_sm,
                on_select=self._on_file_select,
                on_check=self._on_check_change,
            )
            row.pack(fill="x")
            self._rows.append(row)

        self._update_counts()
        self._set_status(f"Loaded {len(files)} files", state="ok")

    # ── File selection ────────────────────────────────────────────────────────

    def _on_file_select(self, path: str, row: "_FileRow") -> None:
        for r in self._rows:
            r.set_active(r is row)

        self._selected = path
        self._lbl_selected.configure(text=os.path.basename(path))

        self._cancel_load.set()
        cancel = threading.Event()
        self._cancel_load = cancel

        self._set_status("Loading tags…", state="busy")

        def _worker() -> None:
            tags = load_mp3_tags(path)
            if not cancel.is_set():
                self.after(0, lambda: self._fill_form(tags))
                self.after(0, lambda: self._set_status(
                    os.path.basename(path), state="ok"
                ))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_check_change(self) -> None:
        self._update_counts()

    # ── Form helpers ──────────────────────────────────────────────────────────

    def _clear_form(self) -> None:
        for e in self._entries.values():
            e.delete(0, "end")

    def _fill_form(self, tags: Dict[str, str]) -> None:
        for field, e in self._entries.items():
            e.delete(0, "end")
            v = tags.get(field, "")
            if v:
                e.insert(0, v)

    def _form_data(self) -> Dict[str, str]:
        return {f: self._entries[f].get().strip() for f in FIELDS}

    # ── List helpers ──────────────────────────────────────────────────────────

    def _toggle_all(self) -> None:
        visible = [r for r in self._rows if r.is_visible]
        all_on = all(r.checked for r in visible)
        for r in visible:
            r.set_checked(not all_on)
        self._update_counts()

    def _checked_paths(self) -> List[str]:
        return [r.path for r in self._rows if r.checked and r.is_visible]

    def _filter_rows(self) -> None:
        q = self._search_var.get().lower()
        for row in self._rows:
            match = not q or q in os.path.basename(row.path).lower()
            row.show() if match else row.hide()
        self._update_counts()

    def _update_counts(self) -> None:
        total   = len(self._rows)
        visible = sum(1 for r in self._rows if r.is_visible)
        checked = sum(1 for r in self._rows if r.checked and r.is_visible)

        badge_text = str(total) if visible == total else f"{visible}/{total}"
        self._badge.configure(text=badge_text)
        self._lbl_count.configure(text=f"{checked} selected" if checked else "")
        save_label = f"💾  Save  ({checked})" if checked else "💾  Save"
        self._btn_save.configure(text=save_label)

    # ── Fill from filename ────────────────────────────────────────────────────

    def _fill_titles(self) -> None:
        paths = self._checked_paths()
        if not paths:
            self._set_status("No files selected", state="error")
            return

        self._set_status(f"Filling {len(paths)} titles from filenames…", state="busy")

        def _worker() -> None:
            count, errors = fill_titles_from_filenames(paths)
            ok = not errors
            msg = f"Filled {count} title(s) from filename"
            if errors:
                msg += f"  ·  {len(errors)} error(s)"

            def _done() -> None:
                self._set_status(msg, state="ok" if ok else "error")
                if self._selected and self._selected in paths:
                    self._fill_form(load_mp3_tags(self._selected))

            self.after(0, _done)

        threading.Thread(target=_worker, daemon=True).start()

    # ── Save ──────────────────────────────────────────────────────────────────

    def _save(self) -> None:
        paths = self._checked_paths()
        if not paths:
            self._set_status("No files selected", state="error")
            return

        data = self._form_data()
        if not any(data.values()):
            self._set_status("Fill in at least one tag field before saving", state="error")
            return

        self._set_status(f"Saving {len(paths)} file(s)…", state="busy")

        def _worker() -> None:
            count, errors = save_tags_to_files(paths, data)
            ok = not errors
            msg = f"Saved {count} file(s)"
            if errors:
                msg += f"  ·  {len(errors)} error(s)"
            self.after(0, lambda: self._set_status(msg, state="ok" if ok else "error"))

        threading.Thread(target=_worker, daemon=True).start()

    # ── Mode toggle ───────────────────────────────────────────────────────────

    def _toggle_mode(self) -> None:
        is_dark = ctk.get_appearance_mode() == "Dark"
        ctk.set_appearance_mode("light" if is_dark else "dark")
        self._btn_mode.configure(text="☀" if not is_dark else "☾")

    # ── Status bar ────────────────────────────────────────────────────────────

    def _set_status(self, msg: str, state: str = "ok") -> None:
        self._status_var.set(msg)
        dot = {"ok": C_DOT_OK, "error": C_DOT_ERR, "busy": C_DOT_BUSY}.get(state, C_DOT_OK)
        self._status_dot.configure(fg_color=dot)


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  _FileRow — one row in the file list                                        ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

class _FileRow(ctk.CTkFrame):
    """Compact file row: checkbox (tick only) + filename label with hover fx."""

    def __init__(
        self,
        master,
        path: str,
        font,
        on_select,
        on_check,
        **kw,
    ) -> None:
        super().__init__(master, fg_color="transparent", corner_radius=5, **kw)
        self.path = path
        self._on_select = on_select
        self._on_check = on_check
        self._active = False
        self._hovered = False
        self._visible = True

        self.columnconfigure(1, weight=1)

        self._var = tk.BooleanVar(value=True)

        # Checkbox — toggle only; does NOT trigger file selection
        self._cb = ctk.CTkCheckBox(
            self, text="", variable=self._var,
            width=24, checkbox_width=16, checkbox_height=16,
            fg_color=C_ACCENT, hover_color=C_ACCENT_H,
            onvalue=True, offvalue=False,
            command=self._cb_toggled,
        )
        self._cb.grid(row=0, column=0, padx=(8, 2), pady=4)

        # Filename label — click to select & load tags
        name = os.path.basename(path)
        display = name if len(name) <= 52 else name[:49] + "…"
        self._lbl = ctk.CTkLabel(
            self, text=display, font=font,
            text_color=C_TEXT, anchor="w", cursor="hand2",
        )
        self._lbl.grid(row=0, column=1, sticky="ew", padx=(2, 10), pady=4)

        # Click / hover bindings on all parts of the row
        for widget in (self, self._lbl):
            widget.bind("<Button-1>", lambda _e: on_select(path, self))
            widget.bind("<Enter>",    lambda _e: self._hover(True))
            widget.bind("<Leave>",    lambda _e: self._hover(False))
        for widget in (self._cb,):
            widget.bind("<Enter>", lambda _e: self._hover(True))
            widget.bind("<Leave>", lambda _e: self._hover(False))

    def _cb_toggled(self) -> None:
        self._on_check()

    def _hover(self, on: bool) -> None:
        self._hovered = on
        self._refresh()

    def _refresh(self) -> None:
        if self._active:
            self.configure(fg_color=C_ROW_SEL)
        elif self._hovered:
            self.configure(fg_color=C_ROW_HOV)
        else:
            self.configure(fg_color="transparent")

    def set_active(self, active: bool) -> None:
        self._active = active
        self._lbl.configure(
            text_color=("#1d4ed8", "#93c5fd") if active else C_TEXT
        )
        self._refresh()

    @property
    def checked(self) -> bool:
        return self._var.get()

    def set_checked(self, value: bool) -> None:
        self._var.set(value)

    @property
    def is_visible(self) -> bool:
        return self._visible

    def show(self) -> None:
        if not self._visible:
            self._visible = True
            self.pack(fill="x")

    def hide(self) -> None:
        if self._visible:
            self._visible = False
            self.pack_forget()


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = App()
    app.mainloop()
