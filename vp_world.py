"""
Vector scene renderer (Skia): backdrops + light + particles + camera + puppet actions.
render_scene() writes a silent MP4 for one scene; voice is muxed later by main.py.
"""
import math
import random
import subprocess

import numpy as np
import skia

from vp_puppet import C, Puppet, fill, line, mix, ov, path_of, poly, rr, shade, stroke, vgrad

W, H, FPS = 720, 1280, 30
GY = int(0.80 * H)          # ground line (feet y)
HORIZON = int(0.62 * H)

PALETTES = {
    "sunrise": dict(sky=("#4a2f26", "#c27a38", "#efb257"), sun="#f6dc92", ground=("#4b2a1b", "#1f110b"),
                    sil="#3a2013", cloud="#7d5236", light="#ffd68a", star=False),
    "day":     dict(sky=("#3f9bd8", "#86c9ee", "#e4f5fb"), sun="#fff3b0", ground=("#6fb55f", "#2f6a3a"),
                    sil="#4f8f6a", cloud="#ffffff", light="#fff6c8", star=False),
    "dusk":    dict(sky=("#33214d", "#b9506b", "#f4a35a"), sun="#ffd27d", ground=("#3a1f3a", "#180d1c"),
                    sil="#2a1630", cloud="#7a3a5e", light="#ffc48a", star=False),
    "night":   dict(sky=("#1a2245", "#39467a", "#6a77a8"), sun="#ece7cf", ground=("#38325f", "#1b1736"),
                    sil="#2a2850", cloud="#2a3357", light="#bcc8ff", star=True),
    "war":     dict(sky=("#160b0b", "#7a2014", "#e2692b"), sun="#ffb347", ground=("#2e1711", "#120907"),
                    sil="#1c0d0a", cloud="#3a1a14", light="#ff9a55", star=False),
    "mystic":  dict(sky=("#0b0e2e", "#2a2f6a", "#6b4fa8"), sun="#c6ecff", ground=("#2a2455", "#0f0c26"),
                    sil="#1c1a44", cloud="#2b2f66", light="#a9c8ff", star=True),
    "forest":  dict(sky=("#0f2e29", "#2a6a52", "#9ad6a8"), sun="#fff3b0", ground=("#1f4a35", "#0c2118"),
                    sil="#133528", cloud="#3c7a62", light="#e9ffb8", star=False),
    "palace":  dict(sky=("#35160f", "#7c3b22", "#cf8740"), sun="#ffd98a", ground=("#4a2616", "#1a0d08"),
                    sil="#2a130b", cloud="#7a4a30", light="#ffd08a", star=False),
}
DEFAULT_PALETTE = {"sunrise_field": "sunrise", "night_sky": "night", "palace_hall": "palace", "battlefield": "war",
                   "forest": "forest", "temple": "dusk", "cosmic": "mystic", "sky_clouds": "day",
                   "fire": "war", "river": "dusk"}


def ease(t):
    t = min(max(t, 0.0), 1.0)
    return t * t * (3 - 2 * t)


def radial(cx, cy, r, c0, c1, a0=255, a1=0):
    return skia.Paint(AntiAlias=True, Shader=skia.GradientShader.MakeRadial(
        (cx, cy), r, [C(c0, a0), C(c1, a1)]))


# ------------------------------------------------------------------ layers
def sky(c, pal):
    top, mid, bot = pal["sky"]
    p = skia.Paint(AntiAlias=True, Shader=skia.GradientShader.MakeLinear(
        [(0, -300), (0, HORIZON + 40)], [C(top), C(mid), C(bot)], [0.0, 0.55, 1.0]))
    c.drawRect(skia.Rect.MakeLTRB(-400, -400, W + 400, HORIZON + 60), p)


def stars(c, t, n=70, seed=3, y1=0.55):
    rnd = random.Random(seed)
    for _ in range(n):
        x, y, r = rnd.uniform(-100, W + 100), rnd.uniform(-100, H * y1), rnd.uniform(0.8, 2.4)
        tw = 0.55 + 0.45 * math.sin(t * rnd.uniform(0.8, 2.4) + rnd.uniform(0, 6))
        ov(c, x, y, r, r, fill("#ffffff", 200 * tw))


