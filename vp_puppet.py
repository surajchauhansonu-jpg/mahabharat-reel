"""
Flat-vector jointed puppet (front view), drawn with Skia. Everything is code -> the same character
looks identical in every scene, and every joint can be animated.

Local units: origin = feet centre on the ground, y negative = up, character is ~95 units tall.
"""
import math

import skia


# ------------------------------------------------------------------ small helpers
def hex2rgb(h):
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def C(h, a=255):
    r, g, b = hex2rgb(h)
    return skia.ColorSetARGB(int(a), r, g, b)


def mix(h1, h2, t):
    a, b = hex2rgb(h1), hex2rgb(h2)
    return "#%02x%02x%02x" % tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def shade(h, k):
    """k<0 darker, k>0 lighter"""
    return mix(h, "#000000", -k) if k < 0 else mix(h, "#ffffff", k)


def fill(h, a=255):
    return skia.Paint(AntiAlias=True, Color=C(h, a))


def stroke(h, w, a=255, cap=True):
    p = skia.Paint(AntiAlias=True, Color=C(h, a), Style=skia.Paint.kStroke_Style, StrokeWidth=w)
    if cap:
        p.setStrokeCap(skia.Paint.kRound_Cap)
        p.setStrokeJoin(skia.Paint.kRound_Join)
    return p


def vgrad(y0, y1, top, bot, a=255):
    return skia.Paint(AntiAlias=True, Shader=skia.GradientShader.MakeLinear(
        [(0, y0), (0, y1)], [C(top, a), C(bot, a)]))


def ov(c, cx, cy, rx, ry, p):
    c.drawOval(skia.Rect.MakeLTRB(cx - rx, cy - ry, cx + rx, cy + ry), p)


def rr(c, x0, y0, x1, y1, r, p):
    c.drawRoundRect(skia.Rect.MakeLTRB(x0, y0, x1, y1), r, r, p)


def poly(c, pts, p, close=True):
    path = skia.Path()
    path.moveTo(*pts[0])
    for q in pts[1:]:
        path.lineTo(*q)
    if close:
        path.close()
    c.drawPath(path, p)
    return path


def path_of(pts):
    path = skia.Path()
    path.moveTo(*pts[0])
    for q in pts[1:]:
        path.lineTo(*q)
    path.close()
    return path


def line(c, x0, y0, x1, y1, p):
    c.drawLine(x0, y0, x1, y1, p)


# ------------------------------------------------------------------ the puppet
DEFAULT = dict(
    skin="#b9774a", hair="#1b1210", gold="#e0b43a", build=1.0, height=1.0,
    crown="cone", crown_color="#d9a928", beard="none", beard_color="#1b1210",
    top="armor", top_color="#d9a928", bottom="dhoti", bottom_color="#9b1c1f", strip_color="#e0b43a",
    prop="none", heads=1, mark="dot", mark_color="#c8201e", blindfold=False, earrings=True,
    sash="none", sash_color="#ffffff", necklace=True, eye_color="#241a14", brow_color="#1b1210",
)


