"""

A working memory task designed to progressively induce fatigue
for eye-tracking ground truth data collection.

Levels:
  1 — Grid recall (shapes + positions)
  2 — Grid recall + alphanumeric code entry
  3 — Grid recall + code + letter sequence

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
from datetime import datetime

# ─────────────────────────────────────────────
#  CONSTANTS & CONFIG
# ─────────────────────────────────────────────

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
    1: {"shapes_shown": 3, "display_ms": 2500, "code_len": 0, "seq_len": 0,
        "label": "Level 1 — Grid Recall"},
    2: {"shapes_shown": 3, "display_ms": 6000, "code_len": 3, "seq_len": 0,
        "label": "Level 2 — Grid + Code"},
    3: {"shapes_shown": 4, "display_ms": 10000, "code_len": 3, "seq_len": 4,
        "label": "Level 3 — Grid + Code + Sequence"},
}

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


# ─────────────────────────────────────────────
#  DATA LOGGER
# ─────────────────────────────────────────────

class DataLogger:
    FIELDS = [
        "session_id", "timestamp", "trial_num", "level",
        "block_num", "event_type",
        "stim_shapes", "stim_positions",
        "grid_correct", "grid_total",
        "code_shown", "code_entered", "code_correct",
        "seq_shown", "seq_entered", "seq_correct",
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

#  MAIN APPLICATION

class CFITApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Cognitive Fatigue Induction Task  ·  CFIT v1.0")
        self.configure(bg=BG)
        self.geometry("980x780")
        self.resizable(False, False)
        self.logger = DataLogger()

        # Session state
        self.current_level   = 1
        self.trial_num       = 0
        self.block_num       = 1
        self.trials_in_block = 0
        self.trials_in_level = 0   # resets when level changes

        # Trial state
        self.stim_items    = []   # [(shape, cell_idx), ...]
        self.code_string   = ""
        self.seq_string    = ""
        self.selected_cells = {}  # cell_idx -> shape
        self.grid_buttons  = []
        self.response_start = None

        # Countdown token: used to cancel stale timers after _clear_main
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
        """Label-based button that respects background colour on all platforms."""
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
        # Top bar
        topbar = tk.Frame(self, bg=SURFACE, height=56)
        topbar.pack(fill="x", side="top")
        topbar.pack_propagate(False)

        tk.Label(topbar, text="Fatigue Induction Task", font=self.f_heading,
                 fg=ACCENT, bg=SURFACE).pack(side="left", padx=20, pady=10)

        self.lbl_level = tk.Label(topbar, text="", font=self.f_body,
                                  fg=TEXT_SEC, bg=SURFACE)
        self.lbl_level.pack(side="left", padx=8)

        self.lbl_trial = tk.Label(topbar, text="", font=self.f_small,
                                  fg=TEXT_DIM, bg=SURFACE)
        self.lbl_trial.pack(side="right", padx=20)

        # Main canvas
        self.main = tk.Frame(self, bg=BG)
        self.main.pack(fill="both", expand=True, padx=40, pady=24)

        # Status bar
        statusbar = tk.Frame(self, bg=SURFACE, height=34)
        statusbar.pack(fill="x", side="bottom")
        statusbar.pack_propagate(False)

        self.lbl_status = tk.Label(statusbar, text="", font=self.f_small,
                                   fg=TEXT_DIM, bg=SURFACE)
        self.lbl_status.pack(side="left", padx=16, pady=6)

        tk.Label(statusbar, text=f"Logging → {self.logger.filepath}",
                 font=self.f_small, fg=TEXT_DIM, bg=SURFACE).pack(side="right", padx=16)

    def _clear_main(self):
        # Bump token so any pending countdown callbacks become no-ops
        self._timer_token += 1
        for w in self.main.winfo_children():
            w.destroy()

    def _set_status(self, text):
        self.lbl_status.config(text=text)

    def _update_header(self):
        cfg = LEVEL_CONFIG[self.current_level]
        self.lbl_level.config(text=cfg["label"])
        self.lbl_trial.config(text=f"Trial {self.trial_num}  ·  Block {self.block_num}")

    #  SCREENS

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
                "Memorize their positions and types.\n"
                "Then recall them on a blank grid.\n\n"
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
                         (3, "Level 3\n+ Sequence")]:
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
        if cfg["seq_len"] > 0:
            steps.append(f"5.  Also memorise a {cfg['seq_len']}-letter sequence and reproduce it in order.")
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

    #  TRIAL FLOW

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

        if cfg["seq_len"] > 0:
            pool = string.ascii_uppercase[:8]
            self.seq_string = "".join(random.choices(pool, k=cfg["seq_len"]))
        else:
            self.seq_string = ""

        self.selected_cells = {}

    # STIMULUS DISPLAY 

    def _show_stimulus(self):
        self._clear_main()
        cfg = LEVEL_CONFIG[self.current_level]
        self._set_status("Memorise the grid.")

        # Use pack into main directly — avoid place() for dynamic content
        wrapper = tk.Frame(self.main, bg=BG)
        wrapper.pack(expand=True)  # vertically centred

        tk.Label(wrapper, text="Memorise", font=self.f_heading,
                 fg=TEXT_DIM, bg=BG).pack(pady=(20, 12))

        grid_f = tk.Frame(wrapper, bg=SURFACE)
        grid_f.pack()
        self._draw_grid_stimulus(grid_f)

        # Code display
        if self.code_string:
            tk.Label(wrapper, text="Code to memorise:",
                     font=self.f_body, fg=TEXT_DIM, bg=BG).pack(pady=(20, 4))
            # Space out characters manually — no letterSpacing kwarg in Tkinter
            spaced = "   ".join(self.code_string)
            tk.Label(wrapper, text=spaced, font=self.f_code,
                     fg=ACCENT2, bg=BG).pack()

        # Sequence display
        if self.seq_string:
            tk.Label(wrapper, text="Sequence to memorise (in order):",
                     font=self.f_body, fg=TEXT_DIM, bg=BG).pack(pady=(16, 6))
            seq_row = tk.Frame(wrapper, bg=BG)
            seq_row.pack()
            for i, ch in enumerate(self.seq_string):
                box = tk.Frame(seq_row, bg=SURFACE2, width=52, height=56)
                box.pack(side="left", padx=4)
                box.pack_propagate(False)
                tk.Label(box, text=str(i + 1), font=self.f_small,
                         fg=TEXT_DIM, bg=SURFACE2).pack(pady=(6, 0))
                tk.Label(box, text=ch, font=self.f_heading,
                         fg=ACCENT, bg=SURFACE2).pack()

        # Progress bar
        bar_bg = tk.Frame(wrapper, bg=SURFACE2, height=5, width=420)
        bar_bg.pack(pady=(20, 6))
        bar_bg.pack_propagate(False)
        bar_fill = tk.Frame(bar_bg, bg=ACCENT, height=5)
        bar_fill.place(x=0, y=0, relwidth=1.0, height=5)

        # Start countdown — capture token at call time
        disp = cfg["display_ms"]
        token = self._timer_token
        self._run_countdown(bar_fill, disp, disp, token)
        self.after(disp, lambda: self._safe_proceed(token, self._show_blank_then_recall))

    def _run_countdown(self, bar_fill, remaining, total, token):
        """Shrink bar_fill each tick. Stops if token has changed (screen cleared)."""
        if self._timer_token != token:
            return
        if remaining <= 0:
            return
        try:
            frac = remaining / total
            bar_fill.place_configure(relwidth=frac)
        except tk.TclError:
            return
        self.after(50, lambda: self._run_countdown(bar_fill, remaining - 50, total, token))

    def _safe_proceed(self, token, callback):
        """Only proceed if the screen hasn't been cleared since we scheduled this."""
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
        self._set_status("Recall: click cells, then assign a shape.")
        self.response_start = time.time()

        # Two-column layout
        left = tk.Frame(self.main, bg=BG)
        left.pack(side="left", fill="y", padx=(20, 30), pady=20)

        right = tk.Frame(self.main, bg=BG)
        right.pack(side="left", fill="both", expand=True, pady=20)

        # Left: grid
        tk.Label(left, text="Click the correct cells",
                 font=self.f_body, fg=TEXT_SEC, bg=BG).pack(pady=(0, 10))

        grid_f = tk.Frame(left, bg=SURFACE)
        grid_f.pack()
        self._draw_grid_recall(grid_f)

        # Left: shape picker
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

        # Right: code entry
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

        # Right: sequence entry
        if cfg["seq_len"] > 0:
            tk.Label(right, text="Re-enter the sequence:", font=self.f_heading,
                     fg=TEXT_SEC, bg=BG).pack(anchor="w", pady=(28, 6))
            self._seq_var = tk.StringVar()
            seq_entry = tk.Entry(right, textvariable=self._seq_var,
                                 font=self.f_mono, fg=ACCENT,
                                 bg=SURFACE2, insertbackground=ACCENT,
                                 relief="flat", bd=0,
                                 width=cfg["seq_len"] + 2,
                                 justify="center")
            seq_entry.pack(anchor="w", ipady=12, ipadx=12)
        else:
            self._seq_var = None

        tk.Label(right, text="Select a shape from the picker,\nthen click grid cells to place it.\nClick a placed cell again to deselect.",
                 font=self.f_small, fg=TEXT_DIM, bg=BG, justify="left").pack(anchor="w", pady=(28, 0))

        self._make_btn(right, "Submit Response", self._submit_response,
                       padx=24, pady=12,
                       pack_kwargs={"anchor": "w", "pady": (24, 0)})

    def _draw_grid_recall(self, parent):
        CELL = 88
        self.grid_buttons  = []
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

    # ── SUBMIT ────────────────────────────────

    def _submit_response(self):
        rt_ms = int((time.time() - self.response_start) * 1000)

        correct_set = {(sh, cell) for sh, cell in self.stim_items}
        user_set    = {(sh, cell) for cell, sh in self.selected_cells.items()}
        grid_correct = len(correct_set & user_set)
        grid_total   = len(correct_set)

        code_entered = self._code_var.get().strip().upper() if self._code_var else ""
        code_correct = (code_entered == self.code_string) if self.code_string else True

        seq_entered  = self._seq_var.get().strip().upper() if self._seq_var else ""
        seq_correct  = (seq_entered == self.seq_string) if self.seq_string else True

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
            seq_shown=self.seq_string,
            seq_entered=seq_entered,
            seq_correct=int(seq_correct),
            response_time_ms=rt_ms,
        )

        self._show_feedback(grid_correct, grid_total, code_correct, seq_correct)

    # FEEDBACK
    def _show_feedback(self, gc, gt, cc, sc):
        self._clear_main()
        cfg = LEVEL_CONFIG[self.current_level]

        wrapper = tk.Frame(self.main, bg=BG)
        wrapper.pack(expand=True)

        score_col = CORRECT if gc == gt else (ACCENT if gc > gt // 2 else WRONG)
        tk.Label(wrapper, text=f"Grid: {gc} / {gt}", font=self.f_heading,
                 fg=score_col, bg=BG).pack(pady=6)

        if cfg["code_len"] > 0:
            col = CORRECT if cc else WRONG
            tk.Label(wrapper, text=f"Code: {'Correct' if cc else 'Wrong'}",
                     font=self.f_body, fg=col, bg=BG).pack(pady=2)

        if cfg["seq_len"] > 0:
            col = CORRECT if sc else WRONG
            tk.Label(wrapper, text=f"Sequence: {'Correct' if sc else 'Wrong'}",
                     font=self.f_body, fg=col, bg=BG).pack(pady=2)

        answer = "  ".join([f"{sh} -> cell {cell}" for sh, cell in self.stim_items])
        tk.Label(wrapper, text=f"Correct answer: {answer}",
                 font=self.f_small, fg=TEXT_DIM, bg=BG, wraplength=600).pack(pady=(14, 0))

        # Level progress indicator 
        TRIALS_PER_LEVEL = TRIALS_PER_BLOCK * 3   # 15
        done  = self.trials_in_level
        left  = TRIALS_PER_LEVEL - done

        if self.current_level < 3:
            prog_frame = tk.Frame(wrapper, bg=SURFACE2, padx=20, pady=12)
            prog_frame.pack(pady=(22, 0), fill="x", padx=60)

            header = tk.Frame(prog_frame, bg=SURFACE2)
            header.pack(fill="x")
            tk.Label(header, text="Level progress",
                     font=self.f_small, fg=TEXT_DIM, bg=SURFACE2).pack(side="left")
            tk.Label(header, text=f"{done} / {TRIALS_PER_LEVEL} trials",
                     font=self.f_small, fg=TEXT_SEC, bg=SURFACE2).pack(side="right")

            # Bar track
            bar_track = tk.Frame(prog_frame, bg=GRID_IDLE, height=8)
            bar_track.pack(fill="x", pady=(6, 8))
            bar_track.pack_propagate(False)
            frac = min(done / TRIALS_PER_LEVEL, 1.0)
            bar_fill = tk.Frame(bar_track, bg=ACCENT, height=8)
            bar_fill.place(x=0, y=0, relwidth=frac, height=8)

            if left <= 0:
                msg     = "Level up next!"
                msg_col = ACCENT2
            elif left == 1:
                msg     = "1 trial until next level"
                msg_col = ACCENT2
            else:
                msg     = f"{left} trials until next level"
                msg_col = TEXT_SEC
            tk.Label(prog_frame, text=msg, font=self.f_small,
                     fg=msg_col, bg=SURFACE2).pack(anchor="w")
        else:
            # Already at max level — show overall trial count only
            tk.Label(wrapper, text=f"Max level  ·  Trial {self.trial_num} overall",
                     font=self.f_small, fg=TEXT_DIM, bg=BG).pack(pady=(18, 0))

        if self.trials_in_block >= TRIALS_PER_BLOCK:
            self.after(1200, self._show_fatigue_report)
        else:
            self.after(1200, self._next_trial)

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
            ("1", "Normal",           CORRECT, "Alert and focused"),
            ("2", "Mildly Fatigued",  ACCENT,  "Somewhat tired, effort required"),
            ("3", "Severely Fatigued",WRONG,   "Very tired, struggling to concentrate"),
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

        # Escalate every 3 blocks
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

#  ENTRY POINT

if __name__ == "__main__":
    app = CFITApp()
    app.mainloop()