def mandala(c, cx, cy, r, t, pal, strength=1.0):
    sun = pal["sun"]
    c.drawCircle(cx, cy, r * 2.6, radial(cx, cy, r * 2.6, pal["light"], pal["light"], 120 * strength, 0))
    c.drawCircle(cx, cy, r * 1.25, radial(cx, cy, r * 1.25, sun, sun, 255 * strength, 0))
    c.save()
    c.translate(cx, cy)
    c.rotate(t * 4.0)
    ring = stroke(pal["light"], 1.6, 150 * strength)
    for rad_, w_ in ((r * 1.9, 1.6), (r * 1.62, 1.0)):
        c.drawCircle(0, 0, rad_, stroke(pal["light"], w_, 150 * strength))
    for q in range(24):
        a = q * math.pi / 12
        line(c, math.cos(a) * r * 1.62, math.sin(a) * r * 1.62, math.cos(a) * r * 1.9, math.sin(a) * r * 1.9,
             stroke(pal["light"], 0.9, 120 * strength))
    for q in range(16):
        a = q * math.pi / 8
        ov(c, math.cos(a) * r * 1.9, math.sin(a) * r * 1.9, 2.4, 2.4, fill(pal["light"], 190 * strength))
    c.rotate(-t * 8.0)
    for q in range(24):                       # short thin rays around the disc
        a_ = q * math.pi / 12
        c.save()
        c.rotate(math.degrees(a_))
        poly(c, [(-r * 0.075, -r * 1.0), (r * 0.075, -r * 1.0), (0, -r * (1.26 if q % 2 == 0 else 1.14))],
             fill(shade(sun, 0.05), 220 * strength))
        c.restore()
    c.restore()
    c.drawCircle(cx, cy, r * 0.95, radial(cx, cy, r, shade(sun, 0.35), sun, 255 * strength, 255 * strength))


def clouds(c, t, pal, y, n, speed, size, alpha=210, seed=1):
    rnd = random.Random(seed)
    span = W + 500
    for _ in range(n):
        x0, yy, s = rnd.uniform(0, span), y + rnd.uniform(-60, 60), size * rnd.uniform(0.7, 1.3)
        x = (x0 + t * speed) % span - 250
        col = shade(pal["cloud"], rnd.uniform(-0.08, 0.08))
        p = fill(col, alpha)
        for dx, dy, rx, ry in ((0, 0, 1.0, 0.45), (-0.7, 0.1, 0.7, 0.35), (0.75, 0.08, 0.8, 0.38), (-0.2, -0.3, 0.6, 0.4), (0.35, -0.22, 0.55, 0.36)):
            ov(c, x + dx * s, yy + dy * s, rx * s, ry * s, p)


def ground(c, pal, y0=HORIZON):
    g0, g1 = pal["ground"]
    c.drawRect(skia.Rect.MakeLTRB(-400, y0, W + 400, H + 400), vgrad(y0, H, g0, g1))
    line(c, -400, y0, W + 400, y0, stroke(shade(pal["light"], 0.1), 1.6, 110))
    c.drawRect(skia.Rect.MakeLTRB(-400, y0, W + 400, y0 + 70), vgrad(y0, y0 + 70, pal["light"], pal["light"], 0))
    c.drawRect(skia.Rect.MakeLTRB(-400, y0, W + 400, y0 + 90),
               skia.Paint(AntiAlias=True, Shader=skia.GradientShader.MakeLinear(
                   [(0, y0), (0, y0 + 90)], [C(pal["light"], 70), C(pal["light"], 0)])))


def rocks(c, pal, y0=HORIZON, seed=5, n=9, hmax=170):
    rnd = random.Random(seed)
    x = -60
    while x < W + 100:
        w = rnd.uniform(60, 140)
        h = rnd.uniform(50, hmax)
        poly(c, [(x, y0 + 2), (x + w * 0.2, y0 - h), (x + w * 0.62, y0 - h * 0.55), (x + w, y0 + 2)], fill(pal["sil"]))
        x += w * rnd.uniform(0.55, 1.1)


def domes(c, pal, y0=HORIZON, seed=2):
    rnd = random.Random(seed)
    for i in range(6):
        x, r = i * 150 - 40 + rnd.uniform(-20, 20), rnd.uniform(70, 110)
        ov(c, x, y0 + 20, r, r * 0.8, fill(pal["sil"], 190))


