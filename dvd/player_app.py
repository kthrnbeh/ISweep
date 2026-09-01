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

    def __init__(self, root: tk.Tk, controller: VLCPlaybackController) -> None:
        self.root = root
        self.controller = controller
        self.current_source: MediaSource | None = None

        self.root.title("ISweep Player")
        self.root.geometry("1100x720")
        self.root.minsize(760, 500)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build_ui()

        # Tk must create the native HWND before libVLC can render into it.
        self.root.update_idletasks()
        self.controller.set_video_output(self.video_frame.winfo_id())

        self._poll_player()

    def _build_ui(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        shell = ttk.Frame(self.root, padding=10)
        shell.grid(row=0, column=0, sticky="nsew")
        shell.columnconfigure(0, weight=1)
        shell.rowconfigure(1, weight=1)

        top = ttk.Frame(shell)
        top.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        top.columnconfigure(2, weight=1)

        ttk.Label(top, text="ISweep Player", font=("Segoe UI", 16, "bold")).grid(
            row=0, column=0, padx=(0, 14)
        )
        ttk.Button(top, text="Open Video", command=self.open_file).grid(
            row=0, column=1, padx=(0, 8)
        )
        ttk.Button(top, text="Load DVD", command=self.open_detected_dvd).grid(
            row=0, column=2, sticky="w"
        )

        self.source_label = ttk.Label(top, text="No media loaded", anchor="e")
        self.source_label.grid(row=0, column=3, sticky="e")

        # A plain Tk frame gives VLC a stable native window handle on Windows.
        self.video_frame = tk.Frame(shell, bg="black")
        self.video_frame.grid(row=1, column=0, sticky="nsew")

        controls = ttk.Frame(shell, padding=(0, 10, 0, 0))
        controls.grid(row=2, column=0, sticky="ew")
        controls.columnconfigure(9, weight=1)

        ttk.Button(controls, text="Play", command=self.play).grid(row=0, column=0, padx=3)
        ttk.Button(controls, text="Pause", command=self.pause).grid(row=0, column=1, padx=3)
        ttk.Button(controls, text="Stop", command=self.stop).grid(row=0, column=2, padx=3)
        ttk.Separator(controls, orient="vertical").grid(
            row=0, column=3, sticky="ns", padx=8
        )
        ttk.Button(controls, text="-15 sec", command=lambda: self.seek(-15)).grid(
            row=0, column=4, padx=3
        )
        ttk.Button(controls, text="+15 sec", command=lambda: self.seek(15)).grid(
            row=0, column=5, padx=3
        )
        ttk.Separator(controls, orient="vertical").grid(
            row=0, column=6, sticky="ns", padx=8
        )
        ttk.Button(controls, text="Mute", command=self.controller.mute).grid(
            row=0, column=7, padx=3
        )
        ttk.Button(controls, text="Unmute", command=self.controller.unmute).grid(
            row=0, column=8, padx=3
        )

        self.clock_label = ttk.Label(controls, text="00:00 / --:--", anchor="e")
        self.clock_label.grid(row=0, column=9, sticky="e")

        self.status_label = ttk.Label(
            shell,
            text="Ready. ISweep filtering will connect to this same playback clock.",
            anchor="w",
        )
        self.status_label.grid(row=3, column=0, sticky="ew", pady=(6, 0))

    def load_source(self, source: MediaSource, *, autoplay: bool = True) -> None:
        try:
            self.controller.load(source)
            self.current_source = source
            self.source_label.config(text=source.title or source.location)
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