class Puppet:
    SW, TW = 11.5, 8.0          # half widths at shoulder / waist
    SHY, WY = -61.5, -38.0      # shoulder y, waist y
    L1, L2 = 15.0, 14.0         # upper arm / forearm

    def __init__(self, spec):
        self.s = {**DEFAULT, **spec}

    # ---------------------------------------------------------------- public
    def draw(self, c, x, y, scale, pose, t=0.0, flip=False, shadow=True):
        s = self.s
        k = scale * s["height"]
        c.save()
        c.translate(x, y)
        c.scale(-k if flip else k, k)
        b = s["build"]
        bob = pose.get("bob", 0.0)
        hover = pose.get("hover", 0.0)
        if shadow:
            sh = fill("#000000", 70)
            sh.setMaskFilter(skia.MaskFilter.MakeBlur(skia.kNormal_BlurStyle, 2.2))
            ov(c, 0, 0.6, (16 * b) * (1 - 0.25 * min(hover / 30, 1)), 2.6, sh)
        c.translate(pose.get("dx", 0.0), -hover)
        self._feet(c, pose, b)
        self._lower(c, pose, b, t)
        c.save()
        c.translate(0, bob)
        c.rotate(pose.get("lean", 0.0), 0, self.WY)       # rotate upper body about the waist
        self._back_arm_props(c, pose)
        self._torso(c, b)
        self._arms_and_head(c, pose, b, t)
        c.restore()
        c.restore()

    # ---------------------------------------------------------------- parts
    def _feet(self, c, pose, b):
        sk = self.s["skin"]
        fl, fr = pose.get("foot_l", 0.0), pose.get("foot_r", 0.0)
        for sx, lift in ((-1, fl), (1, fr)):
            ov(c, sx * 4.2 * b, -1.5 - lift, 3.6, 1.7, fill(shade(sk, -0.25)))
            if self.s["bottom"] != "saree":
                line(c, sx * 4.2 * b - 2.4, -3.2 - lift, sx * 4.2 * b + 2.4, -3.2 - lift,
                     stroke(self.s["gold"], 0.9))   # anklet

    def _lower(self, c, pose, b, t):
        s = self.s
        top, hem = self.WY, -5.0
        wtop, whem = self.TW * b + 0.8, (self.TW + 4.5) * b
        sway = pose.get("sway", 0.0)
        col = s["bottom_color"]
        if s["bottom"] == "saree":
            whem = (self.TW + 3.2) * b
        pts = [(-wtop, top), (wtop, top), (whem + sway * 0.5, hem), (-whem + sway, hem)]
        path = path_of(pts)
        c.drawPath(path, vgrad(top, hem, shade(col, 0.12), shade(col, -0.18)))
        c.save()
        c.clipPath(path, skia.ClipOp.kIntersect, True)
        if s["bottom"] == "dhoti":
            rr(c, -2.6 * b, top, 2.6 * b, hem + 4, 0.5, fill(s["strip_color"]))
            poly(c, [(-2.6 * b, hem + 2), (2.6 * b, hem + 2), (0, hem + 7)], fill(s["strip_color"]))
            line(c, -wtop, hem - 0.6, whem, hem - 0.6, stroke(s["gold"], 1.2))
        elif s["bottom"] == "saree":
            for i in range(-3, 4):                      # pleats
                line(c, i * 2.2 * b, top + 6, i * 2.6 * b + sway * 0.3, hem, stroke(shade(col, -0.28), 0.35, 140))
            line(c, -whem, hem - 0.8, whem, hem - 0.8, stroke(s["gold"], 1.8))
        else:
            line(c, -whem, hem - 0.8, whem, hem - 0.8, stroke(s["gold"], 1.2))
        c.restore()
        rr(c, -wtop, top - 1.2, wtop, top + 2.6, 1.0, fill(s["gold"]))          # belt
        ov(c, 0, top + 0.7, 1.5, 1.5, fill(s["mark_color"]))

    def _torso(self, c, b):
        s = self.s
        sw, tw = self.SW * b, self.TW * b
        top, wy = self.SHY - 2.5, self.WY
        path = skia.Path()
        path.moveTo(-sw, top + 3)
        path.quadTo(-sw, top, -sw + 3, top)
        path.lineTo(sw - 3, top)
        path.quadTo(sw, top, sw, top + 3)
        path.lineTo(tw, wy)
        path.lineTo(-tw, wy)
        path.close()
        kind = s["top"]
        base = s["skin"] if kind in ("bare", "robe_open") else s["top_color"]
        c.drawPath(path, vgrad(top, wy, shade(base, 0.10), shade(base, -0.16)))
        c.save()
        c.clipPath(path, skia.ClipOp.kIntersect, True)
        if kind == "armor":
            sc = stroke(shade(base, -0.38), 0.55, 150, cap=False)
            for r_ in range(7):
                for q in range(-3, 4):
                    cx = q * 4.4 * b + (2.2 * b if r_ % 2 else 0)
                    c.drawArc(skia.Rect.MakeLTRB(cx - 2.2, top + 3 + r_ * 3.4, cx + 2.2, top + 7.4 + r_ * 3.4), 0, 180, False, sc)
            ov(c, 0, top + 8, 2.6, 2.6, fill(s["mark_color"]))
            ov(c, 0, top + 8, 2.6, 2.6, stroke(s["gold"], 0.7))
        elif kind == "bare":
            line(c, -sw + 1, top + 2, tw, wy, stroke(s["sash_color"], 1.3, 230))          # sacred thread / sash
            for sx in (-1, 1):
                line(c, sx * 3.2 * b, top + 6, sx * 2.6 * b, top + 14, stroke(shade(s["skin"], -0.3), 0.5, 120))
        elif kind == "saree_top":
            line(c, -sw, top + 2, tw, wy + 1, stroke(s["gold"], 2.4))
        elif kind == "cloth":
            line(c, -sw, top + 3, sw, top + 3, stroke(s["gold"], 1.4))
        elif kind == "robe":
            line(c, 0, top, 0, wy, stroke(shade(base, -0.3), 0.7))
        if s["sash"] != "none":
            poly(c, [(-sw - 1, top + 1), (-sw + 5, top), (tw + 1, wy - 3), (tw - 5, wy - 1)], fill(s["sash_color"], 235))
        c.restore()
        if kind == "armor":
            c.drawPath(path, stroke(shade(base, -0.4), 0.7))
            rr(c, -tw - 0.5, wy - 3.4, tw + 0.5, wy + 0.6, 0.8, fill(s["gold"]))

    def _arm_points(self, side, a, e, b):
        sgn = 1 if side == "R" else -1
        S = (sgn * self.SW * b * 0.93, self.SHY)
        ar, br = math.radians(a), math.radians(a - e)
        u = (sgn * math.sin(ar), math.cos(ar))
        v = (sgn * math.sin(br), math.cos(br))
        E = (S[0] + self.L1 * u[0], S[1] + self.L1 * u[1])
        Wr = (E[0] + self.L2 * v[0], E[1] + self.L2 * v[1])
        Hd = (Wr[0] + 2.4 * v[0], Wr[1] + 2.4 * v[1])
        return S, E, Wr, Hd, math.degrees(math.atan2(v[1], v[0]))

    def _back_arm_props(self, c, pose):
        pass

    def _band(self, c, p0, p1, f, width):
        x, y = p0[0] + (p1[0] - p0[0]) * f, p0[1] + (p1[1] - p0[1]) * f
        dx, dy = p1[0] - p0[0], p1[1] - p0[1]
        n = math.hypot(dx, dy) or 1
        px, py = -dy / n, dx / n
        h = width / 2
        line(c, x - px * h, y - py * h, x + px * h, y + py * h, stroke(self.s["gold"], 1.5, cap=False))

    def _draw_arm(self, c, side, pose, b):
        s = self.s
        a, e = pose.get(f"arm_{side.lower()}", (6.0, 8.0))
        S, E, Wr, Hd, ang = self._arm_points(side, a, e, b)
        sk = s["skin"]
        edge, base = shade(sk, -0.38), shade(sk, 0.04)
        for pa, pb, w in ((S, E, 5.4), (E, Wr, 4.7)):
            line(c, *pa, *pb, stroke(edge, w + 0.9))
        for pa, pb, w in ((S, E, 5.4), (E, Wr, 4.7)):
            line(c, *pa, *pb, stroke(base, w))
        ov(c, *E, 2.9, 2.9, fill(shade(sk, -0.12)))                                 # elbow joint
        self._band(c, S, E, 0.55, 5.6)                                              # armlet
        ov(c, Wr[0], Wr[1], 2.7, 1.5, fill(s["gold"]))                              # bracelet
        ov(c, Hd[0], Hd[1], 2.5, 2.8, stroke(edge, 0.5))
        ov(c, Hd[0], Hd[1], 2.4, 2.7, fill(base))
        if s["top"] == "armor":
            ov(c, S[0], S[1] - 0.5, 5.6, 4.6, fill(s["gold"]))                       # shoulder pad
            ov(c, S[0], S[1] - 0.5, 5.6, 4.6, stroke(shade(s["gold"], -0.4), 0.6))
        elif s["top"] in ("robe", "cloth", "saree_top"):
            ov(c, S[0], S[1], 4.6, 4.0, fill(s["top_color"]))
        return Hd, ang

    def _prop(self, c, hand, ang, pose):
        p = self.s["prop"]
        if p == "none":
            return
        hx, hy = hand
        c.save()
        c.translate(hx, hy)
        c.rotate(pose.get("prop_rot", 0.0))
        wood, gold, steel = "#6b4423", self.s["gold"], "#cfd6dc"
        if p == "mace":
            line(c, 0, 6, 0, -22, stroke(wood, 2.0))
            ov(c, 0, -27, 6.0, 6.0, fill(gold))
            ov(c, 0, -27, 6.0, 6.0, stroke(shade(gold, -0.4), 0.7))
            for q in range(6):
                a = q * math.pi / 3
                ov(c, 4.2 * math.cos(a), -27 + 4.2 * math.sin(a), 0.9, 0.9, fill(shade(gold, -0.35)))
        elif p == "sword":
            poly(c, [(-1.2, -2), (1.2, -2), (1.0, -34), (0, -38), (-1.0, -34)], fill(steel))
            line(c, 0, -3, 0, -35, stroke("#ffffff", 0.5, 160))
            rr(c, -4.5, -3.4, 4.5, -1.2, 0.8, fill(gold))
            rr(c, -1.0, 0, 1.0, 6, 0.5, fill(wood))
        elif p == "bow":
            path = skia.Path()
            path.moveTo(0, 30)
            path.quadTo(-17, 0, 0, -30)
            c.drawPath(path, stroke(wood, 2.0))
            c.drawPath(path, stroke(gold, 0.7))
            line(c, 0, 30, 0, -30, stroke("#e8e0c8", 0.5))
        elif p == "staff":
            line(c, 0, 24, 0, -36, stroke(wood, 1.8))
            ov(c, 0, -38, 2.0, 2.0, fill(gold))
        elif p == "flute":
            c.rotate(-78)
            line(c, -14, 0, 14, 0, stroke("#c9892b", 1.5))
            for q in range(4):
                ov(c, -6 + q * 3.2, 0, 0.45, 0.45, fill("#3a2410"))
        elif p == "dice":
            t = pose.get("t", 0.0)
            for q, off in enumerate((-4, 4)):
                yy = -8 - 4 * abs(math.sin(t * 5 + q))
                c.save()
                c.translate(off, yy)
                c.rotate(25 * math.sin(t * 4 + q))
                rr(c, -2.4, -2.4, 2.4, 2.4, 0.7, fill("#f4efe1"))
                ov(c, -0.7, -0.7, 0.4, 0.4, fill("#222222"))
                ov(c, 0.8, 0.8, 0.4, 0.4, fill("#222222"))
                c.restore()
        elif p == "spear":
            line(c, 0, 20, 0, -44, stroke(wood, 1.6))
            poly(c, [(-2.2, -42), (2.2, -42), (0, -54)], fill(steel))
        c.restore()

    def _head(self, c, pose, t, scale=1.0, cx=0.0, cy=-74.0, main=True):
        s = self.s
        sk = s["skin"]
        c.save()
        c.translate(cx, cy)
        c.scale(scale, scale)
        c.translate(0, -cy)           # local head centre is (0,-74)
        hy = -74.0
        # hair behind head
        if s["crown"] in ("hair", "tiara", "bun", "feather"):
            ov(c, 0, hy - 1.0, 7.3, 8.2, fill(s["hair"]))
        if s["crown"] == "jata":
            for q in range(5):
                ov(c, -6 + q * 3, hy - 7.5 - (q % 2), 3.4, 3.0, fill(s["hair"]))
        # ears + earrings
        for sx in (-1, 1):
            ov(c, sx * 6.6, hy + 0.5, 1.5, 2.2, fill(shade(sk, -0.15)))
            if s["earrings"]:
                ov(c, sx * 6.9, hy + 3.4, 1.35, 1.7, fill(s["gold"]))
        # face
        face = skia.Path()
        face.addOval(skia.Rect.MakeLTRB(-6.2, hy - 7.2, 6.2, hy + 7.4))
        c.drawPath(face, vgrad(hy - 7, hy + 7, shade(sk, 0.08), shade(sk, -0.10)))
        c.drawPath(face, stroke(shade(sk, -0.45), 0.45, 200))
        if main or True:
            self._face(c, pose, t, hy)
        self._crown(c, hy, pose, t)
        c.restore()

    def _face(self, c, pose, t, hy):
        s = self.s
        mouth = float(pose.get("mouth", 0.0))
        brow = float(pose.get("brow", 0.0))                  # + = angry (inner down), - = sad
        look = pose.get("look", (0.0, 0.0))
        blink = pose.get("blink", 0.0)
        eyec = s["eye_color"]
        if s["blindfold"]:
            rr(c, -6.4, hy - 3.4, 6.4, hy + 0.2, 0.5, fill("#f5f1e6"))
            line(c, -6.4, hy - 1.6, 6.4, hy - 1.6, stroke("#d8d2c2", 0.4))
        else:
            for sx in (-1, 1):
                ex, ey = sx * 2.6, hy - 1.3
                if blink > 0.5:
                    line(c, ex - 1.9, ey, ex + 1.9, ey, stroke(eyec, 0.7))
                else:
                    ov(c, ex, ey, 1.55, 0.95, fill("#f7f4ee"))
                    ov(c, ex + look[0] * 0.6, ey + look[1] * 0.35, 0.72, 0.72, fill(eyec))
                    ov(c, ex + look[0] * 0.6 + 0.25, ey - 0.25, 0.2, 0.2, fill("#ffffff"))
                    c.drawArc(skia.Rect.MakeLTRB(ex - 1.7, ey - 1.15, ex + 1.7, ey + 0.8), 190, 160, False, stroke(eyec, 0.45))
                bx0, bx1 = sx * 1.1, sx * 4.2
                by0 = hy - 3.7 + brow * 0.8
                by1 = hy - 4.0 - brow * 0.8
                line(c, bx0, by0, bx1, by1, stroke(s["brow_color"], 0.5))
        if s["beard"] == "long":
            path = skia.Path()
            path.moveTo(-6.2, hy + 0.5)
            path.quadTo(-6.5, hy + 8, -3.0, hy + 16)
            path.quadTo(0, hy + 22, 3.0, hy + 16)
            path.quadTo(6.5, hy + 8, 6.2, hy + 0.5)
            path.quadTo(3.6, hy + 4.6, 0, hy + 5.0)
            path.quadTo(-3.6, hy + 4.6, -6.2, hy + 0.5)
            c.drawPath(path, vgrad(hy, hy + 20, s["beard_color"], shade(s["beard_color"], -0.12)))
        line(c, 0.0, hy - 0.6, 0.5, hy + 1.8, stroke(shade(s["skin"], -0.35), 0.45, 220))      # nose
        my = hy + 4.2
        if mouth < 0.08:
            c.drawArc(skia.Rect.MakeLTRB(-1.8, my - 1.0, 1.8, my + 0.9), 20, 140, False, stroke("#5a2218", 0.55))
        else:
            ov(c, 0, my + 0.2 + mouth * 0.4, 1.7, 0.35 + mouth * 1.6, fill("#4a1712"))
            if mouth > 0.45:
                ov(c, 0, my - 0.4, 1.2, 0.35, fill("#f3efe6"))
        if s["beard"] in ("moustache", "trim", "long"):
            bc = s["beard_color"]
            for sx in (-1, 1):
                path = skia.Path()
                path.moveTo(0, my - 1.4)
                path.quadTo(sx * 2.0, my - 2.0, sx * 3.4, my - 0.5)
                path.quadTo(sx * 2.2, my - 0.5, 0, my - 0.4)
                c.drawPath(path, fill(bc))
        if s["beard"] == "trim":
            path = skia.Path()
            path.moveTo(-6.1, hy + 1.5)
            path.quadTo(-5.5, hy + 8, 0, hy + 8.4)
            path.quadTo(5.5, hy + 8, 6.1, hy + 1.5)
            path.quadTo(4.5, hy + 5.2, 0, hy + 5.8)
            path.quadTo(-4.5, hy + 5.2, -6.1, hy + 1.5)
            c.drawPath(path, fill(s["beard_color"], 235))
        m = s["mark"]
        if m == "dot":
            ov(c, 0, hy - 4.9, 0.7, 0.75, fill(s["mark_color"]))
        elif m == "tilak":
            poly(c, [(-0.45, hy - 6.4), (0.45, hy - 6.4), (0.3, hy - 3.8), (-0.3, hy - 3.8)], fill(s["mark_color"]))
        elif m == "gem":
            ov(c, 0, hy - 5.2, 1.0, 1.2, fill("#59d6e8"))
            ov(c, 0, hy - 5.2, 1.0, 1.2, stroke(s["gold"], 0.4))

    def _crown(self, c, hy, pose, t):
        s = self.s
        kind, cc = s["crown"], s["crown_color"]
        if kind == "cone":
            base_y, top_y = hy - 6.0, hy - 15.2
            path = path_of([(-6.0, base_y), (6.0, base_y), (3.0, top_y), (-3.0, top_y)])
            c.drawPath(path, vgrad(top_y, base_y, shade(cc, 0.18), shade(cc, -0.15)))
            c.drawPath(path, stroke(shade(cc, -0.45), 0.5))
            for q in range(1, 4):
                yy = base_y - q * (base_y - top_y) / 4
                w = 6.0 - (q * 3.0 / 4)
                line(c, -w, yy, w, yy, stroke(shade(cc, -0.35), 0.45))
            rr(c, -6.3, base_y - 1.4, 6.3, base_y + 0.9, 0.5, fill(shade(cc, 0.1)))
            ov(c, 0, base_y - 0.3, 0.8, 0.8, fill(s["mark_color"]))
            ov(c, 0, top_y - 1.3, 1.5, 1.5, fill(cc))
        elif kind == "feather":
            ov(c, 0, hy - 6.4, 6.4, 2.4, fill(cc))
            rr(c, -6.4, hy - 7.4, 6.4, hy - 5.4, 0.8, fill(shade(cc, 0.1)))
            ov(c, 0, hy - 6.4, 0.9, 0.9, fill("#2fb7c9"))
            line(c, 2.0, hy - 7.5, 6.0, hy - 17.0, stroke("#2c6b3a", 0.6))
            ov(c, 6.0, hy - 17.4, 2.0, 3.2, fill("#1f9e6b"))
            ov(c, 6.0, hy - 17.4, 1.1, 1.8, fill("#2554c7"))
            ov(c, 6.0, hy - 17.8, 0.5, 0.8, fill("#e0b43a"))
        elif kind == "hair":
            path = skia.Path()
            path.addOval(skia.Rect.MakeLTRB(-6.7, hy - 9.6, 6.7, hy - 3.9))
            c.drawPath(path, fill(s["hair"]))
            rr(c, -6.6, hy - 6.0, 6.6, hy - 5.2, 0.4, fill(s["gold"]))              # headband
        elif kind == "bun":
            ov(c, 0, hy - 5.0, 6.8, 4.6, fill(s["hair"]))
            ov(c, 0, hy - 11.2, 3.6, 3.4, fill(s["hair"]))
        elif kind == "jata":
            ov(c, 0, hy - 5.6, 6.6, 4.0, fill(s["hair"]))
            ov(c, 0, hy - 12.5, 4.2, 4.4, fill(s["hair"]))
            for q in range(3):
                ov(c, -2.2 + q * 2.2, hy - 12.5, 0.5, 4.2, fill(shade(s["hair"], 0.25), 120))
        elif kind == "tiara":
            path = skia.Path()
            path.addOval(skia.Rect.MakeLTRB(-6.7, hy - 9.2, 6.7, hy - 3.6))
            c.drawPath(path, fill(s["hair"]))
            line(c, -4.6, hy - 6.4, 4.6, hy - 6.4, stroke(cc, 1.0))
            poly(c, [(-1.4, hy - 6.6), (1.4, hy - 6.6), (0, hy - 9.4)], fill(cc))
            ov(c, 0, hy - 7.2, 0.7, 0.7, fill(s["mark_color"]))

    def _arms_and_head(self, c, pose, b, t):
        s = self.s
        # neck
        rr(c, -2.3, self.SHY - 5.5, 2.3, self.SHY + 0.8, 0.6, fill(shade(s["skin"], -0.28)))
        if s["necklace"] and s["top"] in ("bare", "armor", "robe_open"):
            c.drawArc(skia.Rect.MakeLTRB(-5.0, self.SHY - 6.0, 5.0, self.SHY + 3.2), 10, 160, False, stroke(s["gold"], 1.1))
        c.save()
        c.translate(0, self.SHY - 5.5)
        c.rotate(pose.get("head_tilt", 0.0))
        c.translate(0, -(self.SHY - 5.5))
        if s["heads"] > 1:
            for sx in (-1, 1):
                self._head(c, {"mouth": 0.0}, t, scale=0.78, cx=sx * 8.4, cy=-74.0 + 0.0, main=False)
        self._head(c, pose, t)
        c.restore()
        hands = {}
        for side in ("L", "R"):
            hands[side] = self._draw_arm(c, side, pose, b)
        # prop in the right hand (screen right, before flipping)
        Hd, ang = hands["R"]
        self._prop(c, Hd, ang, pose)