def pillar(c, x, y_top, y_bot, w, pal, t, banner=True):
    base, cap = "#7a4a22", "#c99a3f"
    rr(c, x - w * 0.62, y_bot - 28, x + w * 0.62, y_bot + 6, 4, fill(shade(base, -0.2)))
    c.drawRect(skia.Rect.MakeLTRB(x - w / 2, y_top + 30, x + w / 2, y_bot - 24),
               skia.Paint(AntiAlias=True, Shader=skia.GradientShader.MakeLinear(
                   [(x - w / 2, 0), (x + w / 2, 0)], [C(shade(base, -0.25)), C(shade(base, 0.12)), C(shade(base, -0.3))], [0, 0.45, 1])))
    rr(c, x - w * 0.78, y_top, x + w * 0.78, y_top + 34, 6, fill(cap))
    rr(c, x - w * 0.66, y_top + 30, x + w * 0.66, y_top + 42, 4, fill(shade(cap, -0.25)))
    if banner:
        sway = math.sin(t * 1.6 + x) * 6
        poly(c, [(x - w / 2 - 2, y_top + 44), (x - w / 2 - 44 + sway, y_top + 80), (x - w / 2 - 38 + sway, y_top + 210),
                 (x - w / 2 - 2, y_top + 190)], fill("#8c1620", 235))
        line(c, x - w / 2 - 2, y_top + 44, x - w / 2 - 2, y_top + 190, stroke("#e0b43a", 2))


def trees(c, pal, seed, y0, depth, t):
    rnd = random.Random(seed)
    x = -80
    while x < W + 100:
        h = rnd.uniform(220, 420) * depth
        w = rnd.uniform(26, 44) * depth
        col = shade(pal["sil"], 0.04 * (1 - depth))
        rr(c, x - w / 2, y0 - h, x + w / 2, y0 + 4, 5, fill(col))
        for _ in range(4):
            ov(c, x + rnd.uniform(-70, 70) * depth + math.sin(t * 0.7 + x) * 3, y0 - h + rnd.uniform(-20, 40),
               rnd.uniform(60, 110) * depth, rnd.uniform(50, 80) * depth, fill(col))
        x += rnd.uniform(95, 170) * depth + 40


def temple(c, pal, cx, y0, s, t):
    col = pal["sil"]
    for k in range(7):
        w = (150 - k * 17) * s
        rr(c, cx - w / 2, y0 - (k + 1) * 34 * s, cx + w / 2, y0 - k * 34 * s, 4 * s, fill(shade(col, 0.025 * k)))
    ov(c, cx, y0 - 7 * 34 * s - 8 * s, 20 * s, 15 * s, fill(col))
    line(c, cx, y0 - 7 * 34 * s - 20 * s, cx, y0 - 7 * 34 * s - 62 * s, stroke(col, 3))
    sway = math.sin(t * 2.2) * 5
    poly(c, [(cx, y0 - 7 * 34 * s - 62 * s), (cx + 34 * s + sway, y0 - 7 * 34 * s - 54 * s), (cx, y0 - 7 * 34 * s - 46 * s)], fill("#e8742a"))
    for k in range(5):
        rr(c, cx - (90 + k * 24) * s, y0 - 2 - k * 10 * s, cx + (90 + k * 24) * s, y0 + 2 + k * 3, 2, fill(shade(col, -0.05)))


def army(c, pal, y0, seed=4):
    rnd = random.Random(seed)
    for i in range(34):
        x = rnd.uniform(-40, W + 40)
        s = rnd.uniform(0.8, 1.5)
        col = shade(pal["sil"], 0.05)
        rr(c, x - 4 * s, y0 - 22 * s, x + 4 * s, y0, 2, fill(col))
        ov(c, x, y0 - 26 * s, 4 * s, 4 * s, fill(col))
        line(c, x + 7 * s, y0 - 40 * s, x + 7 * s, y0, stroke(col, 1.2))
        if i % 3 == 0:
            poly(c, [(x + 7 * s, y0 - 40 * s), (x + 17 * s, y0 - 36 * s), (x + 7 * s, y0 - 32 * s)], fill("#a3261c", 220))


def flames(c, t, y0, pal, n=14):
    for i in range(n):
        x = -30 + i * (W + 60) / (n - 1)
        h = 90 + 70 * (0.5 + 0.5 * math.sin(t * 5 + i * 1.7)) + (i % 3) * 26
        w = 48
        path = skia.Path()
        path.moveTo(x - w, y0 + 40)
        path.quadTo(x - w * 0.4, y0 - h * 0.45 + math.sin(t * 7 + i) * 8, x + math.sin(t * 6 + i) * 10, y0 - h)
        path.quadTo(x + w * 0.5, y0 - h * 0.4, x + w, y0 + 40)
        path.close()
        c.drawPath(path, vgrad(y0 - h, y0 + 40, "#ffd266", "#d8401a", 235))
        ov(c, x, y0 + 4, w * 0.4, h * 0.34, fill("#fff2b3", 190))


