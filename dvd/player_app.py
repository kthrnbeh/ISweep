"""ISweep DVD - first real Host Player window.

This is the first UI that lets ISweep directly own playback instead of
controlling a separate DVD player from the outside.

Prototype capabilities:
- open a normal video file
- detect/load a mounted DVD-Video disc
- play / pause / stop
- mute / unmute
- seek backward/forward 15 seconds
- expose the real playback clock that later ISweep filtering will use

The original media is never edited or rewritten.
"""

from __future__ import annotations

import argparse
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from dvd.playback import (
    MediaKind,
    MediaSource,
    PlaybackStatus,
    VLCPlaybackController,
    VLCUnavailableError,
)
from dvd.playback.disc import find_inserted_dvds


class ISweepPlayerApp:
    """Small Windows desktop player built around the ISweep playback API."""

    NAVY = "#102a36"
    BLUE = "#2f80ed"
    TEAL = "#16b8ad"
    SKY = "#eaf8fc"
    PANEL = "#ffffff"
    MUTED_TEXT = "#607783"

    def __init__(self, root: tk.Tk, controller: VLCPlaybackController) -> None:
        self.root = root
        self.controller = controller
        self.current_source: MediaSource | None = None

        self.root.title("ISweep Player")
        self.root.geometry("1180x780")
        self.root.minsize(860, 580)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self._configure_style()

        self._build_ui()

        # Tk must create the native HWND before libVLC can render into it.
        self.root.update_idletasks()
        self.controller.set_video_output(self.video_frame.winfo_id())

        self._poll_player()

    def _configure_style(self) -> None:
        """Configure the branded ttk theme without adding UI dependencies."""

        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure("App.TFrame", background=self.SKY)
        style.configure("Card.TFrame", background=self.PANEL)
        style.configure("Header.TFrame", background=self.PANEL)
        style.configure("Title.TLabel", background=self.PANEL, foreground=self.NAVY,
                        font=("Segoe UI", 19, "bold"))
        style.configure("Subtitle.TLabel", background=self.PANEL, foreground=self.MUTED_TEXT,
                        font=("Segoe UI", 9))
        style.configure("Section.TLabel", background=self.PANEL, foreground=self.NAVY,
                        font=("Segoe UI", 10, "bold"))
        style.configure("Status.TLabel", background=self.SKY, foreground=self.MUTED_TEXT,
                        font=("Segoe UI", 9))
        style.configure("Primary.TButton", background=self.BLUE, foreground="white",
                        borderwidth=0, padding=(14, 8), font=("Segoe UI", 9, "bold"))
        style.map("Primary.TButton", background=[("active", "#1769d1")])
        style.configure("Action.TButton", background="#f3f7fa", foreground=self.NAVY,
                        borderwidth=0, padding=(12, 8), font=("Segoe UI", 9, "bold"))
        style.map("Action.TButton", background=[("active", "#dcecf5")])
        style.configure("Pill.TLabel", background="#e5f8f5", foreground="#087f75",
                        padding=(10, 5), font=("Segoe UI", 9, "bold"))

    def _build_ui(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        shell = ttk.Frame(self.root, padding=(18, 16), style="App.TFrame")
        shell.grid(row=0, column=0, sticky="nsew")
        shell.columnconfigure(1, weight=1)
        shell.rowconfigure(1, weight=1)

        top = ttk.Frame(shell, padding=(18, 14), style="Header.TFrame")
        top.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        top.columnconfigure(4, weight=1)

        brand = tk.Canvas(top, width=38, height=38, highlightthickness=0, bg=self.PANEL)
        brand.create_oval(3, 3, 35, 35, fill=self.TEAL, outline="")
        brand.create_text(19, 19, text="I", fill="white", font=("Segoe UI", 18, "bold"))
        brand.grid(row=0, column=0, rowspan=2, padx=(0, 12))
        ttk.Label(top, text="ISweep Player", style="Title.TLabel").grid(
            row=0, column=1, sticky="w"
        )
        ttk.Label(top, text="Playback that follows your boundaries", style="Subtitle.TLabel").grid(
            row=1, column=1, sticky="w"
        )
        ttk.Button(top, text="Open Video", style="Primary.TButton", command=self.open_file).grid(
            row=0, column=2, rowspan=2, padx=(28, 8)
        )
        ttk.Button(top, text="Load DVD", style="Action.TButton", command=self.open_detected_dvd).grid(
            row=0, column=3, rowspan=2, sticky="w"
        )

        self.source_label = ttk.Label(top, text="No media loaded", style="Subtitle.TLabel", anchor="e")
        self.source_label.grid(row=0, column=4, rowspan=2, sticky="e", padx=(18, 0))

        # The library rail makes the app feel like a player, while the video
        # surface remains a plain native window for libVLC rendering.
        library = tk.Frame(shell, bg=self.NAVY, width=220, highlightthickness=0)
        library.grid(row=1, column=0, sticky="nsw", padx=(0, 10))
        library.grid_propagate(False)
        tk.Label(
            library, text="YOUR LIBRARY", bg=self.NAVY, fg="#9cc7d6",
            font=("Segoe UI", 9, "bold"), anchor="w",
        ).pack(fill="x", padx=18, pady=(22, 12))
        tk.Label(
            library, text="▣  Playlist", bg=self.NAVY, fg="white",
            font=("Segoe UI", 15, "bold"), anchor="w",
        ).pack(fill="x", padx=18, pady=(0, 18))
        self.playlist = tk.Listbox(
            library, height=8, bd=0, relief="flat", highlightthickness=0,
            bg="#173b49", fg="white", selectbackground=self.BLUE,
            selectforeground="white", activestyle="none",
            font=("Segoe UI", 10), exportselection=False,
        )
        self.playlist.insert("end", "  No media loaded")
        self.playlist.pack(fill="x", padx=12)
        tk.Label(
            library,
            text="ISweep will analyze upcoming speech\nand apply your saved filters during playback.",
            bg=self.NAVY, fg="#9cc7d6", justify="left", anchor="w",
            font=("Segoe UI", 9),
        ).pack(fill="x", padx=18, pady=(22, 0))

        stage = tk.Frame(shell, bg="#07151d", highlightthickness=0)
        stage.grid(row=1, column=1, sticky="nsew")
        stage.grid_rowconfigure(0, weight=1)
        stage.grid_columnconfigure(0, weight=1)
        self.video_frame = tk.Frame(stage, bg="#07151d", highlightthickness=0)
        self.video_frame.grid(row=0, column=0, sticky="nsew")

        controls = ttk.Frame(shell, padding=(18, 14), style="Card.TFrame")
        controls.grid(row=2, column=0, columnspan=2, sticky="ew")
        controls.columnconfigure(10, weight=1)
        ttk.Label(controls, text="PLAYBACK CONTROLS", style="Section.TLabel").grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 8)
        )
        ttk.Label(controls, text="SHARED FILTERS", style="Section.TLabel").grid(
            row=0, column=8, columnspan=2, sticky="e", pady=(0, 8)
        )

        ttk.Button(controls, text="Play", style="Primary.TButton", command=self.play).grid(row=1, column=0, padx=(0, 5))
        ttk.Button(controls, text="Pause", style="Action.TButton", command=self.pause).grid(row=1, column=1, padx=5)
        ttk.Button(controls, text="Stop", style="Action.TButton", command=self.stop).grid(row=1, column=2, padx=5)
        ttk.Separator(controls, orient="vertical").grid(
            row=1, column=3, sticky="ns", padx=12
        )
        ttk.Button(controls, text="−15 sec", style="Action.TButton", command=lambda: self.seek(-15)).grid(
            row=1, column=4, padx=5
        )
        ttk.Button(controls, text="+15 sec", style="Action.TButton", command=lambda: self.seek(15)).grid(
            row=1, column=5, padx=5
        )
        ttk.Separator(controls, orient="vertical").grid(
            row=1, column=6, sticky="ns", padx=12
        )
        ttk.Button(controls, text="Mute", style="Action.TButton", command=self.controller.mute).grid(
            row=1, column=7, padx=5
        )
        ttk.Button(controls, text="Unmute", style="Action.TButton", command=self.controller.unmute).grid(
            row=1, column=8, padx=5
        )

        self.filter_badge = ttk.Label(controls, text="FILTERING READY", style="Pill.TLabel")
        self.filter_badge.grid(row=1, column=9, padx=(16, 10), sticky="e")
        self.clock_label = ttk.Label(controls, text="00:00 / --:--", style="Section.TLabel", anchor="e")
        self.clock_label.grid(row=1, column=10, sticky="e")

        self.status_label = ttk.Label(
            shell,
            text="Ready. ISweep filtering will connect to this same playback clock.",
            anchor="w",
            style="Status.TLabel",
        )
        self.status_label.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(10, 0))

    def load_source(self, source: MediaSource, *, autoplay: bool = True) -> None:
        try:
            self.controller.load(source)
            self.current_source = source
            self.source_label.config(text=source.title or source.location)
            self.playlist.delete(0, "end")
            self.playlist.insert("end", f"  {source.title or source.location}")
            self.playlist.selection_set(0)
            self.status_label.config(text=f"Loaded {source.kind.value}: {source.location}")
            if autoplay:
                self.controller.play()
        except Exception as exc:
            messagebox.showerror("ISweep Player", f"Could not load this media.\n\n{exc}")

    def open_file(self) -> None:
        filename = filedialog.askopenfilename(
            title="Open video in ISweep Player",
            filetypes=[
                ("Video files", "*.mp4 *.mkv *.avi *.mov *.wmv *.m4v *.mpeg *.mpg *.vob"),
                ("All files", "*.*"),
            ],
        )
        if not filename:
            return

        path = Path(filename)
        self.load_source(
            MediaSource(
                kind=MediaKind.FILE,
                location=str(path),
                title=path.name,
            )
        )

    def open_detected_dvd(self) -> None:
        candidates = [candidate for candidate in find_inserted_dvds() if candidate.is_dvd_video]

        if not candidates:
            messagebox.showinfo(
                "ISweep Player",
                "No mounted DVD-Video disc was detected.\n\n"
                "Insert a DVD into a Windows optical drive and try again.",
            )
            return

        # Prototype 1 uses the first mounted DVD-Video drive. A later session
        # manager will present a device picker if more than one drive is active.
        drive = candidates[0].drive
        self.load_source(
            MediaSource(
                kind=MediaKind.DVD,
                location=drive,
                title=f"DVD {drive}",
            )
        )

    def play(self) -> None:
        if self.current_source is not None:
            self.controller.play()

    def pause(self) -> None:
        if self.current_source is not None:
            self.controller.pause()

    def stop(self) -> None:
        if self.current_source is not None:
            self.controller.stop()

    def seek(self, seconds: float) -> None:
        if self.current_source is not None:
            self.controller.seek_relative(seconds)

    def _poll_player(self) -> None:
        try:
            state = self.controller.get_state()
            self.clock_label.config(
                text=f"{self._format_time(state.position_seconds)} / "
                f"{self._format_time(state.duration_seconds)}"
            )

            status = state.status.value
            if state.muted:
                status += " · MUTED"
            self.status_label.config(text=status)
        except Exception:
            # A transient VLC read during startup/shutdown should not kill UI.
            pass

        self.root.after(250, self._poll_player)

    @staticmethod
    def _format_time(seconds: float | None) -> str:
        if seconds is None or seconds < 0:
            return "--:--"
        total = int(seconds)
        hours, remainder = divmod(total, 3600)
        minutes, secs = divmod(remainder, 60)
        if hours:
            return f"{hours:02d}:{minutes:02d}:{secs:02d}"
        return f"{minutes:02d}:{secs:02d}"

    def _on_close(self) -> None:
        try:
            self.controller.stop()
        finally:
            self.root.destroy()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Launch the ISweep Host Player")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--file", dest="file_path", help="Video file to open at startup")
    source.add_argument(
        "--dvd",
        dest="dvd_drive",
        help="DVD drive/root to open at startup (for example, drive D:)",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    root = tk.Tk()
    root.withdraw()

    try:
        controller = VLCPlaybackController()
    except VLCUnavailableError as exc:
        messagebox.showerror("ISweep Player setup", str(exc))
        root.destroy()
        return

    root.deiconify()
    app = ISweepPlayerApp(root, controller)

    if args.file_path:
        path = Path(args.file_path)
        app.load_source(
            MediaSource(MediaKind.FILE, str(path), path.name),
        )
    elif args.dvd_drive:
        app.load_source(
            MediaSource(MediaKind.DVD, args.dvd_drive, f"DVD {args.dvd_drive}"),
        )

    root.mainloop()


if __name__ == "__main__":
    main()
