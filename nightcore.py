#!/usr/bin/env python3
"""
Nightcore Maker - a tiny GUI to speed up + pitch up song files (and the reverse).

Two independent sliders:
  - Speed (tempo) %: how much faster/slower the track plays.
  - Pitch (semitones): how much higher/lower it sounds.
A "Link (classic)" toggle ties pitch to speed for the authentic sped-up-record sound:
  pitch_semitones = 12 * log2(speed).

High Quality uses the SoX (soxr) resampler at high precision for clean, real-nightcore sound.

Audio engine: ffmpeg/ffprobe. When built as an .exe these are bundled alongside,
so nothing needs to be installed.
"""

import os
import sys
import math
import shutil
import threading
import subprocess
import queue
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

APP_TITLE = "Nightcore Maker"
AUDIO_EXTS = (".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg", ".opus", ".wma", ".aiff")


# ----------------------------- ffmpeg locating -----------------------------
def _candidate_dirs():
    dirs = []
    # PyInstaller temp extraction dir
    if hasattr(sys, "_MEIPASS"):
        dirs.append(sys._MEIPASS)
    # Next to the exe / script
    if getattr(sys, "frozen", False):
        dirs.append(os.path.dirname(sys.executable))
    dirs.append(os.path.dirname(os.path.abspath(__file__)))
    dirs.append(os.getcwd())
    return dirs


def find_tool(name):
    exe = name + (".exe" if os.name == "nt" else "")
    for d in _candidate_dirs():
        p = os.path.join(d, exe)
        if os.path.isfile(p):
            return p
    found = shutil.which(name) or shutil.which(exe)
    return found


FFMPEG = find_tool("ffmpeg")
FFPROBE = find_tool("ffprobe")


def _no_window_kwargs():
    if os.name == "nt":
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        return {"startupinfo": si, "creationflags": 0x08000000}  # CREATE_NO_WINDOW
    return {}


# ----------------------------- audio helpers -----------------------------
def detect_soxr():
    """Not every ffmpeg build ships the soxr resampler; check before using it."""
    if not FFMPEG:
        return False
    try:
        out = subprocess.run([FFMPEG, "-hide_banner", "-resamplers"],
                             capture_output=True, text=True, **_no_window_kwargs())
        return "soxr" in (out.stdout + out.stderr).lower()
    except Exception:
        return False


SOXR_OK = detect_soxr()


def probe_sample_rate(path, default=44100):
    if not FFPROBE:
        return default
    try:
        out = subprocess.check_output(
            [FFPROBE, "-v", "error", "-select_streams", "a:0",
             "-show_entries", "stream=sample_rate", "-of", "csv=p=0", path],
            text=True, **_no_window_kwargs()
        ).strip().splitlines()
        return int(out[0]) if out and out[0].isdigit() else default
    except Exception:
        return default


def split_atempo(factor):
    """ffmpeg atempo accepts 0.5..2.0 reliably; decompose any factor into a chain."""
    factors = []
    f = factor
    while f > 2.0 + 1e-9:
        factors.append(2.0)
        f /= 2.0
    while f < 0.5 - 1e-9:
        factors.append(0.5)
        f /= 0.5
    factors.append(f)
    return factors


def build_filter(sr, speed_pct, semitones, high_quality):
    """
    speed_pct: tempo as a percentage (100 = original).
    semitones: pitch shift, independent of tempo.
    Returns an ffmpeg -af filter string.
    """
    tempo = speed_pct / 100.0
    pf = 2 ** (semitones / 12.0)                 # pitch factor
    atempo_total = tempo / pf                    # tempo correction after pitch shift
    new_rate = int(round(sr * pf))
    if high_quality and SOXR_OK:
        # best quality: SoX resampler (same idea as Audacity "High Quality")
        resample = f"aresample={sr}:resampler=soxr:precision=28"
    elif high_quality:
        # soxr not in this ffmpeg build -> ffmpeg's own high-quality swr resampler
        resample = f"aresample={sr}:resampler=swr:filter_size=256:cutoff=0.91"
    else:
        resample = f"aresample={sr}"
    parts = [f"asetrate={new_rate}", resample]
    for a in split_atempo(atempo_total):
        parts.append(f"atempo={a:.6f}")
    return ",".join(parts)


def output_args(fmt):
    if fmt == "mp3":
        return ["-c:a", "libmp3lame", "-b:a", "320k"], ".mp3"
    if fmt == "flac":
        return ["-c:a", "flac"], ".flac"
    return ["-c:a", "pcm_s16le"], ".wav"  # wav


def convert_file(in_path, out_dir, speed_pct, semitones, high_quality, fmt, suffix):
    sr = probe_sample_rate(in_path)
    flt = build_filter(sr, speed_pct, semitones, high_quality)
    codec, ext = output_args(fmt)
    base = os.path.splitext(os.path.basename(in_path))[0]
    out_path = os.path.join(out_dir, f"{base}{suffix}{ext}")
    cmd = [FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
           "-i", in_path, "-af", flt, *codec, out_path]
    proc = subprocess.run(cmd, capture_output=True, text=True, **_no_window_kwargs())
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "ffmpeg failed")
    return out_path