def earth(c, cx, cy, r, t):
    c.drawCircle(cx, cy, r * 1.3, radial(cx, cy, r * 1.3, "#6ac2ff", "#6ac2ff", 110, 0))
    c.drawCircle(cx, cy, r, vgrad(cy - r, cy + r, "#4d9fe0", "#1f4f93"))
    c.save()
    c.clipPath(skia.Path().addCircle(cx, cy, r), skia.ClipOp.kIntersect, True)
    off = (t * 6) % (r * 2)
    for bx, by, rx, ry in ((-0.3, -0.2, 0.4, 0.28), (0.4, 0.2, 0.34, 0.4), (-0.6, 0.45, 0.3, 0.2), (0.05, -0.55, 0.25, 0.18)):
        x = cx + bx * r + off - r
        for k in (-1, 0, 1):
            ov(c, x + k * 2 * r, cy + by * r, rx * r, ry * r, fill("#3f9a63", 235))
    c.restore()
    c.drawCircle(cx, cy, r, stroke("#bfe6ff", 2, 160))


# ------------------------------------------------------------------ backdrops
def backdrop(c, kind, pal, t, cam, halo, seed):
    px, py = cam[0] - W / 2, cam[1] - H / 2
    def layer(f):
        c.save()
        c.translate(px * f, py * f * 0.6)
    def end():
        c.restore()

    layer(0.88)
    sky(c, pal)
    if pal["star"]:
        stars(c, t, seed=seed)
    sunx, suny = W * 0.5, H * 0.285
    if halo or kind in ("sunrise_field", "night_sky", "cosmic", "palace_hall", "temple"):
        mandala(c, sunx, suny, 86 if kind != "cosmic" else 70, t, pal, 1.0 if halo else 0.8)
    clouds(c, t, pal, H * 0.10, 5, 6, 150, 200, seed)
    if kind in ("sunrise_field", "night_sky", "river", "battlefield", "temple"):
        clouds(c, t, pal, H * 0.50, 4, 9, 120, 140, seed + 9)
    end()

    layer(0.6)
    if kind == "sunrise_field":
        rocks(c, pal, seed=seed)
    elif kind == "night_sky":
        domes(c, pal, seed=seed)
    elif kind == "battlefield":
        rocks(c, pal, seed=seed, hmax=110)
        army(c, pal, HORIZON + 8, seed)
    elif kind in ("forest",):
        trees(c, pal, seed, HORIZON + 10, 0.7, t)
    elif kind == "temple":
        temple(c, pal, W * 0.5, HORIZON + 4, 1.25, t)
        domes(c, pal, seed=seed)
    elif kind == "river":
        rocks(c, pal, seed=seed, hmax=90)
    elif kind == "cosmic":
        earth(c, W * 0.5, H * 0.60, 120, t)
    end()

    layer(0.25)
    if kind == "palace_hall":
        c.drawRect(skia.Rect.MakeLTRB(-400, -300, W + 400, HORIZON + 40), fill(shade(pal["sky"][0], -0.2), 120))
        pillar(c, 70, 60, HORIZON + 40, 70, pal, t)
        pillar(c, W - 70, 60, HORIZON + 40, 70, pal, t)
        c.drawCircle(W / 2, H * 0.30, 190, stroke("#c99a3f", 6, 180))
    if kind != "cosmic":
        ground(c, pal)
    else:
        c.drawRect(skia.Rect.MakeLTRB(-400, HORIZON, W + 400, H + 400), vgrad(HORIZON, H, "#171a45", "#0a0b25"))
    end()

    layer(0.0)
    if kind == "forest":
        trees(c, pal, seed + 3, H * 0.9, 1.15, t)
    if kind == "battlefield":
        for i, x in enumerate((60, W - 80)):
            line(c, x, GY - 330, x, GY + 20, stroke("#3a2418", 4))
            sway = math.sin(t * 3 + i) * 10
            poly(c, [(x, GY - 330), (x + 80 + sway, GY - 312), (x + 66 + sway, GY - 280), (x, GY - 270)], fill("#b3281d", 235))
    if kind == "fire":
        flames(c, t, GY - 10, pal)
    if kind == "river":
        for i in range(10):
            y = HORIZON + 30 + i * 22
            w = 80 + i * 14
            line(c, ((t * 20 + i * 90) % (W + 200)) - 100, y, ((t * 20 + i * 90) % (W + 200)) - 100 + w, y,
                 stroke(pal["light"], 2, 110))
    end()


