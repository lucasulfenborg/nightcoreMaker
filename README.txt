NIGHTCORE MAKER
===============

A tiny app that turns song files into nightcore (sped up + pitched up) -
and the reverse (slowed/lowered "daycore") too. Batch-process a whole
folder at once, with a high-quality mode for clean, real-nightcore sound.


HOW TO GET THE .EXE
-------------------
The standalone .exe has to be compiled on your own Windows PC (it bundles
the audio engine so the final app needs nothing installed). It's one click:

  1. Make sure Python is installed (https://www.python.org/downloads/ -
     tick "Add Python to PATH" during install). One-time only.
  2. Double-click  build_exe.bat
  3. Wait. It installs the builder, downloads ffmpeg, and packages everything.
  4. When it finishes you'll have:  dist\NightcoreMaker.exe

That .exe is fully self-contained - move it anywhere, no install needed.

(If you'd rather just run it without building: double-click nightcore.py,
but that path needs Python AND ffmpeg.exe/ffprobe.exe sitting next to it.
The .exe route is the easy one.)


USING IT
--------
  - Add files   : pick one or many songs (mp3, wav, flac, m4a, ...).
  - Speed       : how much faster it plays (130% = classic nightcore).
  - Pitch       : how much higher it sounds, in semitones.
  - Link toggle : ON = authentic "sped-up record" sound. Pitch follows
                  speed automatically (this is true classic nightcore).
                  OFF = move pitch and speed independently.
  - High Quality: ON = uses the soxr resampler for clean sound. Leave on.
  - Presets     : quick 115% / 130% / 150% starting points.
  - Format      : mp3 (320k), wav, or flac.
  - Make Nightcore -> writes new files (originals are never touched).


HOW SPEED AND PITCH RELATE
--------------------------
Doubling the speed raises the pitch by exactly one octave (12 semitones).
So:  pitch in semitones = 12 x log2(speed).
  +15% speed  -> about +2.4 semitones
  +30% speed  -> about +3.9 semitones
  +50% speed  -> about +7.0 semitones
With "Link" on, the app does this math for you - that's the genuine
nightcore effect (same as speeding up a record / Audacity "Change Speed").
Turn Link off if you want, say, a higher pitch without it getting faster.


WHAT "HIGH QUALITY" DOES
------------------------
It uses the SoX (soxr) resampler at high precision when shifting pitch -
the same idea as Audacity's "High Quality" option. It removes the gritty
aliasing you can get from cheap resampling, so the result sounds smooth
and professional. There's no real downside; keep it on.


TIPS
----
  - Classic nightcore sits around 125-135% with Link on.
  - For "daycore" (slowed + lowered), set Speed below 100% with Link on.
  - Batch a whole playlist: add many files, they all use the same settings.