# ----------------------------- GUI -----------------------------
class NightcoreApp:
    def __init__(self, root):
        self.root = root
        root.title(APP_TITLE)
        root.geometry("640x620")
        root.minsize(560, 560)

        self.files = []
        self.out_dir = tk.StringVar(value="")
        self.fmt = tk.StringVar(value="mp3")
        self.suffix = tk.StringVar(value=" (nightcore)")
        self.hq = tk.BooleanVar(value=True)
        self.link = tk.BooleanVar(value=True)
        self.speed = tk.DoubleVar(value=130.0)   # %
        self.pitch = tk.DoubleVar(value=0.0)      # semitones (auto when linked)
        self.msgq = queue.Queue()
        self._building = False

        self._build_ui()
        self._sync_link()
        self.root.after(100, self._drain_log)

        if not FFMPEG or not FFPROBE:
            messagebox.showwarning(
                APP_TITLE,
                "ffmpeg/ffprobe not found.\n\nPlace ffmpeg.exe and ffprobe.exe next to "
                "this program (the build script bundles them automatically)."
            )

    def _build_ui(self):
        pad = {"padx": 10, "pady": 6}
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        # Files
        frm_files = ttk.LabelFrame(self.root, text="Songs")
        frm_files.pack(fill="both", expand=True, **pad)
        self.lst = tk.Listbox(frm_files, height=6, selectmode=tk.EXTENDED)
        self.lst.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=8)
        sb = ttk.Scrollbar(frm_files, orient="vertical", command=self.lst.yview)
        sb.pack(side="left", fill="y", pady=8)
        self.lst.config(yscrollcommand=sb.set)
        btns = ttk.Frame(frm_files)
        btns.pack(side="left", fill="y", padx=8, pady=8)
        ttk.Button(btns, text="Add files…", command=self.add_files).pack(fill="x", pady=2)
        ttk.Button(btns, text="Remove", command=self.remove_sel).pack(fill="x", pady=2)
        ttk.Button(btns, text="Clear", command=self.clear_files).pack(fill="x", pady=2)

        # Controls
        frm = ttk.LabelFrame(self.root, text="Settings")
        frm.pack(fill="x", **pad)

        # Speed
        row1 = ttk.Frame(frm); row1.pack(fill="x", padx=8, pady=(8, 2))
        ttk.Label(row1, text="Speed", width=8).pack(side="left")
        self.speed_scale = ttk.Scale(row1, from_=50, to=200, variable=self.speed,
                                     command=self._on_speed)
        self.speed_scale.pack(side="left", fill="x", expand=True, padx=6)
        self.speed_lbl = ttk.Label(row1, text="130%", width=7)
        self.speed_lbl.pack(side="left")

        # Pitch
        row2 = ttk.Frame(frm); row2.pack(fill="x", padx=8, pady=2)
        ttk.Label(row2, text="Pitch", width=8).pack(side="left")
        self.pitch_scale = ttk.Scale(row2, from_=-12, to=12, variable=self.pitch,
                                     command=self._on_pitch)
        self.pitch_scale.pack(side="left", fill="x", expand=True, padx=6)
        self.pitch_lbl = ttk.Label(row2, text="+0.0 st", width=7)
        self.pitch_lbl.pack(side="left")

        # Toggles
        row3 = ttk.Frame(frm); row3.pack(fill="x", padx=8, pady=2)
        ttk.Checkbutton(row3, text="Link pitch to speed (classic nightcore)",
                        variable=self.link, command=self._sync_link).pack(side="left")
        ttk.Checkbutton(row3, text="High Quality (soxr)",
                        variable=self.hq).pack(side="left", padx=16)

        # Presets
        row4 = ttk.Frame(frm); row4.pack(fill="x", padx=8, pady=2)
        ttk.Label(row4, text="Presets:").pack(side="left")
        for name, sp in [("Subtle 115%", 115), ("Classic 130%", 130), ("Hard 150%", 150)]:
            ttk.Button(row4, text=name,
                       command=lambda v=sp: self._preset(v)).pack(side="left", padx=3)

        # Output
        frm_out = ttk.LabelFrame(self.root, text="Output")
        frm_out.pack(fill="x", **pad)
        r = ttk.Frame(frm_out); r.pack(fill="x", padx=8, pady=4)
        ttk.Label(r, text="Folder:").pack(side="left")
        ttk.Entry(r, textvariable=self.out_dir).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(r, text="Browse…", command=self.pick_out).pack(side="left")
        r2 = ttk.Frame(frm_out); r2.pack(fill="x", padx=8, pady=4)
        ttk.Label(r2, text="Format:").pack(side="left")
        ttk.Combobox(r2, textvariable=self.fmt, values=["mp3", "wav", "flac"],
                     width=6, state="readonly").pack(side="left", padx=6)
        ttk.Label(r2, text="Name suffix:").pack(side="left", padx=(12, 0))
        ttk.Entry(r2, textvariable=self.suffix, width=16).pack(side="left", padx=6)

        # Action + progress
        frm_act = ttk.Frame(self.root); frm_act.pack(fill="x", **pad)
        self.go_btn = ttk.Button(frm_act, text="Make Nightcore", command=self.start)
        self.go_btn.pack(side="left")
        self.prog = ttk.Progressbar(frm_act, mode="determinate")
        self.prog.pack(side="left", fill="x", expand=True, padx=10)

        self.log = tk.Text(self.root, height=6, state="disabled", wrap="word")
        self.log.pack(fill="both", expand=False, padx=10, pady=(0, 10))

    # --- slider handling ---
    def _on_speed(self, _=None):
        self.speed_lbl.config(text=f"{self.speed.get():.0f}%")
        if self.link.get():
            self._apply_link()

    def _on_pitch(self, _=None):
        if self.link.get():
            return
        self.pitch_lbl.config(text=f"{self.pitch.get():+.1f} st")

    def _apply_link(self):
        st = 12 * math.log2(self.speed.get() / 100.0)
        self.pitch.set(st)
        self.pitch_lbl.config(text=f"{st:+.1f} st")

    def _sync_link(self):
        if self.link.get():
            self.pitch_scale.state(["disabled"])
            self._apply_link()
        else:
            self.pitch_scale.state(["!disabled"])
            self.pitch_lbl.config(text=f"{self.pitch.get():+.1f} st")

    def _preset(self, sp):
        self.link.set(True)
        self.speed.set(sp)
        self._on_speed()
        self._sync_link()

    # --- file ops ---
    def add_files(self):
        paths = filedialog.askopenfilenames(
            title="Choose songs",
            filetypes=[("Audio", " ".join("*" + e for e in AUDIO_EXTS)), ("All files", "*.*")]
        )
        for p in paths:
            if p not in self.files:
                self.files.append(p)
                self.lst.insert("end", os.path.basename(p))
        if paths and not self.out_dir.get():
            self.out_dir.set(os.path.dirname(paths[0]))

    def remove_sel(self):
        for i in reversed(self.lst.curselection()):
            self.lst.delete(i)
            del self.files[i]

    def clear_files(self):
        self.lst.delete(0, "end")
        self.files.clear()

    def pick_out(self):
        d = filedialog.askdirectory(title="Output folder")
        if d:
            self.out_dir.set(d)

    # --- logging ---
    def _log(self, msg):
        self.msgq.put(msg)

    def _drain_log(self):
        try:
            while True:
                msg = self.msgq.get_nowait()
                self.log.config(state="normal")
                self.log.insert("end", msg + "\n")
                self.log.see("end")
                self.log.config(state="disabled")
        except queue.Empty:
            pass
        self.root.after(100, self._drain_log)

    # --- run ---
    def start(self):
        if self._building:
            return
        if not FFMPEG:
            messagebox.showerror(APP_TITLE, "ffmpeg.exe not found.")
            return
        if not self.files:
            messagebox.showinfo(APP_TITLE, "Add some songs first.")
            return
        out = self.out_dir.get().strip()
        if not out:
            messagebox.showinfo(APP_TITLE, "Choose an output folder.")
            return
        os.makedirs(out, exist_ok=True)

        self._building = True
        self.go_btn.config(state="disabled")
        self.prog.config(maximum=len(self.files), value=0)
        t = threading.Thread(target=self._worker, daemon=True)
        t.start()

    def _worker(self):
        speed = self.speed.get()
        semis = self.pitch.get()
        hq = self.hq.get()
        fmt = self.fmt.get()
        suffix = self.suffix.get()
        out = self.out_dir.get().strip()
        ok = 0
        self._log(f"Speed {speed:.0f}% | Pitch {semis:+.1f} st | "
                  f"{'HQ' if hq else 'fast'} | {fmt}")
        for i, f in enumerate(list(self.files), 1):
            name = os.path.basename(f)
            try:
                self._log(f"[{i}/{len(self.files)}] {name} …")
                outp = convert_file(f, out, speed, semis, hq, fmt, suffix)
                self._log(f"    -> {os.path.basename(outp)}")
                ok += 1
            except Exception as e:
                self._log(f"    ! failed: {e}")
            self.root.after(0, lambda v=i: self.prog.config(value=v))
        self._log(f"Done. {ok}/{len(self.files)} converted into {out}")
        self.root.after(0, self._finish)

    def _finish(self):
        self._building = False
        self.go_btn.config(state="normal")
        messagebox.showinfo(APP_TITLE, "Finished. Check your output folder.")


def main():
    root = tk.Tk()
    NightcoreApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