def rays(c, t, pal, cx, cy, strength=1.0):
    c.save()
    c.translate(cx, cy)
    c.rotate(t * 3)
    for q in range(9):
        c.save()
        c.rotate(q * 40)
        path = skia.Path()
        path.moveTo(0, 0)
        path.lineTo(-46, -1700)
        path.lineTo(46, -1700)
        path.close()
        p = skia.Paint(AntiAlias=True, Shader=skia.GradientShader.MakeLinear(
            [(0, 0), (0, -1100)], [C(pal["light"], 26 * strength), C(pal["light"], 0)]))
        c.drawPath(path, p)
        c.restore()
    c.restore()


def particles(c, t, kind, pal, seed=1):
    rnd = random.Random(seed)
    n = 70 if kind in ("dust", "stars") else 55
    for i in range(n):
        x0, y0, s, sp, ph = rnd.uniform(0, W), rnd.uniform(0, H), rnd.uniform(1.2, 3.6), rnd.uniform(14, 50), rnd.uniform(0, 6.28)
        if kind == "embers":
            y = (y0 - t * sp * 1.6) % (H + 40) - 20
            x = x0 + math.sin(t * 1.2 + ph) * 22
            a = 200 * (0.5 + 0.5 * math.sin(t * 5 + ph))
            ov(c, x, y, s, s, fill("#ffb347", a))
        elif kind == "petals":
            y = (y0 + t * sp) % (H + 40) - 20
            x = x0 + math.sin(t * 0.9 + ph) * 40
            c.save(); c.translate(x, y); c.rotate(t * 90 + ph * 50)
            ov(c, 0, 0, s * 2.4, s * 1.2, fill("#ff9bb0", 210)); c.restore()
        elif kind == "stars":
            ov(c, x0, (y0 * 0.7), s * 0.5, s * 0.5, fill("#ffffff", 200 * (0.5 + 0.5 * math.sin(t * 2 + ph))))
        else:   # dust motes
            y = (y0 - t * sp * 0.5) % (H + 40) - 20
            x = x0 + math.sin(t * 0.6 + ph) * 16
            ov(c, x, y, s * 0.7, s * 0.7, fill(pal["light"], 130 * (0.5 + 0.5 * math.sin(t * 1.5 + ph))))


# ------------------------------------------------------------------ actions
def _blink(t, k):
    ph = (t + k * 0.9) % 3.4
    return 1.0 if ph < 0.12 else 0.0


