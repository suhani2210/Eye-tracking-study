"""
Cognitive Fatigue Induction Task — CFIT v1.1
==============================================
A working memory task designed to progressively induce fatigue
for eye-tracking ground truth data collection.

Levels:
  1 — Grid recall (shapes + positions)
  2 — Grid recall + alphanumeric code entry
  3 — Grid recall + code + PVT falling-digit catch task (dual-task)

Level 3 PVT mechanic:
  During the RECALL phase, random single digits fall from the top of the
  right panel at random intervals (2–10 s gaps, matching classic PVT).
  The participant must CLICK exactly 3 falling digits before they reach
  the bottom.  Each successful catch is logged with its reaction time.
  Missing a digit (it reaches the bottom) counts as a LAPSE.
  After 3 catches the mini-game ends; remaining digits keep falling as
  distractors until the participant submits their recall answer.

Self-report fatigue check every N trials (no recovery gap).
All responses logged to CSV with timestamps.
"""

import tkinter as tk
from tkinter import font as tkfont
import random
import string
import time
import csv
import os
import math
from datetime import datetime

#  CONSTANTS & CONFIG

GRID_SIZE          = 4      # 4x4
BLANK_TIME_MS      = 500    # blank between stimulus and recall
TRIALS_PER_BLOCK   = 5      # fatigue check fires after this many trials

SHAPES = ["●", "■", "▲", "◆", "★", "⬟", "⬡"]
COLORS = {
    "●": "#E84855",
    "■": "#3D9EE4",
    "▲": "#F0C040",
    "◆": "#7DCE82",
    "★": "#E07BE0",
    "⬟": "#FF8C42",
    "⬡": "#40E0D0",
}
LEVEL_CONFIG = {
    1: {"shapes_shown": 3, "display_ms": 2500,  "code_len": 0, "pvt": False,
        "label": "Level 1 — Grid Recall"},
    2: {"shapes_shown": 3, "display_ms": 6000,  "code_len": 3, "pvt": False,
        "label": "Level 2 — Grid + Code"},
    3: {"shapes_shown": 4, "display_ms": 10000, "code_len": 3, "pvt": True,
        "label": "Level 3 — Grid + Code + PVT"},
}

# PVT config
PVT_TARGETS_REQUIRED      = 3      # sequence length — must catch this many IN ORDER
PVT_TICK_MS               = 16     # ~60 fps animation tick
PVT_BASE_SPEED            = 1.8    # px per tick at trial start
PVT_ACCEL_INTERVAL_S      = 12     # every N seconds, digits speed up
PVT_ACCEL_FACTOR          = 1.25   # multiply speed by this each interval
PVT_MAX_SPEED             = 7.0    # cap so it never becomes impossible
PVT_SPEED_VARIANCE        = 0.4    # per-digit variance around current speed
PVT_SPAWN_INTERVAL_MS_MIN = 1800
PVT_SPAWN_INTERVAL_MS_MAX = 7000
PVT_DECOY_PROBABILITY     = 0.30   # 30 pct of spawns are red decoys
PVT_PANEL_W               = 340    # width of right PVT canvas area
PVT_PANEL_H               = 310    # shorter so Submit button stays visible

PVT_ACTIVE  = "#FFD166"   # target digit (not yet needed)
PVT_NEXT    = "#6CF5C2"   # digit you must catch right now
PVT_DECOY   = "#E84855"   # decoy — clicking resets progress one step
PVT_CAUGHT  = "#4CAF50"   # brief flash on correct catch
PVT_PENALTY = "#FF6584"   # brief flash on decoy click

# Colour palette
BG         = "#0D0D12"
SURFACE    = "#16161E"
SURFACE2   = "#1E1E2A"
ACCENT     = "#6C63FF"
ACCENT2    = "#FF6584"
TEXT_PRI   = "#F0F0FA"
TEXT_SEC   = "#9090B0"
TEXT_DIM   = "#50506A"
GRID_IDLE  = "#1A1A28"
GRID_HOVER = "#22223A"
GRID_SEL   = "#6C63FF"
CORRECT    = "#4CAF50"
WRONG      = "#E84855"

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cfit_data")
os.makedirs(DATA_DIR, exist_ok=True)

#  DATA LOGGER

class DataLogger:
    FIELDS = [
        "session_id", "timestamp", "trial_num", "level",
        "block_num", "event_type",
        "stim_shapes", "stim_positions",
        "grid_correct", "grid_total",
        "code_shown", "code_entered", "code_correct",
        # PVT fields (replaces arithmetic)
        "pvt_targets_caught", "pvt_lapses", "pvt_penalties",
        "pvt_catch_rts_ms",        # list of per-digit RT in ms
        "pvt_sequence",            # the ordered sequence to catch e.g. [3,7,1]
        "fatigue_self_report",
        "response_time_ms",
    ]

    def __init__(self):
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.session_id = ts
        self.filepath = os.path.join(DATA_DIR, f"cfit_{ts}.csv")
        with open(self.filepath, "w", newline="") as f:
            csv.writer(f).writerow(self.FIELDS)

    def log(self, **kwargs):
        row = {k: "" for k in self.FIELDS}
        row["session_id"] = self.session_id
        row["timestamp"]  = datetime.now().isoformat()
        row.update(kwargs)
        with open(self.filepath, "a", newline="") as f:
            csv.writer(f).writerow([row[k] for k in self.FIELDS])

#  PVT DIGIT STATE

