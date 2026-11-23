"""
Impactful audio for the videos, fully free and license-free:
  * music bed   : synthesized cinematic drone + dhol-style pulse + temple-bell notes (D phrygian)
                  -> or a random file from assets/music/ if you add your own epic tracks
  * sfx track   : whoosh + deep boom on every scene change, thud on every internal cut
The final mix (voice EQ/compression, sidechain ducking, loudness) is done by ffmpeg in main.py.
"""
import random
import subprocess
import wave
from pathlib import Path

import numpy as np

SR = 44100


def _write_wav(path, stereo):
    x = np.clip(stereo, -1, 1)
    pcm = (x * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


def _env_exp(n, tau):
    return np.exp(-np.arange(n) / (SR * tau)).astype(np.float32)


def _boom(dur=1.1, f0=120.0, f1=38.0, amp=1.0):
    n = int(SR * dur)
    t = np.arange(n) / SR
    f = f1 + (f0 - f1) * np.exp(-t / 0.12)
    ph = 2 * np.pi * np.cumsum(f) / SR
    sig = np.sin(ph) * _env_exp(n, 0.38)
    rng = np.random.default_rng(1)
    click = rng.standard_normal(n).astype(np.float32) * _env_exp(n, 0.012) * 0.25
    return (sig + click) * amp


def _bandpass_noise(n, lo, hi, seed):
    rng = np.random.default_rng(seed)
    x = rng.standard_normal(n).astype(np.float32)
    X = np.fft.rfft(x)
    fr = np.fft.rfftfreq(n, 1 / SR)
    X[(fr < lo) | (fr > hi)] = 0
    y = np.fft.irfft(X, n).astype(np.float32)
    return y / (np.abs(y).max() + 1e-9)


def _whoosh(dur=0.75, amp=0.8):
    n = int(SR * dur)
    t = np.linspace(0, 1, n, dtype=np.float32)
    env = np.sin(np.pi * np.clip(t, 0, 1) ** 0.65) ** 2
    lo = _bandpass_noise(n, 250, 1800, 3)
    hi = _bandpass_noise(n, 1800, 7000, 4)
    sweep = (1 - t) * lo + t * hi  # dark -> bright, feels like movement
    return sweep * env * amp


def _riser(dur=1.6, amp=0.6):
    n = int(SR * dur)
    t = np.linspace(0, 1, n, dtype=np.float32)
    noise = _bandpass_noise(n, 1200, 9000, 11) * t ** 2.2
    f = 180 + 1300 * t ** 2
    sweep = np.sin(2 * np.pi * np.cumsum(f) / SR).astype(np.float32) * t ** 2.5 * 0.5
    return (noise + sweep) * amp * np.minimum(1, (1 - t) * 14 + 0.0 + (t > 0.97) * 0)


def _place(buf, clip, at, gain=1.0, pan=0.0):
    i = int(at * SR)
    if i >= buf.shape[0]:
        return
    j = min(buf.shape[0], i + clip.shape[0])
    seg = clip[: j - i] * gain
    buf[i:j, 0] += seg * (1 - max(pan, 0))
    buf[i:j, 1] += seg * (1 + min(pan, 0))


def make_sfx(total, scene_starts, cut_times, out_path, energies=None):
    buf = np.zeros((int(total * SR) + SR, 2), np.float32)
    boom_big, boom_small = _boom(1.3, 130, 36, 1.0), _boom(0.6, 170, 60, 0.8)
    wh = _whoosh()
    ris = _riser()
    hit = _boom(2.2, 150, 32, 1.0)
    for k, t in enumerate(scene_starts):
        en = (energies[k] if energies and k < len(energies) else 2)
        if en >= 3 and t > 1.6:
            _place(buf, ris, t - 1.6, 0.55)           # tension riser into the shock scene
        if k == 0:
            _place(buf, hit, 0.0, 0.9)                # opening hit
        _place(buf, wh, max(0.0, t - 0.28), 0.55, pan=0.2 if k % 2 else -0.2)  # whoosh leads into the cut
        _place(buf, boom_big if k % 3 == 0 else boom_small, t, 0.8 if k % 3 == 0 else 0.5)
    for t in cut_times:
        _place(buf, boom_small, t, 0.5)
        _place(buf, wh, max(0.0, t - 0.2), 0.35)
    _write_wav(out_path, buf[: int(total * SR)] * 0.9)


def _intensity(total, scene_starts, energies):
    n = int(total * SR)
    if not energies:
        return np.ones(n, np.float32)
    xs = list(scene_starts) + [total]
    pts_t, pts_v = [], []
    for k, e in enumerate(energies):
        v = {1: 0.45, 2: 0.75, 3: 1.0}.get(int(e), 0.75)
        pts_t += [xs[k] + 0.3, xs[k + 1] - 0.3]
        pts_v += [v, v]
    env = np.interp(np.arange(n) / SR, pts_t, pts_v).astype(np.float32)
    k = int(1.2 * SR)
    return np.convolve(env, np.ones(k, np.float32) / k, mode="same")


def make_music(total, out_path, scene_starts=None, energies=None, seed=7):
    n = int(total * SR)
    inten = _intensity(total, scene_starts, energies)
    t = np.arange(n, dtype=np.float32) / SR
    rng = random.Random(seed)
    L = np.zeros(n, np.float32)
    R = np.zeros(n, np.float32)

    # --- drone: D / Eb (phrygian) swells
    def drone(root, gain_curve):
        out = np.zeros(n, np.float32)
        for mult, g in ((1, 1.0), (1.5, 0.6), (2, 0.55), (3, 0.25)):
            for det in (-0.25, 0.25):
                f = root * mult + det
                for h in range(1, 7):
                    out += np.sin(2 * np.pi * f * h * t + h) * (g / h) * 0.05
        return out * gain_curve

    sec = 12.0
    lfo = 0.6 + 0.4 * np.sin(2 * np.pi * 0.05 * t)
    w_d = 0.5 + 0.5 * np.sin(2 * np.pi * t / (2 * sec))
    d_main = drone(73.42, lfo * w_d)           # D2
    d_tense = drone(77.78, lfo * (1 - w_d))    # Eb2 (b2 tension)
    pad = (d_main + d_tense) * 1.6 * (0.8 + 0.4 * inten)
    L += pad
    R += pad * 0.95

    # --- dhol-style pulse (76 bpm)
    beat = 60 / 76
    thump, ghost = _boom(0.8, 105, 48, 1.0), _boom(0.3, 140, 80, 0.45)
    perc = np.zeros((n + SR, 2), np.float32)
    bar = beat * 4
    for b in range(int(total / bar) + 1):
        t0 = b * bar
        for off, clip, g in ((0, thump, 0.9), (0.75 * beat, ghost, 0.5), (2 * beat, thump, 0.7),
                             (2.5 * beat, ghost, 0.55), (3.5 * beat, ghost, 0.4)):
            _place(perc, clip, t0 + off, g)
    # --- 8th-note ticks that add drive after the intro
    tick = _bandpass_noise(int(0.04 * SR), 5000, 9000, 9) * _env_exp(int(0.04 * SR), 0.01)
    k = 0
    while k * beat / 2 < total:
        tt = k * beat / 2
        if tt > 8:
            _place(perc, tick, tt, 0.18 if k % 2 == 0 else 0.1, pan=0.3 if k % 2 else -0.3)
        k += 1
    L += perc[:n, 0] * (0.45 + 0.75 * inten)
    R += perc[:n, 1] * (0.45 + 0.75 * inten)

    # --- temple-bell notes
    notes = [587.33, 622.25, 698.46, 880.0, 932.33]
    tt = 3.0
    while tt < total - 2:
        f = rng.choice(notes)
        m = int(2.4 * SR)
        tb = np.arange(m, dtype=np.float32) / SR
        bell = (np.sin(2 * np.pi * f * tb) + 0.4 * np.sin(2 * np.pi * f * 2.76 * tb)) * np.exp(-tb / 0.9) * 0.05
        i = int(tt * SR)
        j = min(n, i + m)
        pan = rng.uniform(-0.6, 0.6)
        L[i:j] += bell[: j - i] * (1 - max(pan, 0))
        R[i:j] += bell[: j - i] * (1 + min(pan, 0))
        e = int(0.37 * SR)  # echo
        if i + e < n:
            j2 = min(n, i + e + m)
            L[i + e:j2] += bell[: j2 - i - e] * 0.45
            R[i + e:j2] += bell[: j2 - i - e] * 0.45
        tt += beat * rng.choice((1.5, 2.0, 3.0, 4.0))

    st = np.stack([L, R], 1)
    st /= np.abs(st).max() + 1e-9
    fade_in, fade_out = min(int(1.5 * SR), n // 4), min(int(2.5 * SR), n // 4)
    st[:fade_in] *= np.linspace(0, 1, fade_in)[:, None]
    st[-fade_out:] *= np.linspace(1, 0, fade_out)[:, None]
    _write_wav(out_path, st * 0.6)


def music_from_folder(total, out_path, folder="assets/music"):
    files = [p for p in Path(folder).glob("*") if p.suffix.lower() in (".mp3", ".wav", ".m4a", ".ogg")]
    if not files:
        return False
    f = random.choice(files)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-stream_loop", "-1", "-i", str(f), "-t", f"{total:.2f}",
                    "-af", f"afade=t=in:d=1.5,afade=t=out:st={max(total - 2.5, 0):.2f}:d=2.5,loudnorm=I=-20:TP=-3",
                    "-ar", str(SR), "-ac", "2", str(out_path)], check=True)
    return True


def build_audio_assets(total, scene_starts, cut_times, workdir, music_dir="assets/music", energies=None):
    workdir = Path(workdir)
    bed, sfx = workdir / "bed.wav", workdir / "sfx.wav"
    if not music_from_folder(total, bed, music_dir):
        make_music(total, bed, scene_starts, energies)
    make_sfx(total, scene_starts, cut_times, sfx, energies)
    return bed, sfx