def pose_for(action, t, env, energy, k=0, speaker=True):
    e = {1: 0.7, 2: 1.0, 3: 1.5}.get(int(energy), 1.0)
    br = math.sin(2 * math.pi * 0.3 * t + k)
    P = dict(bob=0.35 * br, lean=0.0, head_tilt=0.8 * math.sin(2 * math.pi * 0.2 * t + k), mouth=0.0, brow=0.0,
             look=(0.0, 0.0), blink=_blink(t, k), arm_l=(6 + 1.5 * br, 8.0), arm_r=(6 - 1.5 * br, 8.0),
             foot_l=0.0, foot_r=0.0, sway=1.0 * math.sin(2 * math.pi * 0.5 * t + k), hover=0.0, dx=0.0,
             prop_rot=0.0, t=t)
    ev = env if speaker else 0.0
    g = 0.5 + 0.5 * math.sin(2 * math.pi * 0.85 * t + k * 1.3)
    if action == "talk":
        P["mouth"] = min(1.0, ev ** 0.8 * 1.1)
        P["arm_r"] = (14 + 42 * g * ev * e, 22 + 60 * g * ev * e)
        P["arm_l"] = (8 + 10 * ev, 12 + 18 * ev * (1 - g))
        P["head_tilt"] += 2.4 * math.sin(2 * math.pi * 1.5 * t) * ev * e
        P["bob"] += 0.6 * ev
        P["look"] = (0.2 * math.sin(t * 0.7), 0.0)
    elif action == "listen":
        P["head_tilt"] += 2.2 * math.sin(2 * math.pi * 0.55 * t + k)
        P["look"] = (-0.5, 0.0)
    elif action == "namaste":
        P["arm_l"] = P["arm_r"] = (12.0, 104.0 + 2 * br)
        P["head_tilt"] = -3.0
        P["mouth"] = min(1.0, ev ** 0.8)
    elif action == "bow":
        P["arm_l"] = P["arm_r"] = (12.0, 104.0)
        P["lean"] = 9 * (0.5 + 0.5 * math.sin(2 * math.pi * 0.35 * t - 1.2))
        P["head_tilt"] = -6
    elif action == "pray":
        P["arm_l"] = P["arm_r"] = (14.0, 118.0)
        P["head_tilt"] = -4.0
        P["blink"] = 1.0
        P["mouth"] = min(1.0, ev ** 0.8 * 0.7)
    elif action == "point":
        P["arm_r"] = (80 + 4 * math.sin(2 * math.pi * 0.8 * t), 6.0)
        P["mouth"] = min(1.0, ev ** 0.8)
        P["lean"] = 2.5
        P["brow"] = 0.2
    elif action == "raise":
        P["arm_r"] = (160 + 5 * math.sin(2 * math.pi * 0.9 * t), 12.0)
        P["arm_l"] = (145 + 6 * math.sin(2 * math.pi * 0.9 * t + 1), 14.0)
        P["mouth"] = min(1.0, ev ** 0.8)
        P["bob"] -= 0.6
        P["brow"] = 0.3
    elif action == "angry":
        P["brow"] = 0.95
        P["arm_l"] = (22, 74)
        P["arm_r"] = (24, 78)
        P["lean"] = 4 + 2.5 * math.sin(2 * math.pi * 3 * t) * ev * e
        P["head_tilt"] = 3.5 * math.sin(2 * math.pi * 2.6 * t) * ev * e
        P["mouth"] = min(1.0, ev ** 0.8 * 1.1)
        P["bob"] += 0.5 * math.sin(2 * math.pi * 3 * t) * ev
    elif action == "sad":
        P["head_tilt"] = -8.0
        P["lean"] = 3.0
        P["bob"] = -0.9 + 0.3 * br
        P["brow"] = -0.9
        P["look"] = (0.0, 0.9)
        P["arm_l"] = (4.0, 6.0)
        P["arm_r"] = (4.0, 6.0)
        P["mouth"] = min(1.0, ev ** 0.8 * 0.8)
    elif action == "shock":
        P["dx"] = -4 * ease(t / 0.25)
        P["arm_l"] = (40.0, 28.0)
        P["arm_r"] = (42.0, 26.0)
        P["mouth"] = 0.95 if env < 0.2 else min(1.0, 0.5 + ev)
        P["brow"] = -0.7
        P["head_tilt"] = 1.2 * math.sin(2 * math.pi * 9 * t)
        P["lean"] = -4.0
    elif action == "walk":
        s = math.sin(2 * math.pi * 1.35 * t)
        P["foot_l"], P["foot_r"] = 3.2 * max(0.0, s), 3.2 * max(0.0, -s)
        P["bob"] = 0.9 * abs(s) - 0.3
        P["arm_l"] = (6 + 16 * s, 10.0)
        P["arm_r"] = (6 - 16 * s, 10.0)
        P["lean"] = 2.0
    elif action == "fight":
        s = math.sin(2 * math.pi * 1.3 * t)
        P["arm_r"] = (85 + 55 * s, 40 - 25 * s)
        P["arm_l"] = (30, 70)
        P["prop_rot"] = -30 + 40 * s
        P["lean"] = 5 + 4 * s
        P["brow"] = 0.8
        P["mouth"] = min(1.0, ev ** 0.8)
        P["foot_l"] = 2.5 * max(0, s)
    elif action == "float":
        P["hover"] = 22 + 4 * math.sin(2 * math.pi * 0.5 * t)
        P["arm_l"] = (34 + 3 * br, 22.0)
        P["arm_r"] = (34 - 3 * br, 22.0)
        P["mouth"] = min(1.0, ev ** 0.8)
    elif action == "laugh":
        P["mouth"] = 0.5 + 0.5 * abs(math.sin(2 * math.pi * 4.5 * t))
        P["lean"] = -4 + 2 * math.sin(2 * math.pi * 4.5 * t)
        P["bob"] += 0.7 * abs(math.sin(2 * math.pi * 4.5 * t))
        P["arm_l"] = (10, 40)
    else:   # idle
        pass
    return P


