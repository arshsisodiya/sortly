#!/usr/bin/env python3
"""
FileOrganizer GUI
Modern tkinter-based interface for the smart file organizer.
"""

import os
import sys
import json
import threading
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from organizer_core import FileOrganizer, Settings, CATEGORIES, OrganizationPlan, format_human_timestamp

# ─── Theme Constants ──────────────────────────────────────────────────────────

THEME = {
    "bg":           "#0F1117",
    "bg2":          "#161B22",
    "bg3":          "#1C2128",
    "surface":      "#21262D",
    "border":       "#30363D",
    "accent":       "#58A6FF",
    "accent2":      "#3FB950",
    "accent3":      "#FF7B72",
    "accent4":      "#D2A8FF",
    "text":         "#E6EDF3",
    "text_dim":     "#7D8590",
    "text_muted":   "#484F58",
    "warning":      "#F0883E",
    "success":      "#3FB950",
    "error":        "#FF7B72",
}

FONTS = {
    "title":  ("Segoe UI", 22, "bold"),
    "h2":     ("Segoe UI", 14, "bold"),
    "h3":     ("Segoe UI", 11, "bold"),
    "body":   ("Segoe UI", 10),
    "small":  ("Segoe UI", 9),
    "mono":   ("Consolas", 9),
    "badge":  ("Segoe UI", 8, "bold"),
}

CAT_COLORS = {
    "Images":      "#FF6B9D",
    "Videos":      "#FF9F43",
    "Audio":       "#A29BFE",
    "Documents":   "#74B9FF",
    "Archives":    "#FFEAA7",
    "Code":        "#55EFC4",
    "Executables": "#FD79A8",
    "Fonts":       "#B2BEC3",
    "Others":      "#636E72",
}


# ─── Custom Widgets ───────────────────────────────────────────────────────────

class RoundedFrame(tk.Canvas):
    """A canvas-based rounded rectangle frame."""
    def __init__(self, parent, bg=THEME["surface"], radius=10, **kwargs):
        width  = kwargs.pop("width", 200)
        height = kwargs.pop("height", 100)
        super().__init__(parent, bg=THEME["bg"], highlightthickness=0,
                         width=width, height=height, **kwargs)
        self._bg = bg
        self._radius = radius
        self.bind("<Configure>", self._draw)

    def _draw(self, event=None):
        self.delete("all")
        w, h, r = self.winfo_width(), self.winfo_height(), self._radius
        self.create_arc(0, 0, 2*r, 2*r, start=90, extent=90, fill=self._bg, outline=self._bg)
        self.create_arc(w-2*r, 0, w, 2*r, start=0, extent=90, fill=self._bg, outline=self._bg)
        self.create_arc(0, h-2*r, 2*r, h, start=180, extent=90, fill=self._bg, outline=self._bg)
        self.create_arc(w-2*r, h-2*r, w, h, start=270, extent=90, fill=self._bg, outline=self._bg)
        self.create_rectangle(r, 0, w-r, h, fill=self._bg, outline=self._bg)
        self.create_rectangle(0, r, w, h-r, fill=self._bg, outline=self._bg)


class ModernButton(tk.Frame):
    def __init__(self, parent, text="", command=None, style="primary",
                 icon="", width=120, height=36, **kwargs):
        super().__init__(parent, bg=THEME["bg"], **kwargs)
        colors = {
            "primary":   (THEME["accent"],  "#FFFFFF"),
            "success":   (THEME["success"], "#FFFFFF"),
            "danger":    (THEME["error"],   "#FFFFFF"),
            "secondary": (THEME["surface"], THEME["text"]),
            "ghost":     (THEME["bg"],      THEME["text_dim"]),
        }
        self._bg, self._fg = colors.get(style, colors["primary"])
        self._hover_bg = self._lighten(self._bg)
        self._cmd = command

        self._btn = tk.Label(
            self, text=f"{icon}  {text}" if icon else text,
            bg=self._bg, fg=self._fg,
            font=FONTS["h3"], cursor="hand2",
            padx=16, pady=8, width=width//8,
        )
        self._btn.pack(fill="both", expand=True)
        self._btn.bind("<Button-1>", self._click)
        self._btn.bind("<Enter>",  self._enter)
        self._btn.bind("<Leave>",  self._leave)

    def _lighten(self, hex_color):
        try:
            r = min(255, int(hex_color[1:3], 16) + 20)
            g = min(255, int(hex_color[3:5], 16) + 20)
            b = min(255, int(hex_color[5:7], 16) + 20)
            return f"#{r:02x}{g:02x}{b:02x}"
        except Exception:
            return hex_color

    def _click(self, e):
        if self._cmd:
            self._cmd()

    def _enter(self, e):
        self._btn.config(bg=self._hover_bg)

    def _leave(self, e):
        self._btn.config(bg=self._bg)

    def config_text(self, text):
        self._btn.config(text=text)


