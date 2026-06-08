"""
dashboard.py
═══════════════════════════════════════════════════════════════════
BLS Italy Bot — Premium Dark Dashboard
═══════════════════════════════════════════════════════════════════
• One-click START runs the entire bot in a background thread
• Live scrolling log console (never freezes the GUI)
• Real-time stats: center, date, proxy, loop count
• Animated status indicator dot
• Booking alert popup with sound
• Pause / Resume / Stop controls
"""

import os
import queue
import threading
import time
import tkinter as tk
from tkinter import font as tkfont, messagebox, scrolledtext

# ══════════════════════════════════════════════════
# PALETTE & DESIGN TOKENS
# ══════════════════════════════════════════════════
BG_DEEP    = "#0a0a0f"    # outermost background
BG_PANEL   = "#12121a"    # card / panel background
BG_CONSOLE = "#0d0f0a"    # terminal console background
GOLD       = "#c9a227"    # primary accent
GOLD_DIM   = "#8a6e1a"    # dimmed gold
WHITE      = "#e8e8e8"
GREY       = "#5a5a6a"
GREEN      = "#00e676"    # ACTIVE status
ORANGE     = "#ffa726"    # PAUSED status
RED        = "#ef5350"    # STOPPED/ERROR
CYAN       = "#40c4ff"    # info highlights
LOG_TEXT   = "#a8ff78"    # terminal green log text
LOG_ERR    = "#ff6b6b"    # error log text
LOG_WARN   = "#ffd93d"    # warning log text
LOG_INFO   = "#74b9ff"    # info log text

BTN_HOVER_BG   = GOLD
BTN_HOVER_FG   = "#000000"
BTN_NORMAL_BG  = "#1e1e2e"
BTN_NORMAL_FG  = GOLD