# ------------------------------------------------------------------ camera
def plan_cam(idx, dur, energy, focus_x):
    kinds = ["push", "pull", "pan_l", "pan_r", "rise", "push"]
    k = kinds[idx % len(kinds)]
    shots = []
    if dur >= 4.8:
        cut = dur * (0.45 + 0.1 * ((idx * 7) % 3) / 2)
        shots.append((0.0, cut, k, 0))
        shots.append((cut, dur, "close", 1))
    else:
        shots.append((0.0, dur, k, 0))
    return shots


def cam_at(kind, p, focus_x, focus_y, e):
    cx, cy, z = W / 2, H * 0.52, 1.0
    p = ease(p)
    if kind == "push":
        z, cx, cy = 1.0 + 0.16 * p, W / 2 + (focus_x - W / 2) * 0.35 * p, H * 0.52 + (focus_y - H * 0.52) * 0.25 * p
    elif kind == "pull":
        z, cx = 1.18 - 0.16 * p, W / 2
    elif kind == "pan_l":
        z, cx = 1.10, W / 2 + 46 - 92 * p
    elif kind == "pan_r":
        z, cx = 1.10, W / 2 - 46 + 92 * p
    elif kind == "rise":
        z, cy = 1.10, H * 0.62 - 0.17 * H * p
    elif kind == "close":
        z = 1.42 + 0.10 * p
        cx, cy = W / 2 + (focus_x - W / 2) * 0.95, focus_y
    return cx, cy, z


# ------------------------------------------------------------------ render
POSX = {"far_left": 0.16, "left": 0.28, "center": 0.5, "right": 0.72, "far_right": 0.84}