class ToastNotification(tk.Toplevel):
    def __init__(self, parent, message, kind="info", duration=3000):
        super().__init__(parent)
        colors = {"info": THEME["accent"], "success": THEME["success"],
                  "error": THEME["error"], "warning": THEME["warning"]}
        color = colors.get(kind, THEME["accent"])

        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.configure(bg=THEME["bg2"])

        # Position bottom-right
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self.geometry(f"360x60+{sw-380}+{sh-100}")

        tk.Frame(self, bg=color, width=4).pack(side="left", fill="y")
        tk.Label(self, text=message, bg=THEME["bg2"], fg=THEME["text"],
                 font=FONTS["body"], padx=12, pady=12, wraplength=320,
                 justify="left").pack(side="left", fill="both", expand=True)

        self.after(duration, self.destroy)


class ProgressCard(tk.Frame):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, bg=THEME["bg2"], **kwargs)
        self._label = tk.Label(self, text="Ready", bg=THEME["bg2"],
                                fg=THEME["text_dim"], font=FONTS["small"])
        self._label.pack(anchor="w", padx=12, pady=(8, 4))

        bar_bg = tk.Frame(self, bg=THEME["border"], height=6)
        bar_bg.pack(fill="x", padx=12, pady=(0, 8))

        self._bar = tk.Frame(bar_bg, bg=THEME["accent"], height=6)
        self._bar.place(x=0, y=0, relheight=1, relwidth=0)
        self._bar_bg = bar_bg
        self._pct = tk.Label(self, text="", bg=THEME["bg2"],
                              fg=THEME["text_dim"], font=FONTS["small"])
        self._pct.pack(anchor="e", padx=12)

    def update_progress(self, current, total, message=""):
        pct = current / total if total > 0 else 0
        self._bar.place(relwidth=pct)
        self._label.config(text=message or "Processing…")
        pct_text = f"{pct*100:.0f}%  ({current}/{total})"
        self._pct.config(text=pct_text)
        self.update_idletasks()

    def reset(self, text="Ready"):
        self._bar.place(relwidth=0)
        self._label.config(text=text)
        self._pct.config(text="")


# ─── Main Application ─────────────────────────────────────────────────────────