class MainMenuWindow:
    """
    Premium BLS Italy Bot dashboard window.
    Receives the root Tk window after login (passed from app.py).
    """

    def __init__(self, root: tk.Tk):
        self.root       = root
        self.bot_running = False
        self.bot_paused  = False
        self._log_queue  = queue.Queue()
        self._anim_id    = None
        self._dot_state  = 0
        self._loop_count = 0
        self._current_proxy = None

        self._setup_window()
        self._build_header()
        self._build_status_bar()
        self._build_stats_grid()
        self._build_control_buttons()
        self._build_console()
        self._build_footer()

        # Start the log queue drain loop
        self._drain_log_queue()

    # ──────────────────────────────────────────────
    # Window Setup
    # ──────────────────────────────────────────────
    def _setup_window(self):
        self.root.title("BLS Italy Bot  |  RakenTech")
        self.root.geometry("780x680")
        self.root.minsize(700, 580)
        self.root.resizable(True, True)
        self.root.configure(bg=BG_DEEP)

        # Custom title-bar colour (Windows registry trick via tk call)
        try:
            self.root.wm_attributes("-alpha", 1.0)
        except Exception:
            pass

        # Fonts
        self._font_title    = tkfont.Font(family="Segoe UI", size=22, weight="bold")
        self._font_subtitle = tkfont.Font(family="Segoe UI", size=10)
        self._font_label    = tkfont.Font(family="Segoe UI", size=9, weight="bold")
        self._font_value    = tkfont.Font(family="Segoe UI", size=10, weight="bold")
        self._font_btn      = tkfont.Font(family="Segoe UI", size=10, weight="bold")
        self._font_console  = tkfont.Font(family="Consolas",  size=9)
        self._font_status   = tkfont.Font(family="Segoe UI",  size=10, weight="bold")

    # ──────────────────────────────────────────────
    # Header
    # ──────────────────────────────────────────────
    def _build_header(self):
        hdr = tk.Frame(self.root, bg=BG_PANEL, height=90)
        hdr.pack(fill="x", padx=0, pady=0)
        hdr.pack_propagate(False)

        # Gold accent bar
        tk.Frame(hdr, bg=GOLD, height=3).pack(fill="x", side="top")

        inner = tk.Frame(hdr, bg=BG_PANEL)
        inner.pack(fill="both", expand=True, padx=24, pady=10)

        # Bot emoji + title
        tk.Label(inner, text="🤖  BLS ITALY BOT",
                 font=self._font_title, fg=GOLD, bg=BG_PANEL,
                 anchor="w").pack(side="left")

        # Right-side version badge
        badge = tk.Frame(inner, bg="#1e1e2e", padx=10, pady=4)
        badge.pack(side="right", anchor="n", pady=6)
        tk.Label(badge, text="v2.0 PRO", font=self._font_label,
                 fg=CYAN, bg="#1e1e2e").pack()
        tk.Label(badge, text="by RakenTech", font=self._font_subtitle,
                 fg=GREY, bg="#1e1e2e").pack()

        # Subtitle
        tk.Label(inner, text="Italy Visa Appointment Automation  •  Pakistan",
                 font=self._font_subtitle, fg=GREY, bg=BG_PANEL,
                 anchor="w").place(x=0, y=52)

    # ──────────────────────────────────────────────
    # Status Bar (animated dot + status text)
    # ──────────────────────────────────────────────
    def _build_status_bar(self):
        bar = tk.Frame(self.root, bg="#16162a", height=38)
        bar.pack(fill="x", padx=0)
        bar.pack_propagate(False)

        inner = tk.Frame(bar, bg="#16162a")
        inner.pack(expand=True, fill="both", padx=18, pady=6)

        self._status_dot  = tk.Label(inner, text="●", font=self._font_status,
                                      fg=GREY, bg="#16162a")
        self._status_dot.pack(side="left")

        self._status_text = tk.Label(inner,
                                      text="  STATUS:  IDLE — Ready to start",
                                      font=self._font_status,
                                      fg=GREY, bg="#16162a", anchor="w")
        self._status_text.pack(side="left")

    # ──────────────────────────────────────────────
    # Stats Grid (4 cards)
    # ──────────────────────────────────────────────
    def _build_stats_grid(self):
        grid = tk.Frame(self.root, bg=BG_DEEP)
        grid.pack(fill="x", padx=16, pady=(10, 4))

        self._stat_labels = {}

        stats = [
            ("🏢", "CENTER",     "—"),
            ("📅", "TARGET DATE","—"),
            ("📡", "PROXY",      "Direct"),
            ("🔁", "LOOPS",      "0"),
        ]

        for col, (icon, label, default) in enumerate(stats):
            card = tk.Frame(grid, bg=BG_PANEL, padx=14, pady=10,
                            relief="flat", bd=0)
            card.grid(row=0, column=col, padx=6, sticky="ew")
            grid.columnconfigure(col, weight=1)

            tk.Label(card, text=f"{icon}  {label}",
                     font=self._font_label, fg=GREY, bg=BG_PANEL).pack(anchor="w")
            val_lbl = tk.Label(card, text=default,
                               font=self._font_value, fg=WHITE, bg=BG_PANEL,
                               wraplength=140, justify="left")
            val_lbl.pack(anchor="w", pady=(2, 0))
            self._stat_labels[label] = val_lbl

    # ──────────────────────────────────────────────
    # Control Buttons
    # ──────────────────────────────────────────────
    def _build_control_buttons(self):
        btn_row = tk.Frame(self.root, bg=BG_DEEP)
        btn_row.pack(fill="x", padx=16, pady=(8, 6))

        buttons = [
            ("▶  START",   GREEN,  self.start_bot,  "start"),
            ("⏸  PAUSE",   ORANGE, self.stop_bot,   "stop"),
            ("▶  RESUME",  CYAN,   self.resume_bot,  "resume"),
            ("✖  CLOSE",   RED,    self.close_bot,  "close"),
        ]

        self._btns = {}
        for col, (label, color, cmd, key) in enumerate(buttons):
            btn = tk.Button(
                btn_row,
                text=label,
                font=self._font_btn,
                bg=BTN_NORMAL_BG,
                fg=color,
                activebackground=color,
                activeforeground="#000",
                relief="flat",
                bd=0,
                padx=0, pady=10,
                cursor="hand2",
                command=cmd,
            )
            btn.grid(row=0, column=col, padx=5, sticky="ew")
            btn_row.columnconfigure(col, weight=1)

            # Hover effects
            btn.bind("<Enter>", lambda e, b=btn, c=color: b.configure(bg=c, fg="#000"))
            btn.bind("<Leave>", lambda e, b=btn, c=color: b.configure(bg=BTN_NORMAL_BG, fg=c))

            self._btns[key] = btn

    # ──────────────────────────────────────────────
    # Live Log Console
    # ──────────────────────────────────────────────
    def _build_console(self):
        console_frame = tk.Frame(self.root, bg=BG_DEEP)
        console_frame.pack(fill="both", expand=True, padx=16, pady=(4, 4))

        # Header bar
        hdr = tk.Frame(console_frame, bg="#1a1a2e", padx=12, pady=5)
        hdr.pack(fill="x")
        tk.Label(hdr, text="⬛  LIVE LOG CONSOLE",
                 font=self._font_label, fg=CYAN, bg="#1a1a2e").pack(side="left")

        clr_btn = tk.Button(hdr, text="CLEAR", font=tkfont.Font(family="Segoe UI", size=8),
                            bg="#1a1a2e", fg=GREY, relief="flat",
                            cursor="hand2", bd=0, command=self._clear_log)
        clr_btn.pack(side="right")

        # ScrolledText console
        self._console = scrolledtext.ScrolledText(
            console_frame,
            bg=BG_CONSOLE,
            fg=LOG_TEXT,
            font=self._font_console,
            relief="flat",
            bd=0,
            insertbackground=LOG_TEXT,
            wrap="word",
            state="disabled",
            padx=10,
            pady=6,
        )
        self._console.pack(fill="both", expand=True)

        # Configure text tags for colored output
        self._console.tag_config("info",    foreground=LOG_TEXT)
        self._console.tag_config("error",   foreground=LOG_ERR)
        self._console.tag_config("warn",    foreground=LOG_WARN)
        self._console.tag_config("highlight", foreground=GOLD)
        self._console.tag_config("system",  foreground=CYAN)

    # ──────────────────────────────────────────────
    # Footer
    # ──────────────────────────────────────────────
    def _build_footer(self):
        foot = tk.Frame(self.root, bg=BG_PANEL, height=28)
        foot.pack(fill="x", side="bottom")
        foot.pack_propagate(False)
        tk.Frame(foot, bg=GOLD_DIM, height=1).pack(fill="x", side="top")
        tk.Label(foot, text="RakenTech  •  BLS Italy Bot v2.0  •  Unlimited Usage",
                 font=tkfont.Font(family="Segoe UI", size=8),
                 fg=GREY, bg=BG_PANEL).pack(side="right", padx=16)

    # ──────────────────────────────────────────────
    # Logging (thread-safe via queue)
    # ──────────────────────────────────────────────
    def log(self, message: str):
        """Thread-safe log — can be called from the bot thread."""
        self._log_queue.put(message)

    def _drain_log_queue(self):
        """Poll the queue every 100ms and write to console."""
        try:
            while not self._log_queue.empty():
                msg = self._log_queue.get_nowait()
                self._write_to_console(msg)
            self.root.after(100, self._drain_log_queue)
        except Exception:
            pass  # Window was destroyed

    def _write_to_console(self, msg: str):
        """Write one line to the console with colour tagging."""
        try:
            self._console.configure(state="normal")

            msg_lower = msg.lower()
            if any(w in msg_lower for w in ["\u274c", "error", "failed", "fatal", "exception"]):
                tag = "error"
            elif any(w in msg_lower for w in ["\u26a0\ufe0f", "warning", "warn", "skipped"]):
                tag = "warn"
            elif any(w in msg_lower for w in ["\u2705", "success", "booked", "found", "otp"]):
                tag = "highlight"
            elif any(w in msg_lower for w in ["\U0001f310", "\U0001f916", "launched", "navigating", "status"]):
                tag = "system"
            else:
                tag = "info"

            ts = time.strftime("[%H:%M:%S] ")
            self._console.insert("end", ts + msg + "\n", tag)
            self._console.see("end")
            self._console.configure(state="disabled")
        except Exception:
            pass  # Console may be destroyed

    def _clear_log(self):
        self._console.configure(state="normal")
        self._console.delete("1.0", "end")
        self._console.configure(state="disabled")

    # ──────────────────────────────────────────────
    # Animated Status Dot
    # ──────────────────────────────────────────────
    def _start_dot_animation(self, color: str):
        self._dot_state = 0
        self._dot_color = color
        self._animate_dot()

    def _animate_dot(self):
        if not self.bot_running:
            return
        colors = [self._dot_color, BG_DEEP]
        self._status_dot.configure(fg=colors[self._dot_state % 2])
        self._dot_state += 1
        self._anim_id = self.root.after(600, self._animate_dot)

    def _stop_dot_animation(self, final_color: str = GREY):
        if self._anim_id:
            self.root.after_cancel(self._anim_id)
        self._status_dot.configure(fg=final_color)

    # ──────────────────────────────────────────────
    # Stats Update (called from bot thread via queue)
    # ──────────────────────────────────────────────
    def update_stats(self, loop_count: int, proxy_entry=None):
        """Thread-safe stats update via root.after."""
        config = {}
        try:
            import selenium_bot
            config = selenium_bot.live_state.get("config", {})
        except Exception:
            pass

        def _do():
            self._stat_labels["LOOPS"].configure(text=str(loop_count))
            self._stat_labels["CENTER"].configure(
                text=config.get("Center", "—"))
            self._stat_labels["TARGET DATE"].configure(
                text=config.get("Preferred Date", "—"))
            proxy_text = proxy_entry.as_server() if proxy_entry else "Direct"
            self._stat_labels["PROXY"].configure(text=proxy_text)

        self.root.after(0, _do)

    # ──────────────────────────────────────────────
    # Config File Parser
    # ──────────────────────────────────────────────
    def parse_config_file(self, path: str) -> dict:
        config = {}
        if not os.path.exists(path):
            return config
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and ":" in line and not line.startswith("#"):
                    key, _, value = line.partition(":")
                    config[key.strip()] = value.strip()
        return config

    # ──────────────────────────────────────────────
    # Control Actions
    # ──────────────────────────────────────────────
    def start_bot(self):
        if self.bot_running:
            messagebox.showwarning("Bot Running", "Bot is already running!")
            return

        config_path = "./pending_reservations/testing.txt"
        image_path  = "./pending_reservations/passport_img.png"

        if not os.path.exists(config_path):
            messagebox.showerror("Missing Files",
                "⚠️ testing.txt not found in pending_reservations/")
            return
        if not os.path.exists(image_path):
            messagebox.showerror("Missing Files",
                "⚠️ passport_img.png not found in pending_reservations/")
            return

        config = self.parse_config_file(config_path)
        if not config.get("Email") or not config.get("Password"):
            messagebox.showerror("Config Error",
                "Email and Password must be set in testing.txt")
            return

        self.bot_running = True
        self.bot_paused  = False

        # Update UI
        self._status_text.configure(
            text="  STATUS:  ● ACTIVE — Bot is running",
            fg=GREEN)
        self._btns["start"].configure(state="disabled", fg=GREY, bg=BTN_NORMAL_BG)
        self._start_dot_animation(GREEN)

        # Update stats immediately from config
        self._stat_labels["CENTER"].configure(text=config.get("Center", "—"))
        self._stat_labels["TARGET DATE"].configure(text=config.get("Preferred Date", "—"))
        self._stat_labels["LOOPS"].configure(text="0")

        self.log("🚀 Bot starting — all systems initializing...")
        self.log(f"📋 Config loaded: {len(config)} keys")
        self.log(f"   Center: {config.get('Center')}  |  "
                 f"Date: {config.get('Preferred Date')}  |  "
                 f"IP Rotator: {config.get('IP Rotator', 'false')}")

        # Launch bot in background thread (so GUI never freezes)
        import selenium_bot
        bot_thread = threading.Thread(
            target=selenium_bot.launch_bls_automation,
            args=(self, config, image_path),
            daemon=True,
            name="BLSBotEngine"
        )
        bot_thread.start()

    def stop_bot(self):
        """Pause the bot — user can safely edit testing.txt."""
        if not self.bot_running or self.bot_paused:
            return

        import selenium_bot
        selenium_bot.live_state["pause_flag"] = True
        self.bot_paused = True

        self._status_text.configure(
            text="  STATUS:  ⏸ PAUSED — Edit files then Resume",
            fg=ORANGE)
        self._stop_dot_animation(ORANGE)
        self.log("⏸️ Bot PAUSED — You can safely edit pending_reservations/ files now")
        self.log("   Click RESUME when ready to continue with updated config.")

    def resume_bot(self):
        """Reload config from disk and resume the bot."""
        if not self.bot_running or not self.bot_paused:
            return

        config_path = "./pending_reservations/testing.txt"
        new_config  = self.parse_config_file(config_path)

        import selenium_bot
        selenium_bot.update_live_session(new_config)
        selenium_bot.live_state["pause_flag"] = False

        self.bot_paused = False
        self._status_text.configure(
            text="  STATUS:  ● ACTIVE — Bot resumed",
            fg=GREEN)
        self._start_dot_animation(GREEN)

        self.log("▶️ Bot RESUMED with updated config:")
        self.log(f"   Center: {new_config.get('Center')}  |  "
                 f"Date: {new_config.get('Preferred Date')}")

    def on_bot_completed(self):
        """Called from bot thread when booking was successful."""
        self.bot_running = False
        self.bot_paused  = False
        self._status_text.configure(
            text="  STATUS:  ✅ COMPLETED — Appointment booked!",
            fg=GREEN)
        self._stop_dot_animation(GREEN)
        self._btns["start"].configure(state="normal", fg=GREEN)
        self.log("🏆 Mission complete! Bot has been stopped.")

    def on_bot_stopped(self):
        """Called when bot engine exits for any reason."""
        if not self.bot_running:
            return
        self.bot_running = False
        self.bot_paused  = False
        self._status_text.configure(
            text="  STATUS:  ■ STOPPED",
            fg=RED)
        self._stop_dot_animation(RED)
        self._btns["start"].configure(state="normal", fg=GREEN)

    def show_booking_alert(self, message: str):
        """Show a prominent booking success popup."""
        import winsound
        try:
            winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
        except Exception:
            pass
        messagebox.showinfo(
            "🎉 APPOINTMENT BOOKED!",
            message + "\n\nPlease check your browser and email for confirmation.",
            icon="info"
        )

    def close_bot(self):
        if self.bot_running:
            if not messagebox.askyesno(
                "Confirm Close",
                "The bot is currently running.\nAre you sure you want to close it?"
            ):
                return
        # Signal stop
        try:
            import selenium_bot
            selenium_bot.live_state["stop_flag"]  = True
            selenium_bot.live_state["pause_flag"] = False
        except Exception:
            pass
        self.root.quit()