class FallingDigit:
    """One digit falling on the PVT canvas. Can be a target or a decoy."""
    _id_counter = 0

    def __init__(self, canvas, x, digit, speed, spawn_time, is_decoy=False):
        FallingDigit._id_counter += 1
        self.id         = FallingDigit._id_counter
        self.canvas     = canvas
        self.digit      = str(digit)
        self.speed      = speed
        self.y          = -28.0
        self.x          = float(x)
        self.caught     = False
        self.lapsed     = False
        self.is_decoy   = is_decoy
        self.spawn_time = spawn_time

        init_color = PVT_DECOY if is_decoy else PVT_ACTIVE
        self.item = canvas.create_text(
            x, self.y,
            text=self.digit,
            font=("Courier", 30, "bold"),
            fill=init_color,
            tags=("digit", f"digit_{self.id}")
        )
        self.hit = canvas.create_rectangle(
            x - 24, self.y - 24, x + 24, self.y + 24,
            fill="", outline="",
            tags=("hit", f"hit_{self.id}")
        )

    def move(self):
        self.y += self.speed
        self.canvas.coords(self.item, self.x, self.y)
        self.canvas.coords(self.hit,
                           self.x - 24, self.y - 24,
                           self.x + 24, self.y + 24)

    def highlight_as_next(self, active=True):
        """Visually distinguish this as the digit to catch right now."""
        if self.is_decoy or self.caught or self.lapsed:
            return
        self.canvas.itemconfig(self.item,
                               fill=PVT_NEXT if active else PVT_ACTIVE,
                               font=("Courier", 34, "bold") if active else ("Courier", 30, "bold"))

    def mark_caught(self):
        self.caught = True
        self.canvas.itemconfig(self.item, fill=PVT_CAUGHT)

    def mark_lapsed(self):
        self.lapsed = True
        col = PVT_DECOY if self.is_decoy else WRONG
        self.canvas.itemconfig(self.item, fill=col)

    def mark_penalty(self):
        """Flash for wrongly clicked decoy."""
        self.canvas.itemconfig(self.item, fill=PVT_PENALTY)

    def remove(self):
        try:
            self.canvas.delete(self.item)
            self.canvas.delete(self.hit)
        except Exception:
            pass

#  MAIN APPLICATION

class CFITApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Cognitive Fatigue Induction Task  ·  CFIT v1.1")
        self.configure(bg=BG)

        try:
            self.tk.call("tk", "scaling", 1.0)
        except Exception:
            pass

        self.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        win_w = min(1100, sw - 80)
        win_h = min(820,  sh - 80)
        x_off = (sw - win_w) // 2
        y_off = (sh - win_h) // 2
        self.geometry(f"{win_w}x{win_h}+{x_off}+{y_off}")
        self.minsize(900, 700)
        self.resizable(True, True)

        self.logger = DataLogger()

        # Session state
        self.current_level   = 1
        self.trial_num       = 0
        self.block_num       = 1
        self.trials_in_block = 0
        self.trials_in_level = 0

        # Trial state
        self.stim_items     = []
        self.code_string    = ""
        self.selected_cells = {}
        self.grid_buttons   = []
        self.response_start = None

        # PVT runtime state
        self._pvt_digits        = []
        self._pvt_catches        = 0
        self._pvt_lapses         = 0
        self._pvt_penalties      = 0
        self._pvt_catch_rts      = []
        self._pvt_running        = False
        self._pvt_canvas         = None
        self._pvt_spawn_token    = 0
        self._pvt_anim_token     = 0
        self._pvt_status_var     = None
        self._pvt_complete       = False
        self._pvt_sequence       = []
        self._pvt_step           = 0
        self._pvt_current_speed  = PVT_BASE_SPEED
        self._pvt_start_time     = None
        self._pvt_accel_token    = 0

        # Timer cancellation token
        self._timer_token = 0

        self._setup_fonts()
        self._build_skeleton()
        self._show_welcome()

    # FONTS

    def _setup_fonts(self):
        self.f_title   = tkfont.Font(family="Helvetica", size=22, weight="bold")
        self.f_heading = tkfont.Font(family="Helvetica", size=15, weight="bold")
        self.f_body    = tkfont.Font(family="Helvetica", size=12)
        self.f_small   = tkfont.Font(family="Helvetica", size=10)
        self.f_mono    = tkfont.Font(family="Courier",   size=14, weight="bold")
        self.f_shape   = tkfont.Font(family="Helvetica", size=26)
        self.f_code    = tkfont.Font(family="Courier",   size=28, weight="bold")
        self.f_btn     = tkfont.Font(family="Helvetica", size=12, weight="bold")

    # BUTTON HELPER
    def _make_btn(self, parent, text, command, bg=None, fg="#FFFFFF",
                  font=None, padx=24, pady=10, pack_kwargs=None):
        bg   = bg   or ACCENT
        font = font or self.f_btn
        outer = tk.Frame(parent, bg=bg, cursor="hand2")
        lbl   = tk.Label(outer, text=text, font=font,
                         fg=fg, bg=bg, padx=padx, pady=pady)
        lbl.pack()
        hover_bg = ACCENT2

        def on_enter(e):
            outer.config(bg=hover_bg); lbl.config(bg=hover_bg)
        def on_leave(e):
            outer.config(bg=bg);      lbl.config(bg=bg)
        def on_click(e):
            command()

        for w in (outer, lbl):
            w.bind("<Enter>",    on_enter)
            w.bind("<Leave>",    on_leave)
            w.bind("<Button-1>", on_click)

        pk = pack_kwargs or {}
        outer.pack(**pk)
        return outer

    # SKELETON

    def _build_skeleton(self):
        topbar = tk.Frame(self, bg=SURFACE)
        topbar.pack(fill="x", side="top")

        tk.Label(topbar, text="Fatigue Induction Task", font=self.f_heading,
                 fg=ACCENT, bg=SURFACE).pack(side="left", padx=20, pady=12)

        self.lbl_level = tk.Label(topbar, text="", font=self.f_body,
                                  fg=TEXT_SEC, bg=SURFACE)
        self.lbl_level.pack(side="left", padx=8)

        self.lbl_trial = tk.Label(topbar, text="", font=self.f_small,
                                  fg=TEXT_DIM, bg=SURFACE)
        self.lbl_trial.pack(side="right", padx=20)

        self.main = tk.Frame(self, bg=BG)
        self.main.pack(fill="both", expand=True, padx=30, pady=16)

        statusbar = tk.Frame(self, bg=SURFACE)
        statusbar.pack(fill="x", side="bottom")

        self.lbl_status = tk.Label(statusbar, text="", font=self.f_small,
                                   fg=TEXT_DIM, bg=SURFACE)
        self.lbl_status.pack(side="left", padx=16, pady=6)

        tk.Label(statusbar, text=f"Logging → {self.logger.filepath}",
                 font=self.f_small, fg=TEXT_DIM, bg=SURFACE).pack(side="right", padx=16)

    def _clear_main(self):
        self._timer_token += 1
        self._stop_pvt()
        for w in self.main.winfo_children():
            w.destroy()

    def _set_status(self, text):
        self.lbl_status.config(text=text)

    def _update_header(self):
        cfg = LEVEL_CONFIG[self.current_level]
        self.lbl_level.config(text=cfg["label"])
        self.lbl_trial.config(text=f"Trial {self.trial_num}  ·  Block {self.block_num}")

    # SCREENS
    def _show_welcome(self):
        self._clear_main()
        self.lbl_level.config(text="")
        self.lbl_trial.config(text="")

        c = tk.Frame(self.main, bg=BG)
        c.place(relx=0.5, rely=0.5, anchor="center")

        tk.Label(c, text="Cognitive Fatigue", font=self.f_title,
                 fg=TEXT_PRI, bg=BG).pack(pady=(0, 2))
        tk.Label(c, text="Induction Task", font=self.f_title,
                 fg=ACCENT, bg=BG).pack()
        tk.Label(c,
                 text="Working Memory  ·  Progressive Difficulty  ·  Self-Report Fatigue",
                 font=self.f_small, fg=TEXT_DIM, bg=BG).pack(pady=(6, 32))

        info = ("You will be shown shapes on a grid.\n"
                "Memorise their positions and types.\n"
                "Then recall them on a blank grid.\n\n"
                "At Level 3: falling digits will appear during recall —\n"
                "click 3 of them as fast as possible.\n\n"
                "Periodically you will rate your fatigue.\n"
                "There are no breaks between trials.")
        tk.Label(c, text=info, font=self.f_body, fg=TEXT_SEC, bg=BG,
                 justify="center", wraplength=480).pack(pady=(0, 32))

        tk.Label(c, text="Select starting level:", font=self.f_body,
                 fg=TEXT_SEC, bg=BG).pack(pady=(0, 12))

        btn_row = tk.Frame(c, bg=BG)
        btn_row.pack()
        for lvl, lbl in [(1, "Level 1\nBasic"),
                         (2, "Level 2\n+ Code"),
                         (3, "Level 3\n+ PVT")]:
            self._make_btn(btn_row, lbl,
                           command=lambda l=lvl: self._start_session(l),
                           bg=SURFACE2, fg=TEXT_PRI, padx=28, pady=14,
                           pack_kwargs={"side": "left", "padx": 8})

    def _start_session(self, level):
        self.current_level   = level
        self.trial_num       = 0
        self.block_num       = 1
        self.trials_in_block = 0
        self.trials_in_level = 0
        self._show_instructions()

    def _show_instructions(self):
        self._clear_main()
        cfg = LEVEL_CONFIG[self.current_level]
        self._update_header()

        c = tk.Frame(self.main, bg=BG)
        c.place(relx=0.5, rely=0.5, anchor="center")

        tk.Label(c, text=cfg["label"], font=self.f_heading,
                 fg=ACCENT, bg=BG).pack(pady=(0, 20))

        steps = [
            f"1.  A {GRID_SIZE}x{GRID_SIZE} grid appears with {cfg['shapes_shown']} coloured shapes.",
            f"2.  Study it for {cfg['display_ms']/1000:.1f}s — then it clears.",
            "3.  Click the correct cells and pick the matching shape for each.",
        ]
        if cfg["code_len"] > 0:
            steps.append(f"4.  Also memorise a {cfg['code_len']}-character code and type it during recall.")
        if cfg.get("pvt"):
            steps.append(
                f"5.  During recall, digits fall on the right panel.\n"
                f"    Click {PVT_TARGETS_REQUIRED} of them as quickly as possible.\n"
                f"    Digits that reach the bottom count as lapses."
            )
        steps.append(f"     Every {TRIALS_PER_BLOCK} trials: rate your fatigue (3-point scale).")

        for s in steps:
            tk.Label(c, text=s, font=self.f_body, fg=TEXT_SEC, bg=BG,
                     anchor="w", justify="left").pack(pady=3, fill="x")

        self._make_btn(c, "Begin", self._next_trial,
                       padx=40, pady=12,
                       pack_kwargs={"pady": (30, 0)})

    # FIXATION

    def _show_fixation(self, callback, ms=600):
        self._clear_main()
        tk.Label(self.main, text="+",
                 font=tkfont.Font(family="Helvetica", size=48),
                 fg=TEXT_DIM, bg=BG).place(relx=0.5, rely=0.5, anchor="center")
        self.after(ms, callback)

    # TRIAL FLOW

    def _next_trial(self):
        self.trial_num       += 1
        self.trials_in_block += 1
        self.trials_in_level += 1
        self._update_header()
        self._generate_stimulus()
        self._show_fixation(self._show_stimulus)

    def _generate_stimulus(self):
        cfg = LEVEL_CONFIG[self.current_level]
        n = cfg["shapes_shown"]
        cells  = random.sample(range(GRID_SIZE * GRID_SIZE), n)
        shapes = random.choices(SHAPES, k=n)
        self.stim_items = list(zip(shapes, cells))

        if cfg["code_len"] > 0:
            pool = string.ascii_uppercase + string.digits
            self.code_string = "".join(random.choices(pool, k=cfg["code_len"]))
        else:
            self.code_string = ""

        # Reset PVT state
        self._pvt_digits         = []
        self._pvt_catches        = 0
        self._pvt_lapses         = 0
        self._pvt_penalties      = 0
        self._pvt_catch_rts      = []
        self._pvt_running        = False
        self._pvt_complete       = False
        self._pvt_sequence       = []
        self._pvt_step           = 0
        self._pvt_current_speed  = PVT_BASE_SPEED
        self._pvt_start_time     = None
        self.selected_cells      = {}

    # STIMULUS DISPLAY

    def _show_stimulus(self):
        self._clear_main()
        cfg = LEVEL_CONFIG[self.current_level]
        self._set_status("Memorise the grid.")

        wrapper = tk.Frame(self.main, bg=BG)
        wrapper.pack(expand=True)

        tk.Label(wrapper, text="Memorise", font=self.f_heading,
                 fg=TEXT_DIM, bg=BG).pack(pady=(20, 12))

        grid_f = tk.Frame(wrapper, bg=SURFACE)
        grid_f.pack()
        self._draw_grid_stimulus(grid_f)

        if self.code_string:
            tk.Label(wrapper, text="Code to memorise:",
                     font=self.f_body, fg=TEXT_DIM, bg=BG).pack(pady=(20, 4))
            spaced = "   ".join(self.code_string)
            tk.Label(wrapper, text=spaced, font=self.f_code,
                     fg=ACCENT2, bg=BG).pack()

        if cfg.get("pvt"):
            pvt_hint = tk.Frame(wrapper, bg=SURFACE2, padx=20, pady=14)
            pvt_hint.pack(pady=(20, 0))
            tk.Label(pvt_hint,
                     text=f"⚡  During recall: catch {PVT_TARGETS_REQUIRED} digits IN ORDER",
                     font=self.f_body, fg=PVT_NEXT, bg=SURFACE2).pack()
            tk.Label(pvt_hint,
                     text="Green = catch it now  ·  Red = decoy, clicking costs you a step  ·  Digits accelerate over time",
                     font=self.f_small, fg=TEXT_DIM, bg=SURFACE2).pack(pady=(4, 0))

        # Progress bar countdown
        bar_bg = tk.Frame(wrapper, bg=SURFACE2, height=5, width=420)
        bar_bg.pack(pady=(20, 6))
        bar_bg.pack_propagate(False)
        bar_fill = tk.Frame(bar_bg, bg=ACCENT, height=5)
        bar_fill.place(x=0, y=0, relwidth=1.0, height=5)

        disp  = cfg["display_ms"]
        token = self._timer_token
        self._run_countdown(bar_fill, disp, disp, token)
        self.after(disp, lambda: self._safe_proceed(token, self._show_blank_then_recall))

    def _run_countdown(self, bar_fill, remaining, total, token):
        if self._timer_token != token:
            return
        if remaining <= 0:
            return
        try:
            bar_fill.place_configure(relwidth=max(0, remaining / total))
        except tk.TclError:
            return
        self.after(50, lambda: self._run_countdown(bar_fill, remaining - 50, total, token))

    def _safe_proceed(self, token, callback):
        if self._timer_token == token:
            callback()

    def _draw_grid_stimulus(self, parent):
        stim_map = {cell: shape for shape, cell in self.stim_items}
        CELL = 88
        for row in range(GRID_SIZE):
            for col in range(GRID_SIZE):
                idx = row * GRID_SIZE + col
                has = idx in stim_map
                bg_col = SURFACE2 if has else GRID_IDLE
                cell_f = tk.Frame(parent, bg=bg_col, width=CELL, height=CELL,
                                  highlightthickness=1,
                                  highlightbackground=SURFACE)
                cell_f.grid(row=row, column=col, padx=2, pady=2)
                cell_f.pack_propagate(False)
                if has:
                    sh = stim_map[idx]
                    tk.Label(cell_f, text=sh, font=self.f_shape,
                             fg=COLORS[sh], bg=bg_col).place(relx=0.5, rely=0.5, anchor="center")

    # BLANK GAP

    def _show_blank_then_recall(self):
        self._clear_main()
        self._set_status("")
        self.after(BLANK_TIME_MS, self._show_recall)

    # RECALL PHASE
    def _show_recall(self):
        self._clear_main()
        cfg = LEVEL_CONFIG[self.current_level]
        self._set_status("Recall: click cells, assign shapes."
                         + ("  Click falling digits!" if cfg.get("pvt") else ""))
        self.response_start = time.time()

        left = tk.Frame(self.main, bg=BG)
        left.pack(side="left", fill="y", padx=(10, 20), pady=20)

        right = tk.Frame(self.main, bg=BG)
        right.pack(side="left", fill="both", expand=True, pady=20)

        # Left: grid recall
        tk.Label(left, text="Click the correct cells",
                 font=self.f_body, fg=TEXT_SEC, bg=BG).pack(pady=(0, 10))

        grid_f = tk.Frame(left, bg=SURFACE)
        grid_f.pack()
        self._draw_grid_recall(grid_f)

        tk.Label(left, text="Active shape:", font=self.f_small,
                 fg=TEXT_DIM, bg=BG).pack(pady=(16, 4))
        self._active_shape = tk.StringVar(value=SHAPES[0])
        picker_row = tk.Frame(left, bg=BG)
        picker_row.pack()
        for sh in SHAPES:
            rb = tk.Radiobutton(picker_row, text=sh, variable=self._active_shape,
                                value=sh, font=self.f_shape,
                                fg=COLORS[sh], bg=BG,
                                selectcolor=SURFACE2,
                                activebackground=BG,
                                cursor="hand2",
                                indicatoron=False,
                                width=3, height=1,
                                relief="flat", bd=2)
            rb.pack(side="left", padx=2)

        self.lbl_selected = tk.Label(left, text="Selected: 0 cells",
                                     font=self.f_small, fg=TEXT_DIM, bg=BG)
        self.lbl_selected.pack(pady=(10, 0))

        if cfg["code_len"] > 0:
            tk.Label(right, text="Type the code:", font=self.f_heading,
                     fg=TEXT_SEC, bg=BG).pack(anchor="w", pady=(0, 6))
            self._code_var = tk.StringVar()
            code_entry = tk.Entry(right, textvariable=self._code_var,
                                  font=self.f_code, fg=ACCENT2,
                                  bg=SURFACE2, insertbackground=ACCENT2,
                                  relief="flat", bd=0,
                                  width=cfg["code_len"] + 2,
                                  justify="center")
            code_entry.pack(anchor="w", ipady=12, ipadx=12)
            code_entry.focus()
        else:
            self._code_var = None

        if cfg.get("pvt"):
            self._build_pvt_panel(right)
        else:
            tk.Label(right,
                     text="Select a shape from the picker,\nthen click grid cells to place it.\nClick a placed cell again to deselect.",
                     font=self.f_small, fg=TEXT_DIM, bg=BG, justify="left").pack(anchor="w", pady=(28, 0))

        btn_row = tk.Frame(right, bg=BG)
        btn_row.pack(anchor="w", pady=(14, 4))
        self._make_btn(btn_row, "Submit Response", self._submit_response,
                       padx=24, pady=10,
                       pack_kwargs={"side": "left"})

        self._lbl_error = tk.Label(btn_row, text="", font=self.f_body,
                                   fg=WRONG, bg=BG, justify="left", wraplength=320)
        self._lbl_error.pack(side="left", padx=(16, 0))

        if cfg.get("pvt"):
            self.after(300, self._start_pvt)

    # PVT PANEL

    def _build_pvt_panel(self, parent):
        pvt_outer = tk.Frame(parent, bg=SURFACE2, bd=0)
        pvt_outer.pack(anchor="w", pady=(6, 0), fill="x")

        header = tk.Frame(pvt_outer, bg=SURFACE2)
        header.pack(fill="x", padx=10, pady=(8, 2))
        tk.Label(header, text="⚡ PVT — Catch the sequence in order",
                 font=self.f_mono, fg=PVT_NEXT, bg=SURFACE2).pack(side="left")
        self._pvt_status_var = tk.StringVar(value="Waiting…")
        tk.Label(header, textvariable=self._pvt_status_var,
                 font=self.f_small, fg=TEXT_DIM, bg=SURFACE2).pack(side="right")

        seq_row = tk.Frame(pvt_outer, bg=SURFACE2)
        seq_row.pack(fill="x", padx=10, pady=(2, 4))
        tk.Label(seq_row, text="Sequence: ", font=self.f_small,
                 fg=TEXT_DIM, bg=SURFACE2).pack(side="left")
        self._pvt_seq_labels = []
        for _ in range(PVT_TARGETS_REQUIRED):
            lbl = tk.Label(seq_row, text="?", font=self.f_mono,
                           fg=TEXT_DIM, bg=SURFACE2, width=3)
            lbl.pack(side="left", padx=3)
            self._pvt_seq_labels.append(lbl)

        stats = tk.Frame(pvt_outer, bg=SURFACE2)
        stats.pack(fill="x", padx=10, pady=(0, 4))
        self._pvt_catch_lbl = tk.Label(stats, text="Progress: 0/3",
                                        font=self.f_small, fg=CORRECT, bg=SURFACE2)
        self._pvt_catch_lbl.pack(side="left", padx=(0, 12))
        self._pvt_lapse_lbl = tk.Label(stats, text="Lapses: 0",
                                        font=self.f_small, fg=WRONG, bg=SURFACE2)
        self._pvt_lapse_lbl.pack(side="left", padx=(0, 12))
        self._pvt_penalty_lbl = tk.Label(stats, text="Penalties: 0",
                                          font=self.f_small, fg=PVT_PENALTY, bg=SURFACE2)
        self._pvt_penalty_lbl.pack(side="left")
        self._pvt_rt_lbl = tk.Label(stats, text="Last RT: —",
                                     font=self.f_small, fg=TEXT_DIM, bg=SURFACE2)
        self._pvt_rt_lbl.pack(side="right")
        self._pvt_speed_lbl = tk.Label(stats, text="Speed: 1×",
                                        font=self.f_small, fg=TEXT_DIM, bg=SURFACE2)
        self._pvt_speed_lbl.pack(side="right", padx=(0, 12))

        self._pvt_canvas = tk.Canvas(
            pvt_outer,
            width=PVT_PANEL_W, height=PVT_PANEL_H,
            bg=BG, bd=0, highlightthickness=1,
            highlightbackground=SURFACE
        )
        self._pvt_canvas.pack(padx=10, pady=(0, 10))

        for x_frac in [0.25, 0.5, 0.75]:
            x = int(PVT_PANEL_W * x_frac)
            self._pvt_canvas.create_line(x, 0, x, PVT_PANEL_H,
                                         fill=SURFACE2, dash=(3, 10))

        self._pvt_canvas.bind("<Button-1>", self._pvt_canvas_click)

    def _start_pvt(self):
        if not self._pvt_canvas:
            return

        self._pvt_sequence = random.sample(range(1, 10), PVT_TARGETS_REQUIRED)
        self._pvt_step     = 0

        for i, lbl in enumerate(self._pvt_seq_labels):
            lbl.config(text=str(self._pvt_sequence[i]),
                       fg=PVT_NEXT if i == 0 else TEXT_DIM)

        self._pvt_running      = True
        self._pvt_complete     = False
        self._pvt_current_speed = PVT_BASE_SPEED
        self._pvt_start_time   = time.time()

        self._pvt_spawn_token += 1
        self._pvt_anim_token  += 1
        self._pvt_accel_token += 1

        self._pvt_status_var.set(f"Catch  {self._pvt_sequence[0]}  first →")
        self._pvt_schedule_spawn(self._pvt_spawn_token)
        self._pvt_animate(self._pvt_anim_token)
        self._pvt_accelerate(self._pvt_accel_token)

    def _stop_pvt(self):
        self._pvt_running      = False
        self._pvt_spawn_token  += 1
        self._pvt_anim_token   += 1
        self._pvt_accel_token  += 1
        for d in self._pvt_digits:
            try:
                d.remove()
            except Exception:
                pass
        self._pvt_digits  = []
        self._pvt_canvas  = None

    def _pvt_accelerate(self, token):
        if not self._pvt_running or self._pvt_accel_token != token:
            return
        self._pvt_current_speed = min(
            self._pvt_current_speed * PVT_ACCEL_FACTOR,
            PVT_MAX_SPEED
        )
        mult = self._pvt_current_speed / PVT_BASE_SPEED
        try:
            self._pvt_speed_lbl.config(text=f"Speed: {mult:.1f}×")
        except Exception:
            pass
        self.after(int(PVT_ACCEL_INTERVAL_S * 1000),
                   lambda: self._pvt_accelerate(token))

    def _pvt_schedule_spawn(self, token):
        if not self._pvt_running or self._pvt_spawn_token != token:
            return
        delay = random.randint(PVT_SPAWN_INTERVAL_MS_MIN, PVT_SPAWN_INTERVAL_MS_MAX)
        self.after(delay, lambda: self._pvt_spawn_digit(token))

    def _pvt_spawn_digit(self, token):
        if not self._pvt_running or self._pvt_spawn_token != token:
            return
        if not self._pvt_canvas:
            return

        lanes = [int(PVT_PANEL_W * f) for f in [0.15, 0.35, 0.57, 0.79]]
        occupied = {d.x for d in self._pvt_digits
                    if not d.caught and not d.lapsed and d.y < PVT_PANEL_H * 0.25}
        choices = [x for x in lanes if x not in occupied] or lanes
        x = random.choice(choices)

        is_decoy = random.random() < PVT_DECOY_PROBABILITY

        if is_decoy:
            avoid = self._pvt_sequence[self._pvt_step] if self._pvt_step < len(self._pvt_sequence) else -1
            pool  = [d for d in range(1, 10) if d != avoid]
            digit = random.choice(pool)
        else:
            digit = self._pvt_sequence[self._pvt_step] if self._pvt_step < len(self._pvt_sequence) else random.randint(1, 9)

        variance = random.uniform(-PVT_SPEED_VARIANCE, PVT_SPEED_VARIANCE)
        speed    = max(1.0, self._pvt_current_speed + variance)

        d = FallingDigit(self._pvt_canvas, x, digit, speed, time.time(), is_decoy=is_decoy)

        if not is_decoy and str(digit) == str(self._pvt_sequence[self._pvt_step]):
            d.highlight_as_next(True)

        self._pvt_digits.append(d)
        self._pvt_schedule_spawn(token)

    def _pvt_animate(self, token):
        if not self._pvt_anim_token == token:
            return
        if not self._pvt_canvas:
            return

        to_remove = []
        for d in self._pvt_digits:
            if d.caught or d.lapsed:
                continue
            d.move()
            if d.y >= PVT_PANEL_H + 28:
                d.mark_lapsed()
                if not d.is_decoy:
                    self._pvt_lapses += 1
                    self._pvt_update_stats()
                to_remove.append(d)

        for d in to_remove:
            self.after(180, d.remove)
            if d in self._pvt_digits:
                self._pvt_digits.remove(d)

        self.after(PVT_TICK_MS, lambda: self._pvt_animate(token))

    def _pvt_canvas_click(self, event):
        if self._pvt_complete:
            return

        cx, cy     = event.x, event.y
        click_time = time.time()

        best, best_dist = None, float("inf")
        for d in self._pvt_digits:
            if d.caught or d.lapsed:
                continue
            dist = math.hypot(cx - d.x, cy - d.y)
            if dist < 32 and dist < best_dist:
                best, best_dist = d, dist

        if best is None:
            return

        if best.is_decoy:
            best.mark_penalty()
            self.after(300, best.remove)
            if best in self._pvt_digits:
                self._pvt_digits.remove(best)
            self._pvt_penalties += 1
            if self._pvt_step > 0:
                self._pvt_step -= 1
            self._pvt_update_stats()
            self._pvt_refresh_highlights()
            return

        needed = str(self._pvt_sequence[self._pvt_step])
        if best.digit != needed:
            self._pvt_canvas.itemconfig(best.item, fill=WRONG)
            self.after(300, lambda: self._pvt_canvas.itemconfig(
                best.item, fill=PVT_ACTIVE) if not best.caught else None)
            return

        rt_ms = int((click_time - best.spawn_time) * 1000)
        best.mark_caught()
        self._pvt_catches   += 1
        self._pvt_step      += 1
        self._pvt_catch_rts.append(rt_ms)
        self.after(240, best.remove)
        if best in self._pvt_digits:
            self._pvt_digits.remove(best)

        self._pvt_update_stats(last_rt=rt_ms)
        self._pvt_refresh_highlights()

        if self._pvt_catches >= PVT_TARGETS_REQUIRED:
            self._pvt_complete = True
            self._pvt_running  = False
            self._pvt_spawn_token += 1
            try:
                self._pvt_status_var.set("✓ Done — submit when ready")
                for lbl in self._pvt_seq_labels:
                    lbl.config(fg=CORRECT)
            except Exception:
                pass

    def _pvt_refresh_highlights(self):
        if self._pvt_step >= len(self._pvt_sequence):
            return
        needed = str(self._pvt_sequence[self._pvt_step])
        try:
            self._pvt_status_var.set(f"Catch  {needed}  next →")
        except Exception:
            pass
        for i, lbl in enumerate(self._pvt_seq_labels):
            if i < self._pvt_step:
                lbl.config(fg=CORRECT)
            elif i == self._pvt_step:
                lbl.config(fg=PVT_NEXT)
            else:
                lbl.config(fg=TEXT_DIM)
        for d in self._pvt_digits:
            if d.caught or d.lapsed or d.is_decoy:
                continue
            d.highlight_as_next(d.digit == needed)

    def _pvt_update_stats(self, last_rt=None):
        try:
            self._pvt_catch_lbl.config(
                text=f"Progress: {self._pvt_catches}/{PVT_TARGETS_REQUIRED}")
            self._pvt_lapse_lbl.config(text=f"Lapses: {self._pvt_lapses}")
            self._pvt_penalty_lbl.config(text=f"Penalties: {self._pvt_penalties}")
            if last_rt is not None:
                self._pvt_rt_lbl.config(text=f"Last RT: {last_rt} ms")
        except Exception:
            pass

    # GRID RECALL HELPERS

    def _draw_grid_recall(self, parent):
        CELL = 88
        self.grid_buttons   = []
        self.selected_cells = {}

        for row in range(GRID_SIZE):
            row_btns = []
            for col in range(GRID_SIZE):
                idx = row * GRID_SIZE + col
                cell_f = tk.Frame(parent, bg=GRID_IDLE, width=CELL, height=CELL,
                                  cursor="hand2",
                                  highlightthickness=1,
                                  highlightbackground=SURFACE)
                cell_f.grid(row=row, column=col, padx=2, pady=2)
                cell_f.pack_propagate(False)

                lbl = tk.Label(cell_f, text="", font=self.f_shape,
                               bg=GRID_IDLE, fg=TEXT_PRI)
                lbl.place(relx=0.5, rely=0.5, anchor="center")

                for widget in (cell_f, lbl):
                    widget.bind("<Button-1>",
                                lambda e, i=idx, f=cell_f, l=lbl: self._toggle_cell(i, f, l))
                    widget.bind("<Enter>",
                                lambda e, f=cell_f, i=idx: self._cell_hover(f, i, True))
                    widget.bind("<Leave>",
                                lambda e, f=cell_f, i=idx: self._cell_hover(f, i, False))

                row_btns.append((cell_f, lbl))
            self.grid_buttons.append(row_btns)

    def _cell_hover(self, frame, idx, entering):
        if idx in self.selected_cells:
            return
        col = GRID_HOVER if entering else GRID_IDLE
        frame.config(bg=col)
        for child in frame.winfo_children():
            child.config(bg=col)

    def _toggle_cell(self, idx, frame, lbl):
        sh = self._active_shape.get()
        if idx in self.selected_cells and self.selected_cells[idx] == sh:
            del self.selected_cells[idx]
            frame.config(bg=GRID_IDLE)
            lbl.config(text="", bg=GRID_IDLE)
        else:
            self.selected_cells[idx] = sh
            frame.config(bg=GRID_SEL)
            lbl.config(text=sh, fg=COLORS[sh], bg=GRID_SEL)
        self.lbl_selected.config(text=f"Selected: {len(self.selected_cells)} cells")

    # ------------------------------------------------------------------ #
    #  SUBMIT  (FIXED — always advances; wrong answers are logged & shown) #
    # ------------------------------------------------------------------ #

    def _submit_response(self):
        correct_set  = {(sh, cell) for sh, cell in self.stim_items}
        user_set     = {(sh, cell) for cell, sh in self.selected_cells.items()}
        grid_correct = len(correct_set & user_set)
        grid_total   = len(correct_set)

        code_entered = self._code_var.get().strip().upper() if self._code_var else ""
        code_correct = (code_entered == self.code_string) if self.code_string else True

        # Stop PVT cleanly regardless of completion state
        cfg = LEVEL_CONFIG[self.current_level]
        if cfg.get("pvt"):
            self._pvt_running     = False
            self._pvt_spawn_token += 1

        rt_ms = int((time.time() - self.response_start) * 1000)
        self.logger.log(
            trial_num=self.trial_num,
            level=self.current_level,
            block_num=self.block_num,
            event_type="trial_response",
            stim_shapes=str([(sh, c) for sh, c in self.stim_items]),
            stim_positions=str([c for _, c in self.stim_items]),
            grid_correct=grid_correct,
            grid_total=grid_total,
            code_shown=self.code_string,
            code_entered=code_entered,
            code_correct=int(code_correct),
            pvt_targets_caught=self._pvt_catches,
            pvt_lapses=self._pvt_lapses,
            pvt_catch_rts_ms=str(self._pvt_catch_rts),
            pvt_penalties=self._pvt_penalties,
            pvt_sequence=str(self._pvt_sequence),
            response_time_ms=rt_ms,
        )

        # Always advance — accuracy is a data point, not a gate
        self._show_feedback(grid_correct, grid_total, code_correct)

    # ------------------------------------------------------------------ #
    #  FEEDBACK  (FIXED — handles both correct and incorrect outcomes)    #
    # ------------------------------------------------------------------ #

    def _show_feedback(self, gc, gt, cc):
        self._clear_main()
        cfg = LEVEL_CONFIG[self.current_level]

        # Determine overall pass/fail for this trial
        pvt_passed = (self._pvt_catches >= PVT_TARGETS_REQUIRED) if cfg.get("pvt") else True
        trial_ok   = (gc == gt) and cc and pvt_passed

        wrapper = tk.Frame(self.main, bg=BG)
        wrapper.pack(expand=True)

        # Header: correct vs incorrect
        if trial_ok:
            tk.Label(wrapper, text="Correct!", font=self.f_title,
                     fg=CORRECT, bg=BG).pack(pady=(0, 6))
        else:
            tk.Label(wrapper, text="Incorrect", font=self.f_title,
                     fg=WRONG, bg=BG).pack(pady=(0, 6))

        # Grid accuracy — colour-coded
        grid_col = CORRECT if gc == gt else WRONG
        tk.Label(wrapper, text=f"Grid: {gc} / {gt}",
                 font=self.f_body, fg=grid_col, bg=BG).pack(pady=2)

        # Code accuracy
        if cfg["code_len"] > 0:
            if cc:
                tk.Label(wrapper, text="Code: ✓ Correct",
                         font=self.f_body, fg=CORRECT, bg=BG).pack(pady=2)
            else:
                tk.Label(wrapper,
                         text=f"Code: ✗ you entered '{self._code_var.get().strip().upper() if self._code_var else ''}', correct was '{self.code_string}'",
                         font=self.f_body, fg=WRONG, bg=BG).pack(pady=2)

        # PVT summary
        if cfg.get("pvt"):
            pvt_col = CORRECT if pvt_passed else WRONG
            if self._pvt_catch_rts:
                mean_rt = int(sum(self._pvt_catch_rts) / len(self._pvt_catch_rts))
                rt_info = f"Mean RT: {mean_rt} ms"
                rt_col  = CORRECT if mean_rt < 500 else ACCENT2
            else:
                rt_info = "No catches"
                rt_col  = WRONG

            seq_str = " → ".join(str(d) for d in self._pvt_sequence)
            pvt_summary = (
                f"PVT sequence: {seq_str}   "
                f"Caught: {self._pvt_catches}/{PVT_TARGETS_REQUIRED}   "
                f"Lapses: {self._pvt_lapses}   "
                f"Penalties: {self._pvt_penalties}   "
                f"{rt_info}"
            )
            tk.Label(wrapper, text=pvt_summary, font=self.f_body,
                     fg=pvt_col, bg=BG).pack(pady=2)
            if self._pvt_catch_rts:
                rt_str = "  ".join([f"{r} ms" for r in self._pvt_catch_rts])
                tk.Label(wrapper, text=f"RTs: {rt_str}",
                         font=self.f_small, fg=rt_col, bg=BG).pack(pady=(2, 0))

        # Always show the correct answer so participant can learn
        answer = "  ".join([f"{sh} → cell {cell}" for sh, cell in self.stim_items])
        tk.Label(wrapper, text=f"Correct answer: {answer}",
                 font=self.f_small, fg=TEXT_DIM, bg=BG, wraplength=600).pack(pady=(14, 0))

        # Level progress bar
        TRIALS_PER_LEVEL = TRIALS_PER_BLOCK * 3
        done = self.trials_in_level
        left_count = TRIALS_PER_LEVEL - done

        if self.current_level < 3:
            prog_frame = tk.Frame(wrapper, bg=SURFACE2, padx=20, pady=12)
            prog_frame.pack(pady=(22, 0), fill="x", padx=60)

            header = tk.Frame(prog_frame, bg=SURFACE2)
            header.pack(fill="x")
            tk.Label(header, text="Level progress",
                     font=self.f_small, fg=TEXT_DIM, bg=SURFACE2).pack(side="left")
            tk.Label(header, text=f"{done} / {TRIALS_PER_LEVEL} trials",
                     font=self.f_small, fg=TEXT_SEC, bg=SURFACE2).pack(side="right")

            bar_track = tk.Frame(prog_frame, bg=GRID_IDLE, height=8)
            bar_track.pack(fill="x", pady=(6, 8))
            bar_track.pack_propagate(False)
            frac = min(done / TRIALS_PER_LEVEL, 1.0)
            bar_fill = tk.Frame(bar_track, bg=ACCENT, height=8)
            bar_fill.place(x=0, y=0, relwidth=frac, height=8)

            if left_count <= 0:
                msg, msg_col = "Level up next!", ACCENT2
            elif left_count == 1:
                msg, msg_col = "1 trial until next level", ACCENT2
            else:
                msg, msg_col = f"{left_count} trials until next level", TEXT_SEC
            tk.Label(prog_frame, text=msg, font=self.f_small,
                     fg=msg_col, bg=SURFACE2).pack(anchor="w")
        else:
            tk.Label(wrapper, text=f"Max level  ·  Trial {self.trial_num} overall",
                     font=self.f_small, fg=TEXT_DIM, bg=BG).pack(pady=(18, 0))

        if self.trials_in_block >= TRIALS_PER_BLOCK:
            next_cmd = self._show_fatigue_report
        else:
            next_cmd = self._next_trial

        # Auto-advance countdown — no button shown
        countdown_var = tk.StringVar(value="Continuing in 3…")
        tk.Label(wrapper, textvariable=countdown_var,
                 font=self.f_small, fg=TEXT_DIM, bg=BG).pack(pady=(24, 0))

        token = self._timer_token

        def _tick(n):
            if self._timer_token != token:
                return
            if n > 1:
                countdown_var.set(f"Continuing in {n - 1}…")
                self.after(1000, lambda: _tick(n - 1))
            else:
                next_cmd()

        self.after(1000, lambda: _tick(3))

    # FATIGUE SELF-REPORT

    def _show_fatigue_report(self):
        self._clear_main()
        self._set_status(f"Fatigue check — Block {self.block_num} complete.")

        wrapper = tk.Frame(self.main, bg=BG)
        wrapper.pack(expand=True)

        tk.Label(wrapper, text="How do you feel right now?",
                 font=self.f_heading, fg=TEXT_PRI, bg=BG).pack(pady=(0, 6))
        tk.Label(wrapper, text="Rate your current fatigue level.",
                 font=self.f_small, fg=TEXT_DIM, bg=BG).pack(pady=(0, 28))

        options = [
            ("1", "Normal",            CORRECT, "Alert and focused"),
            ("2", "Mildly Fatigued",   ACCENT,  "Somewhat tired, effort required"),
            ("3", "Severely Fatigued", WRONG,   "Very tired, struggling to concentrate"),
        ]
        for val, label, col, sub in options:
            btn_f = tk.Frame(wrapper, bg=SURFACE2, cursor="hand2")
            btn_f.pack(fill="x", pady=6, ipadx=12, ipady=10)

            inner = tk.Frame(btn_f, bg=SURFACE2)
            inner.pack(padx=20, pady=4, anchor="w")
            tk.Label(inner, text=f"{val}   {label}", font=self.f_heading,
                     fg=col, bg=SURFACE2).pack(anchor="w")
            tk.Label(inner, text=sub, font=self.f_small,
                     fg=TEXT_DIM, bg=SURFACE2).pack(anchor="w")

            cb = lambda e, v=val, lv=label: self._submit_fatigue(v, lv)
            for widget in (btn_f, inner) + tuple(inner.winfo_children()):
                widget.bind("<Button-1>", cb)
            btn_f.bind("<Enter>", lambda e, f=btn_f: f.config(bg=SURFACE))
            btn_f.bind("<Leave>", lambda e, f=btn_f: f.config(bg=SURFACE2))

    def _submit_fatigue(self, val, label):
        self.logger.log(
            trial_num=self.trial_num,
            level=self.current_level,
            block_num=self.block_num,
            event_type="fatigue_report",
            fatigue_self_report=f"{val}:{label}",
        )
        self.block_num       += 1
        self.trials_in_block  = 0
        self._set_status("")
        self._show_block_transition()

    # BLOCK TRANSITION

    def _show_block_transition(self):
        self._clear_main()

        wrapper = tk.Frame(self.main, bg=BG)
        wrapper.pack(expand=True)

        tk.Label(wrapper, text=f"Block {self.block_num} starting",
                 font=self.f_heading, fg=ACCENT, bg=BG).pack(pady=(0, 8))

        can_escalate = (self.current_level < 3) and (self.block_num % 3 == 0)
        if can_escalate:
            tk.Label(wrapper, text="Difficulty increasing.",
                     font=self.f_body, fg=ACCENT2, bg=BG).pack(pady=4)

        tk.Label(wrapper, text="Get ready. No breaks between trials.",
                 font=self.f_body, fg=TEXT_DIM, bg=BG).pack(pady=(12, 24))

        self._make_btn(wrapper, "Continue",
                       command=lambda: self._begin_next_block(can_escalate),
                       padx=28, pady=10,
                       pack_kwargs={})

    def _begin_next_block(self, escalate):
        if escalate:
            self.current_level   = min(3, self.current_level + 1)
            self.trials_in_level = 0
            self._update_header()
        self._next_trial()


# ENTRY POINT

if __name__ == "__main__":
    app = CFITApp()
    app.mainloop()