class FileOrganizerApp(tk.Tk):
    def __init__(self):
        super().__init__()

        self.settings = Settings()
        self.organizer = FileOrganizer(
            settings=self.settings,
            progress_callback=self._on_progress,
        )
        self._current_plan: Optional[OrganizationPlan] = None
        self._current_folder: str = ""
        self._monitor_folders: List[str] = list(self.settings.get("monitored_folders", []))

        self._setup_window()
        self._build_ui()

    # ── Window Setup ─────────────────────────────────────────────────────────

    def _setup_window(self):
        self.title("FileOrganizer")
        self.geometry("1100x720")
        self.minsize(900, 600)
        self.configure(bg=THEME["bg"])

        # Try to set icon
        try:
            self.iconbitmap(default="")
        except Exception:
            pass

        # Configure ttk styles
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Treeview",
            background=THEME["surface"],
            foreground=THEME["text"],
            rowheight=26,
            fieldbackground=THEME["surface"],
            borderwidth=0,
            font=FONTS["body"],
        )
        style.configure("Treeview.Heading",
            background=THEME["bg3"],
            foreground=THEME["text_dim"],
            relief="flat",
            font=FONTS["small"],
        )
        style.map("Treeview", background=[("selected", THEME["accent"])])
        style.configure("TSeparator", background=THEME["border"])

        style.configure("Vertical.TScrollbar",
            background=THEME["surface"],
            borderwidth=0,
            arrowsize=12,
        )

    # ── UI Build ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        # ── Top Bar ──────────────────────────────────────────────────
        topbar = tk.Frame(self, bg=THEME["bg2"], height=56)
        topbar.pack(fill="x", side="top")
        topbar.pack_propagate(False)

        tk.Label(topbar, text="⚡ FileOrganizer", bg=THEME["bg2"],
                 fg=THEME["accent"], font=FONTS["title"]).pack(side="left", padx=20, pady=10)

        tk.Label(topbar, text="Smart Automatic File Organizer",
                 bg=THEME["bg2"], fg=THEME["text_dim"],
                 font=FONTS["small"]).pack(side="left", pady=10)

        # History indicator
        self._history_label = tk.Label(topbar, text="", bg=THEME["bg2"],
                                        fg=THEME["text_dim"], font=FONTS["small"])
        self._history_label.pack(side="right", padx=20)

        # ── Main Layout ───────────────────────────────────────────────
        main = tk.PanedWindow(self, orient="horizontal", bg=THEME["bg"],
                               sashwidth=1, sashrelief="flat")
        main.pack(fill="both", expand=True)

        # Left Sidebar
        sidebar = tk.Frame(main, bg=THEME["bg2"], width=240)
        main.add(sidebar, minsize=200)
        self._build_sidebar(sidebar)

        # Right Content
        content = tk.Frame(main, bg=THEME["bg"])
        main.add(content, minsize=500)
        self._build_content(content)

        # Update history labels after both topbar and sidebar widgets exist.
        self._update_history_label()

    def _build_sidebar(self, parent):
        # Section: Quick Organize
        self._sidebar_section(parent, "ORGANIZE")

        folder_frame = tk.Frame(parent, bg=THEME["bg2"])
        folder_frame.pack(fill="x", padx=12, pady=(0, 6))

        self._folder_var = tk.StringVar(value="No folder selected")
        folder_display = tk.Label(folder_frame, textvariable=self._folder_var,
                                   bg=THEME["surface"], fg=THEME["text"],
                                   font=FONTS["small"], anchor="w",
                                   padx=8, pady=6, wraplength=170, justify="left",
                                   cursor="hand2")
        folder_display.pack(fill="x", pady=2)
        folder_display.bind("<Button-1>", lambda e: self._pick_folder())

        ModernButton(parent, text="Select Folder", icon="📂",
                     command=self._pick_folder, style="secondary",
                     width=200).pack(fill="x", padx=12, pady=2)

        ModernButton(parent, text="Preview & Organize", icon="🔍",
                     command=self._do_preview, style="primary",
                     width=200).pack(fill="x", padx=12, pady=2)

        ModernButton(parent, text="Auto-Organize", icon="⚡",
                     command=self._do_auto_organize, style="success",
                     width=200).pack(fill="x", padx=12, pady=2)

        tk.Frame(parent, bg=THEME["border"], height=1).pack(fill="x", padx=12, pady=10)

        # Section: Undo
        self._sidebar_section(parent, "HISTORY")

        self._undo_info = tk.Label(parent, text="No history",
                                    bg=THEME["bg2"], fg=THEME["text_dim"],
                                    font=FONTS["small"], wraplength=190, justify="left")
        self._undo_info.pack(anchor="w", padx=12, pady=(0, 4))

        ModernButton(parent, text="Undo Last Action", icon="↩",
                     command=self._do_undo, style="secondary",
                     width=200).pack(fill="x", padx=12, pady=2)

        tk.Frame(parent, bg=THEME["border"], height=1).pack(fill="x", padx=12, pady=10)

        # Section: Monitor
        self._sidebar_section(parent, "REAL-TIME MONITOR")

        self._monitor_status = tk.Label(parent, text="🔴  Inactive",
                                         bg=THEME["bg2"], fg=THEME["text_dim"],
                                         font=FONTS["small"])
        self._monitor_status.pack(anchor="w", padx=12, pady=(0, 4))

        ModernButton(parent, text="Add Monitor Folder", icon="👁",
                     command=self._add_monitor_folder, style="secondary",
                     width=200).pack(fill="x", padx=12, pady=2)

        self._monitor_toggle = ModernButton(parent, text="Start Monitoring", icon="▶",
                                             command=self._toggle_monitor, style="ghost",
                                             width=200)
        self._monitor_toggle.pack(fill="x", padx=12, pady=2)

        tk.Frame(parent, bg=THEME["border"], height=1).pack(fill="x", padx=12, pady=10)

        # Mode toggle at bottom
        self._sidebar_section(parent, "MODE")
        mode_frame = tk.Frame(parent, bg=THEME["bg2"])
        mode_frame.pack(fill="x", padx=12, pady=(0, 8))

        self._auto_mode_var = tk.BooleanVar(value=self.settings.get("auto_mode", False))
        tk.Label(mode_frame, text="Auto Mode", bg=THEME["bg2"],
                 fg=THEME["text"], font=FONTS["small"]).pack(side="left")
        tk.Checkbutton(mode_frame, variable=self._auto_mode_var,
                       bg=THEME["bg2"], fg=THEME["accent"],
                       activebackground=THEME["bg2"],
                       selectcolor=THEME["bg3"],
                       command=self._toggle_auto_mode).pack(side="right")

    def _sidebar_section(self, parent, title):
        tk.Label(parent, text=title, bg=THEME["bg2"], fg=THEME["text_muted"],
                 font=FONTS["badge"]).pack(anchor="w", padx=12, pady=(10, 4))

    def _build_content(self, parent):
        # Notebook tabs
        tab_frame = tk.Frame(parent, bg=THEME["bg"])
        tab_frame.pack(fill="x", side="top")

        self._tabs = {}
        self._active_tab = tk.StringVar(value="preview")
        tab_defs = [
            ("preview", "📋  Preview"),
            ("activity", "📝  Activity Log"),
            ("rules", "⚙  Rules"),
            ("categories", "🗂  Categories"),
        ]

        for key, label in tab_defs:
            btn = tk.Label(tab_frame, text=label, bg=THEME["bg"],
                           fg=THEME["text_dim"], font=FONTS["body"],
                           padx=16, pady=10, cursor="hand2")
            btn.pack(side="left")
            btn.bind("<Button-1>", lambda e, k=key: self._switch_tab(k))
            self._tabs[key] = btn

        # Content frames
        self._tab_frames: dict = {}
        content_area = tk.Frame(parent, bg=THEME["bg"])
        content_area.pack(fill="both", expand=True, padx=16, pady=8)

        self._tab_frames["preview"]    = self._build_preview_tab(content_area)
        self._tab_frames["activity"]   = self._build_activity_tab(content_area)
        self._tab_frames["rules"]      = self._build_rules_tab(content_area)
        self._tab_frames["categories"] = self._build_categories_tab(content_area)

        self._switch_tab("preview")

        # Progress bar at bottom
        self._progress_card = ProgressCard(parent)
        self._progress_card.pack(fill="x", side="bottom", padx=16, pady=(0, 8))

    def _switch_tab(self, key: str):
        for k, frame in self._tab_frames.items():
            frame.pack_forget()
        self._tab_frames[key].pack(fill="both", expand=True)
        for k, btn in self._tabs.items():
            btn.config(bg=THEME["bg"],
                       fg=THEME["accent"] if k == key else THEME["text_dim"])
        self._active_tab.set(key)

    def _build_preview_tab(self, parent) -> tk.Frame:
        frame = tk.Frame(parent, bg=THEME["bg"])

        # Header
        hdr = tk.Frame(frame, bg=THEME["bg"])
        hdr.pack(fill="x", pady=(0, 8))
        self._preview_title = tk.Label(hdr, text="Select a folder to preview organization",
                                        bg=THEME["bg"], fg=THEME["text_dim"], font=FONTS["h2"])
        self._preview_title.pack(side="left")
        self._execute_btn = ModernButton(hdr, text="Execute Plan", icon="✓",
                                          command=self._execute_plan, style="success")
        self._execute_btn.pack(side="right")
        self._execute_btn._btn.config(state="disabled")

        # Stats row
        self._stats_frame = tk.Frame(frame, bg=THEME["bg"])
        self._stats_frame.pack(fill="x", pady=(0, 8))

        # File tree
        tree_frame = tk.Frame(frame, bg=THEME["bg"])
        tree_frame.pack(fill="both", expand=True)

        scrollbar = ttk.Scrollbar(tree_frame)
        scrollbar.pack(side="right", fill="y")

        self._preview_tree = ttk.Treeview(
            tree_frame,
            columns=("size", "destination", "category"),
            show="tree headings",
            yscrollcommand=scrollbar.set,
        )
        self._preview_tree.pack(fill="both", expand=True)
        scrollbar.config(command=self._preview_tree.yview)

        self._preview_tree.heading("#0", text="File Name")
        self._preview_tree.heading("size", text="Size")
        self._preview_tree.heading("destination", text="Destination")
        self._preview_tree.heading("category", text="Category")
        self._preview_tree.column("#0", width=280, minwidth=150)
        self._preview_tree.column("size", width=70, anchor="e")
        self._preview_tree.column("destination", width=250)
        self._preview_tree.column("category", width=100, anchor="center")

        # Color tags
        for cat, color in CAT_COLORS.items():
            self._preview_tree.tag_configure(cat, foreground=color)

        return frame

    def _build_activity_tab(self, parent) -> tk.Frame:
        frame = tk.Frame(parent, bg=THEME["bg"])

        hdr = tk.Frame(frame, bg=THEME["bg"])
        hdr.pack(fill="x", pady=(0, 8))
        tk.Label(hdr, text="Activity Log", bg=THEME["bg"],
                 fg=THEME["text"], font=FONTS["h2"]).pack(side="left")
        ModernButton(hdr, text="Clear", command=self._clear_log, style="ghost").pack(side="right")

        log_frame = tk.Frame(frame, bg=THEME["surface"])
        log_frame.pack(fill="both", expand=True)

        scrollbar = ttk.Scrollbar(log_frame, orient="vertical")
        scrollbar.pack(side="right", fill="y")

        self._log_text = tk.Text(
            log_frame,
            bg=THEME["surface"],
            fg=THEME["text"],
            font=FONTS["mono"],
            state="disabled",
            wrap="word",
            relief="flat",
            pady=8, padx=8,
            yscrollcommand=scrollbar.set,
        )
        self._log_text.pack(fill="both", expand=True)
        scrollbar.config(command=self._log_text.yview)

        # Text tags for coloring
        self._log_text.tag_configure("ts", foreground=THEME["text_muted"])
        self._log_text.tag_configure("info",    foreground=THEME["accent"])
        self._log_text.tag_configure("success", foreground=THEME["success"])
        self._log_text.tag_configure("error",   foreground=THEME["error"])
        self._log_text.tag_configure("warning", foreground=THEME["warning"])
        self._log_text.tag_configure("monitor", foreground=THEME["accent4"])

        return frame

    def _build_rules_tab(self, parent) -> tk.Frame:
        frame = tk.Frame(parent, bg=THEME["bg"])

        # Header
        hdr = tk.Frame(frame, bg=THEME["bg"])
        hdr.pack(fill="x", pady=(0, 12))
        tk.Label(hdr, text="Custom Rules", bg=THEME["bg"],
                 fg=THEME["text"], font=FONTS["h2"]).pack(side="left")
        ModernButton(hdr, text="+ Add Rule", command=self._add_rule_dialog,
                     style="primary").pack(side="right")

        tk.Label(frame, text="Rules are checked first. Files matching a pattern are sent to the specified category.",
                 bg=THEME["bg"], fg=THEME["text_dim"], font=FONTS["small"]).pack(anchor="w", pady=(0, 8))

        # Rules list
        rules_outer = tk.Frame(frame, bg=THEME["surface"])
        rules_outer.pack(fill="both", expand=True)

        scrollbar = ttk.Scrollbar(rules_outer)
        scrollbar.pack(side="right", fill="y")

        self._rules_list = tk.Listbox(
            rules_outer,
            bg=THEME["surface"], fg=THEME["text"],
            font=FONTS["body"],
            selectbackground=THEME["accent"],
            selectforeground=THEME["text"],
            relief="flat", highlightthickness=0,
            yscrollcommand=scrollbar.set,
        )
        self._rules_list.pack(fill="both", expand=True, padx=2, pady=2)
        scrollbar.config(command=self._rules_list.yview)

        btn_row = tk.Frame(frame, bg=THEME["bg"])
        btn_row.pack(fill="x", pady=8)
        ModernButton(btn_row, text="Remove Selected", icon="🗑",
                     command=self._remove_rule, style="danger").pack(side="left")

        self._refresh_rules_list()
        return frame

    def _build_categories_tab(self, parent) -> tk.Frame:
        frame = tk.Frame(parent, bg=THEME["bg"])

        tk.Label(frame, text="File Categories", bg=THEME["bg"],
                 fg=THEME["text"], font=FONTS["h2"]).pack(anchor="w", pady=(0, 8))

        canvas = tk.Canvas(frame, bg=THEME["bg"], highlightthickness=0)
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=canvas.yview)
        scroll_frame = tk.Frame(canvas, bg=THEME["bg"])

        scroll_frame.bind("<Configure>",
                          lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        for cat, info in CATEGORIES.items():
            color = CAT_COLORS.get(cat, THEME["text_dim"])
            icon = info.get("icon", "📁")
            exts = info.get("extensions", [])

            card = tk.Frame(scroll_frame, bg=THEME["surface"], pady=8, padx=12)
            card.pack(fill="x", pady=4, padx=4)

            tk.Label(card, text=f"{icon}  {cat}", bg=THEME["surface"],
                     fg=color, font=FONTS["h3"]).pack(anchor="w")

            ext_text = "  ".join(exts[:16]) if exts else "Catch-all for unrecognized files"
            if len(exts) > 16:
                ext_text += f"  … +{len(exts)-16} more"
            tk.Label(card, text=ext_text, bg=THEME["surface"],
                     fg=THEME["text_dim"], font=FONTS["small"],
                     wraplength=700, justify="left").pack(anchor="w", pady=(2, 0))

        return frame

    # ── Actions ───────────────────────────────────────────────────────────────

    def _pick_folder(self):
        folder = filedialog.askdirectory(title="Select folder to organize")
        if folder:
            self._current_folder = folder
            name = os.path.basename(folder) or folder
            self._folder_var.set(name)
            self._log(f"Folder selected: {folder}", "info")

    def _do_preview(self):
        if not self._current_folder:
            self._toast("Please select a folder first.", "warning")
            return
        self._switch_tab("preview")
        self._preview_title.config(text="Scanning…", fg=THEME["text_dim"])
        self._progress_card.reset("Scanning…")

        def run():
            plan, _ = self.organizer.organize_folder(self._current_folder, auto=False)
            self.after(0, lambda: self._display_plan(plan))

        threading.Thread(target=run, daemon=True).start()

    def _display_plan(self, plan: OrganizationPlan):
        self._current_plan = plan

        # Clear tree
        for item in self._preview_tree.get_children():
            self._preview_tree.delete(item)

        # Clear stats
        for w in self._stats_frame.winfo_children():
            w.destroy()

        if plan.total_files == 0:
            self._preview_title.config(text="✓  Already organized! Nothing to do.",
                                        fg=THEME["success"])
            self._execute_btn._btn.config(state="disabled")
            self._progress_card.reset("Folder is clean!")
            return

        self._preview_title.config(
            text=f"Preview: {plan.total_files} files to organize in {self._current_folder}",
            fg=THEME["text"])

        # Stats cards
        summary = plan.categories_summary
        for cat, count in sorted(summary.items(), key=lambda x: -x[1]):
            icon = CATEGORIES.get(cat, {}).get("icon", "📁")
            color = CAT_COLORS.get(cat, THEME["text_dim"])
            card = tk.Frame(self._stats_frame, bg=THEME["surface"], padx=10, pady=6)
            card.pack(side="left", padx=4)
            tk.Label(card, text=icon, bg=THEME["surface"], fg=color,
                     font=("Segoe UI", 14)).pack()
            tk.Label(card, text=str(count), bg=THEME["surface"], fg=color,
                     font=FONTS["h3"]).pack()
            tk.Label(card, text=cat, bg=THEME["surface"], fg=THEME["text_dim"],
                     font=FONTS["badge"]).pack()

        # Populate tree grouped by category
        grouped: dict = {}
        for src, dst, cat in plan.moves:
            grouped.setdefault(cat, []).append((src, dst))

        for cat, files in sorted(grouped.items()):
            icon = CATEGORIES.get(cat, {}).get("icon", "📁")
            parent_id = self._preview_tree.insert(
                "", "end", text=f"{icon}  {cat}  ({len(files)} files)",
                open=True, tags=(cat,),
                values=("", "", cat),
            )
            for src, dst in files:
                name = os.path.basename(src)
                try:
                    size_b = os.path.getsize(src)
                    for u in ["B","KB","MB","GB"]:
                        if size_b < 1024: break
                        size_b /= 1024
                    size_str = f"{size_b:.1f} {u}"
                except Exception:
                    size_str = "?"
                self._preview_tree.insert(
                    parent_id, "end", text=f"  {name}",
                    values=(size_str, os.path.basename(os.path.dirname(dst)), cat),
                    tags=(cat,),
                )

        self._execute_btn._btn.config(state="normal")
        self._progress_card.reset(f"{plan.total_files} files ready to organize")
        self._log(f"Preview: {plan.total_files} files → {len(summary)} categories", "info")

    def _execute_plan(self):
        if not self._current_plan or self._current_plan.total_files == 0:
            self._toast("No plan to execute.", "warning")
            return

        count = self._current_plan.total_files
        if not messagebox.askyesno(
            "Confirm Organization",
            f"Move {count} files into category folders in:\n{self._current_folder}\n\nThis can be undone.",
            icon="question",
        ):
            return

        self._execute_btn._btn.config(state="disabled")
        self._log(f"Executing plan: {count} files", "info")

        def run():
            records = self.organizer.execute_plan(self._current_plan, self._current_folder)
            self.after(0, lambda: self._on_execute_done(len(records)))

        threading.Thread(target=run, daemon=True).start()

    def _on_execute_done(self, count: int):
        self._toast(f"✓  Organized {count} files successfully!", "success")
        self._log(f"Organized {count} files. Session saved to history.", "success")
        self._update_history_label()
        self._current_plan = None
        # Refresh preview
        self._do_preview()

    def _do_auto_organize(self):
        if not self._current_folder:
            self._toast("Please select a folder first.", "warning")
            return

        if not messagebox.askyesno(
            "Auto-Organize",
            f"Auto-organize will immediately move all files.\n\nFolder: {self._current_folder}\n\nProceed?",
        ):
            return

        self._log(f"Auto-organizing: {self._current_folder}", "info")

        def run():
            plan, records = self.organizer.organize_folder(self._current_folder, auto=True)
            self.after(0, lambda: self._on_execute_done(len(records)))

        threading.Thread(target=run, daemon=True).start()

    def _do_undo(self):
        last = self.organizer.history.peek_last_session()
        if not last:
            self._toast("No history to undo.", "warning")
            return

        count = len(last.get("moves", []))
        if not messagebox.askyesno("Undo", f"Revert last {count} file move(s)?"):
            return

        ok, msg = self.organizer.undo_last()
        if ok:
            self._toast(msg, "success")
            self._log(f"Undo: {msg}", "success")
        else:
            self._toast(msg, "error")
            self._log(f"Undo error: {msg}", "error")
        self._update_history_label()
        self._do_preview()

    def _toggle_auto_mode(self):
        val = self._auto_mode_var.get()
        self.settings.set("auto_mode", val)
        mode = "Auto" if val else "Preview/Confirm"
        self._log(f"Mode changed to: {mode}", "info")

    # ── Monitor ───────────────────────────────────────────────────────────────

    def _add_monitor_folder(self):
        folder = filedialog.askdirectory(title="Select folder to monitor")
        if folder and folder not in self._monitor_folders:
            self._monitor_folders.append(folder)
            self._log(f"Added monitor folder: {folder}", "info")

    def _toggle_monitor(self):
        if self.organizer.is_monitoring:
            self.organizer.stop_monitoring()
            self._monitor_status.config(text="🔴  Inactive", fg=THEME["text_dim"])
            self._monitor_toggle.config_text("▶  Start Monitoring")
            self._log("Real-time monitoring stopped.", "info")
        else:
            if not self._monitor_folders:
                self._toast("Add at least one folder to monitor.", "warning")
                return
            self.organizer.start_monitoring(
                self._monitor_folders,
                callback=self._on_monitor_event,
            )
            self.settings.set("monitored_folders", self._monitor_folders)
            self._monitor_status.config(text=f"🟢  Watching {len(self._monitor_folders)} folder(s)",
                                         fg=THEME["success"])
            self._monitor_toggle.config_text("⏹  Stop Monitoring")
            self._log(f"Monitoring {len(self._monitor_folders)} folder(s)", "info")

    def _on_monitor_event(self, src, dst, category):
        self.after(0, lambda: self._log(
            f"[Monitor] {os.path.basename(src)} → {category}", "monitor"))

    # ── Rules ─────────────────────────────────────────────────────────────────

    def _refresh_rules_list(self):
        self._rules_list.delete(0, "end")
        rules = self.settings.get("custom_rules", [])
        for rule in rules:
            self._rules_list.insert("end", f"  '{rule['pattern']}'  →  {rule['category']}")

    def _add_rule_dialog(self):
        dialog = tk.Toplevel(self)
        dialog.title("Add Rule")
        dialog.geometry("380x200")
        dialog.configure(bg=THEME["bg2"])
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()

        tk.Label(dialog, text="Add Custom Rule", bg=THEME["bg2"],
                 fg=THEME["text"], font=FONTS["h2"]).pack(pady=(16, 8))

        form = tk.Frame(dialog, bg=THEME["bg2"])
        form.pack(padx=20, fill="x")

        tk.Label(form, text="Filename Pattern:", bg=THEME["bg2"],
                 fg=THEME["text_dim"], font=FONTS["small"]).pack(anchor="w")
        pattern_var = tk.StringVar()
        tk.Entry(form, textvariable=pattern_var, bg=THEME["surface"],
                 fg=THEME["text"], font=FONTS["body"], relief="flat",
                 insertbackground=THEME["text"]).pack(fill="x", pady=(0, 8))

        tk.Label(form, text="Category:", bg=THEME["bg2"],
                 fg=THEME["text_dim"], font=FONTS["small"]).pack(anchor="w")
        cat_var = tk.StringVar(value="Documents")
        cat_menu = ttk.Combobox(form, textvariable=cat_var,
                                 values=list(CATEGORIES.keys()),
                                 state="readonly", font=FONTS["body"])
        cat_menu.pack(fill="x", pady=(0, 12))

        def save():
            p = pattern_var.get().strip()
            c = cat_var.get().strip()
            if not p:
                messagebox.showerror("Error", "Pattern cannot be empty.")
                return
            rules = self.settings.get("custom_rules", [])
            rules.append({"pattern": p, "category": c})
            self.settings.set("custom_rules", rules)
            self.organizer.categorizer.custom_rules = rules
            self._refresh_rules_list()
            self._log(f"Rule added: '{p}' → {c}", "success")
            dialog.destroy()

        ModernButton(dialog, text="Add Rule", command=save,
                     style="primary").pack(pady=4)

    def _remove_rule(self):
        sel = self._rules_list.curselection()
        if not sel:
            self._toast("Select a rule to remove.", "warning")
            return
        idx = sel[0]
        rules = self.settings.get("custom_rules", [])
        if 0 <= idx < len(rules):
            removed = rules.pop(idx)
            self.settings.set("custom_rules", rules)
            self.organizer.categorizer.custom_rules = rules
            self._refresh_rules_list()
            self._log(f"Rule removed: '{removed['pattern']}'", "info")

    # ── Utilities ─────────────────────────────────────────────────────────────

    def _on_progress(self, current, total, message=""):
        self.after(0, lambda: self._progress_card.update_progress(current, total, message))

    def _update_history_label(self):
        count = self.organizer.history.session_count
        last = self.organizer.history.peek_last_session()
        if last:
            ts = format_human_timestamp(last.get("timestamp", ""))
            n  = len(last.get("moves", []))
            self._undo_info.config(text=f"Last: {ts}\n{n} file(s) moved")
        else:
            self._undo_info.config(text="No history")
        self._history_label.config(
            text=f"{count} session(s) in history" if count else "")

    def _log(self, message: str, level: str = "info"):
        ts = time.strftime("%H:%M:%S")
        self._log_text.config(state="normal")
        self._log_text.insert("end", f"[{ts}] ", "ts")
        self._log_text.insert("end", f"{message}\n", level)
        self._log_text.see("end")
        self._log_text.config(state="disabled")

    def _clear_log(self):
        self._log_text.config(state="normal")
        self._log_text.delete("1.0", "end")
        self._log_text.config(state="disabled")

    def _toast(self, message: str, kind: str = "info"):
        ToastNotification(self, message, kind=kind)

    def on_close(self):
        if self.organizer.is_monitoring:
            self.organizer.stop_monitoring()
        self.destroy()


# ─── Entry Point ──────────────────────────────────────────────────────────────

def main():
    app = FileOrganizerApp()
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()


if __name__ == "__main__":
    main()
