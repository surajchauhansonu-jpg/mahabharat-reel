"""
Live2D-style rig for ONE cut-out character image (RGBA PNG, full body, standing, front view).
No layers needed: soft masks (head / arms / chest / legs / cloth) are derived from the alpha channel and
each region is deformed with small rotations, so there are no holes or ghosting.

Motions: breathing, head nod synced to the voice, arm gestures on emphasis, cloth + hair sway,
idle weight shift, pop-in entrance, soft ground shadow.
"""
import math
from pathlib import Path

import cv2
import numpy as np


def _sig(x):
    return 1.0 / (1.0 + np.exp(-np.clip(x, -30, 30)))


class Actor:
    def __init__(self, png_path, height_px):
        im = cv2.imread(str(png_path), cv2.IMREAD_UNCHANGED)
        if im is None or im.ndim != 3 or im.shape[2] != 4:
            raise ValueError(f"{png_path}: need an RGBA png")
        a = im[..., 3]
        ys, xs = np.where(a > 24)
        im = im[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
        s = height_px / im.shape[0]
        im = cv2.resize(im, (max(8, int(im.shape[1] * s)), height_px), interpolation=cv2.INTER_AREA)
        h, w = im.shape[:2]
        self.pad = int(0.10 * max(h, w))
        # premultiplied alpha -> clean edges when warping
        f = im.astype(np.float32)
        f[..., :3] *= f[..., 3:4] / 255.0
        self.sprite = cv2.copyMakeBorder(f, self.pad, self.pad, self.pad, self.pad, cv2.BORDER_CONSTANT, value=0)
        self.h, self.w = h, w
        self._geometry(im[..., 3])
        H, W = self.sprite.shape[:2]
        self.X, self.Y = np.meshgrid(np.arange(W, dtype=np.float32), np.arange(H, dtype=np.float32))

    # ---- masks ----------------------------------------------------------------
    def _geometry(self, alpha):
        h, w, p = self.h, self.w, self.pad
        m = alpha > 128
        widths = cv2.GaussianBlur(m.sum(1).astype(np.float32).reshape(-1, 1), (1, 0), 3).ravel()
        lo, hi = int(0.10 * h), int(0.30 * h)
        neck = lo + int(np.argmin(widths[lo:hi])) if hi > lo else int(0.17 * h)
        row = np.where(m[neck])[0]
        cx = float(row.mean()) if len(row) else w / 2
        hip = int(0.52 * h)
        ymid = int(0.40 * h)
        r = np.where(m[ymid])[0]
        if len(r):
            # run containing the body centre = torso (arms hanging apart are separate runs)
            runs = np.split(r, np.where(np.diff(r) > 3)[0] + 1)
            run = min(runs, key=lambda q: abs(q.mean() - cx) if not (q[0] <= cx <= q[-1]) else -1)
            tw = (run[-1] - run[0]) / 2
        else:
            tw = 0.2 * w
        tw = float(np.clip(tw, 0.14 * w, 0.30 * w))
        self.neck, self.cx, self.hip, self.tw = neck + p, cx + p, hip + p, tw
        self.feet = h + p
        H, W = self.sprite.shape[:2]
        Y, X = np.mgrid[0:H, 0:W].astype(np.float32)
        sh, sw = 0.012 * h, 0.025 * w
        self.w_head = _sig((self.neck - Y) / sh)
        rows = _sig((Y - (self.neck + 0.03 * h)) / sh) * _sig((self.hip - 0.07 * h - Y) / (1.6 * sh))
        self.w_armL = _sig((self.cx - self.tw - X) / sw) * rows   # arm on the left side of the image
        self.w_armR = _sig((X - self.cx - self.tw) / sw) * rows
        band = _sig((Y - (self.neck + 0.02 * h)) / sh) * _sig((self.hip - Y) / sh)
        self.w_chest = band
        self.w_cloth = np.clip((Y - self.hip) / max(1.0, self.feet - self.hip), 0, 1) ** 1.6
        self.w_legL = _sig((Y - self.hip) / sh) * _sig((self.cx - X) / sw)
        self.w_legR = _sig((Y - self.hip) / sh) * _sig((X - self.cx) / sw)

    # ---- deform ---------------------------------------------------------------
    def _rot(self, wgt, cx, cy, ang):
        c, s = math.cos(ang), math.sin(ang)
        px, py = self.X - cx, self.Y - cy
        return wgt * ((c * px + s * py) - px), wgt * ((-s * px + c * py) - py)

    def pose(self, t, env=0.0, action="talk", energy=2, seed=0):
        """Returns the deformed premultiplied-RGBA sprite for time t (s). env = voice loudness 0..1."""
        e = {1: 0.6, 2: 1.0, 3: 1.6}.get(int(energy), 1.0)
        ph = seed * 1.7
        talk = action in ("talk", "angry", "shock")
        amp = env if talk else 0.0
        h = self.h
        breath = math.sin(2 * math.pi * 0.28 * t + ph)
        head_a = math.radians((1.6 * math.sin(2 * math.pi * 0.21 * t + ph) + 4.0 * amp * math.sin(2 * math.pi * 1.7 * t + ph)) * e)
        if action == "angry":
            head_a += math.radians(-4)
        armL_a = math.radians((2.0 * math.sin(2 * math.pi * 0.31 * t + ph) + 14.0 * amp) * e)
        armR_a = math.radians((-2.0 * math.sin(2 * math.pi * 0.27 * t + ph + 1) - 12.0 * amp * math.sin(2 * math.pi * 0.9 * t + ph)) * e)
        if action == "shock":
            armL_a += math.radians(6)
            armR_a -= math.radians(6)
        dx = np.zeros_like(self.X)
        dy = np.zeros_like(self.X)
        for wgt, cx, cy, ang in (
            (self.w_head, self.cx, self.neck, head_a),
            (self.w_armL, self.cx - self.tw * 0.9, self.neck + 0.05 * h, armL_a),
            (self.w_armR, self.cx + self.tw * 0.9, self.neck + 0.05 * h, armR_a),
        ):
            ddx, ddy = self._rot(wgt, cx, cy, ang)
            dx += ddx
            dy += ddy
        if action == "walk":
            sw_ = math.sin(2 * math.pi * 1.2 * t)
            for wgt, ang in ((self.w_legL, math.radians(6 * sw_)), (self.w_legR, math.radians(-6 * sw_))):
                ddx, ddy = self._rot(wgt, self.cx, self.hip, ang)
                dx += ddx
                dy += ddy
        s_ch = 1 + (0.010 + 0.012 * amp) * breath * e
        dy += self.w_chest * ((self.Y - self.hip) / s_ch - (self.Y - self.hip))
        dx += self.w_chest * ((self.X - self.cx) / s_ch - (self.X - self.cx))
        wind = (0.007 * self.w + 0.004 * self.w * amp) * e
        dx += wind * np.sin(2 * math.pi * 0.8 * t - 5.0 * self.Y / h + ph) * self.w_cloth
        dx += 0.35 * wind * np.sin(2 * math.pi * 1.3 * t + 3.0 * self.Y / h) * (self.w_head * (self.Y < self.neck - 0.03 * h))
        out = cv2.remap(self.sprite, self.X + dx, self.Y + dy, cv2.INTER_LINEAR,
                        borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0))
        return out

    def feet_anchor(self):
        """(x, y) of the point that sits on the ground, in sprite coordinates."""
        return self.cx, self.feet


def composite(frame_f32, sprite_pm, anchor, screen_xy, scale, flip=False, dy=0.0, shadow=True):
    """Alpha-composite a premultiplied RGBA sprite onto a float32 BGR frame. Returns the frame."""
    H, W = frame_f32.shape[:2]
    ax, ay = anchor
    sx, sy = screen_xy
    fl = -1.0 if flip else 1.0
    M = np.array([[fl * scale, 0, sx - fl * scale * ax], [0, scale, sy + dy - scale * ay]], np.float32)
    warped = cv2.warpAffine(sprite_pm, M, (W, H), flags=cv2.INTER_LINEAR,
                            borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0))
    if shadow:
        sh = np.zeros((H, W), np.float32)
        cv2.ellipse(sh, (int(sx), int(sy)), (int(0.42 * scale * ax), int(0.035 * scale * ay)), 0, 0, 360, 0.55, -1)
        sh = cv2.GaussianBlur(sh, (0, 0), 9)
        frame_f32 *= (1 - sh)[..., None]
    a = warped[..., 3:4] / 255.0
    frame_f32 *= (1 - a)
    frame_f32 += warped[..., :3]
    return frame_f32