def render_scene(scene, dur, env, out_path, idx, cast, energy=2):
    """scene: dict(backdrop, palette, actors=[{who, at, face, action, prop?, move_to?}], speaker, halo, rays,
    particles). cast: name -> Puppet. Returns time of the internal cut or None."""
    bd = scene.get("backdrop", "sunrise_field")
    pal = PALETTES.get(scene.get("palette") or DEFAULT_PALETTE.get(bd, "dusk"), PALETTES["dusk"])
    actors = (scene.get("actors") or [])[:3]
    n_act = max(1, len(actors))
    base_scale = {1: 5.5, 2: 4.7, 3: 3.9}[min(n_act, 3)]
    speaker = scene.get("speaker", 0)
    rnd = random.Random(40 + idx)
    seed = rnd.randint(1, 999)

    items = []
    for i, a in enumerate(actors):
        pup = cast.get(a.get("who"))
        if pup is None:
            continue
        at = a.get("at") or (("left", "right", "center")[i] if n_act > 1 else "center")
        fx = POSX.get(at, 0.5)
        face_left = (a.get("face") == "left") or (a.get("face") is None and fx > 0.55)
        items.append(dict(pup=pup, x=fx * W, flip=face_left, action=a.get("action", "talk"), i=i,
                          move_to=POSX.get(a.get("move_to")) if a.get("move_to") else None,
                          prop=a.get("prop"), who=a.get("who")))
    n = max(2, int(math.ceil(dur * FPS)))
    shots = plan_cam(idx, dur, energy, W / 2)
    fx_main = items[min(speaker, len(items) - 1)]["x"] if items else W / 2
    focus_y = GY - 0.19 * H

    surf = skia.Surface(W, H)
    cv = surf.getCanvas()
    p = subprocess.Popen(
        ["ffmpeg", "-y", "-f", "rawvideo", "-pix_fmt", "bgra", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-pix_fmt", "yuv420p", str(out_path)],
        stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
    shake = {1: 0.5, 2: 1.0, 3: 2.2}.get(int(energy), 1.0)
    for f in range(n):
        t = f / FPS
        ev = float(env[min(f, len(env) - 1)]) if env is not None and len(env) else 0.0
        sh = shots[-1]
        for cand in shots:
            if t < cand[1]:
                sh = cand
                break
        pr = (t - sh[0]) / max(sh[1] - sh[0], 1e-3)
        cx, cy, z = cam_at(sh[2], pr, fx_main, focus_y, energy)
        z *= 1 + 0.07 * math.exp(-(t - sh[0]) / 0.14) + 0.006 * ev * energy       # punch at every shot start + voice pulse
        cx += shake * (1.3 * math.sin(2 * math.pi * 1.1 * t) + 0.6 * math.sin(2 * math.pi * 2.7 * t + 1))
        cy += shake * (1.0 * math.sin(2 * math.pi * 0.9 * t + 2) + 0.5 * math.sin(2 * math.pi * 3.1 * t))

        cv.save()
        cv.translate(W / 2, H / 2)
        cv.scale(z, z)
        cv.translate(-cx, -cy)
        backdrop(cv, bd, pal, t, (cx, cy), scene.get("halo", False), seed)
        if scene.get("rays", True):
            rays(cv, t, pal, W * 0.5, H * 0.285, 0.9)
        # soft light pool behind actors
        for it in items:
            cv.drawCircle(it["x"], GY - 200, 260, radial(it["x"], GY - 200, 260, pal["light"], pal["light"], 55, 0))
        for it in sorted(items, key=lambda q: q["i"]):
            x = it["x"]
            if it["move_to"] is not None:
                x = it["x"] + (it["move_to"] * W - it["x"]) * ease(t / max(dur, 0.1))
            tt = t - 0.14 * it["i"]
            pop = ease(tt / 0.45)
            over = 1 + 0.06 * math.sin(math.pi * min(max(tt, 0) / 0.45, 1))
            action = it["action"]
            if len(items) > 1 and it["i"] != speaker and action == "talk":
                action = "listen"
            pose = pose_for(action, t, ev, energy, k=it["i"], speaker=(it["i"] == speaker))
            if it["prop"]:
                it["pup"].s["prop"] = it["prop"]
            it["pup"].draw(cv, x, GY + (1 - pop) * 36, base_scale * (0.9 + 0.1 * pop) * over, pose, t=t, flip=it["flip"])
        if scene.get("particles", "dust") not in (None, "none", ""):
            particles(cv, t, scene.get("particles", "dust"), pal, seed)
        cv.restore()

        # screen-space: vignette + flash on shot starts
        cv.drawRect(skia.Rect.MakeLTRB(0, 0, W, H), skia.Paint(Shader=skia.GradientShader.MakeRadial(
            (W / 2, H * 0.5), H * 0.78, [C("#000000", 0), C("#000000", 120)], [0.55, 1.0])))
        for cand in shots:
            lt = t - cand[0]
            if 0 <= lt < 0.10:
                cv.drawRect(skia.Rect.MakeLTRB(0, 0, W, H), fill("#fff4d6", 110 * (1 - lt / 0.10)))
        arr = surf.makeImageSnapshot().toarray(colorType=skia.kBGRA_8888_ColorType)
        p.stdin.write(arr.tobytes())
    p.stdin.close()
    p.wait()
    return shots[0][1] if len(shots) > 1 else None


BACKDROPS = ["sunrise_field", "night_sky", "palace_hall", "battlefield", "forest", "temple", "cosmic", "sky_clouds", "fire", "river"]
ACTIONS = ["talk", "listen", "idle", "namaste", "bow", "pray", "point", "raise", "angry", "sad", "shock", "walk", "fight", "float", "laugh"]
PROPS = ["none", "bow", "mace", "sword", "staff", "flute", "dice", "spear"]
PARTICLES = ["dust", "embers", "petals", "stars", "none"]


def clean_scene(sc, cast):
    """Make LLM output safe: unknown values fall back to defaults, names matched case-insensitively."""
    by_lower = {k.lower(): k for k in cast}
    out = dict(sc)
    bd = str(sc.get("backdrop", "sunrise_field")).lower().strip()
    out["backdrop"] = bd if bd in BACKDROPS else "sunrise_field"
    pal = str(sc.get("palette", "")).lower().strip()
    out["palette"] = pal if pal in PALETTES else DEFAULT_PALETTE[out["backdrop"]]
    out["halo"] = bool(sc.get("halo", False))
    prt = str(sc.get("particles", "dust")).lower().strip()
    out["particles"] = prt if prt in PARTICLES else "dust"
    acts = []
    for a in (sc.get("actors") or [])[:3]:
        who = by_lower.get(str(a.get("who", a.get("name", ""))).lower().strip())
        if not who:
            continue
        act = str(a.get("action", "talk")).lower().strip()
        prop = str(a.get("prop", "")).lower().strip()
        acts.append(dict(who=who, at=a.get("at") if a.get("at") in POSX else None,
                         face=a.get("face") if a.get("face") in ("left", "right") else None,
                         action=act if act in ACTIONS else "talk",
                         prop=prop if prop in PROPS and prop != "none" else None,
                         move_to=a.get("move_to") if a.get("move_to") in POSX else None))
    out["actors"] = acts
    try:
        sp = int(sc.get("speaker", 0))
    except (TypeError, ValueError):
        sp = 0
    out["speaker"] = min(max(sp, 0), max(len(acts) - 1, 0))
    return out
