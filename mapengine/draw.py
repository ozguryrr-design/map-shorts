"""Cairo drawing primitives for map videos."""
import math

import cairo
import numpy as np
from PIL import Image, ImageFilter


def hex2rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


class Frame:
    """Per-frame drawing context: cairo ctx + camera view + screen size."""

    def __init__(self, ctx, surface, view, W, H, t):
        self.ctx, self.surface, self.view, self.W, self.H, self.t = ctx, surface, view, W, H, t
        self.scale = W / view.w

    # ---------------------------------------------------------- transforms
    def to_screen(self, m):
        """mercator (N,2) -> screen (N,2)"""
        v = self.view
        out = np.empty_like(m)
        out[:, 0] = (m[:, 0] - v.cx) * self.scale + self.W / 2
        out[:, 1] = (m[:, 1] - v.cy) * self.scale + self.H / 2
        return out

    def pt(self, mx, my):
        v = self.view
        return (mx - v.cx) * self.scale + self.W / 2, (my - v.cy) * self.scale + self.H / 2

    def screen_rings(self, merc_rings, xform=None, min_px=0.6):
        """Project rings, cull off-screen ones, thin sub-pixel vertices."""
        out = []
        W, H = self.W, self.H
        for r in merc_rings:
            s = self.to_screen(r)
            if xform is not None:
                s = xform(s)
            x0, y0 = s.min(0)
            x1, y1 = s.max(0)
            if x1 < -50 or y1 < -50 or x0 > W + 50 or y0 > H + 50:
                continue
            if (x1 - x0) < 0.8 and (y1 - y0) < 0.8:
                continue
            if len(s) > 64:
                d = np.abs(np.diff(s, axis=0)).sum(1)
                keep = np.ones(len(s), bool)
                acc = np.cumsum(d)
                q = np.floor(acc / min_px)
                keep[1:] = np.diff(np.concatenate([[-1], q])) > 0
                keep[-1] = True
                s = s[keep]
            out.append(s)
        return out

    # ---------------------------------------------------------- paths
    def path(self, rings):
        c = self.ctx
        c.new_path()
        for s in rings:
            c.move_to(*s[0])
            for x, y in s[1:]:
                c.line_to(x, y)
            c.close_path()
        c.set_fill_rule(cairo.FILL_RULE_EVEN_ODD)

    # ---------------------------------------------------------- fills
    def fill_tint(self, rings, color, alpha=1.0, solid=0.45):
        """Colour the satellite texture inside rings (keeps relief visible)."""
        if alpha <= 0 or not rings:
            return
        c = self.ctx
        r, g, b = hex2rgb(color) if isinstance(color, str) else color
        c.save()
        self.path(rings)
        c.clip()
        c.push_group()
        m = c.get_matrix()
        c.identity_matrix()
        c.set_source_surface(self.surface)  # current pixels = texture (device space)
        c.set_matrix(m)
        c.paint()
        c.set_operator(cairo.OPERATOR_HSL_COLOR)
        c.set_source_rgb(r, g, b)
        c.paint()
        c.set_operator(cairo.OPERATOR_OVER)
        c.set_source_rgba(r, g, b, solid)
        c.paint()
        c.pop_group_to_source()
        c.paint_with_alpha(alpha)
        c.restore()

    def fill_solid(self, rings, color, alpha=1.0):
        if alpha <= 0 or not rings:
            return
        r, g, b = hex2rgb(color) if isinstance(color, str) else color
        self.path(rings)
        self.ctx.set_source_rgba(r, g, b, alpha)
        self.ctx.fill()

    def fill_with(self, rings, painter, alpha=1.0, clip_circle=None):
        """Clip to rings and call painter(ctx) (e.g. a flag). Optional circular
        reveal clip_circle=(cx, cy, r)."""
        if alpha <= 0 or not rings:
            return
        c = self.ctx
        c.save()
        self.path(rings)
        c.clip()
        if clip_circle is not None:
            c.new_path()
            c.arc(clip_circle[0], clip_circle[1], max(0.01, clip_circle[2]), 0, 2 * math.pi)
            c.clip()
        c.push_group()
        painter(c)
        c.pop_group_to_source()
        c.paint_with_alpha(alpha)
        c.restore()

    # ---------------------------------------------------------- strokes
    def stroke(self, rings, width=3.0, color=(1, 1, 1), alpha=1.0, progress=1.0, dash=None):
        if alpha <= 0 or progress <= 0 or not rings:
            return
        c = self.ctx
        r, g, b = hex2rgb(color) if isinstance(color, str) else color
        c.set_source_rgba(r, g, b, alpha)
        c.set_line_width(width)
        c.set_line_join(cairo.LINE_JOIN_ROUND)
        c.set_line_cap(cairo.LINE_CAP_ROUND)
        if progress >= 1.0:
            if dash:
                c.set_dash(dash)
            self.path(rings)
            c.stroke()
            c.set_dash([])
            return
        for s in rings:  # draw-on effect, each ring traced simultaneously
            L = float(np.hypot(*np.diff(s, axis=0).T).sum())
            if L < 2:
                continue
            c.new_path()
            c.move_to(*s[0])
            for x, y in s[1:]:
                c.line_to(x, y)
            c.close_path()
            c.set_dash([L * progress, L + 10])
            c.stroke()
        c.set_dash([])

    def glow_stroke(self, rings, width=3.0, color=(1, 1, 1), alpha=1.0, progress=1.0, glow=10, glow_alpha=0.25):
        if alpha <= 0:
            return
        for k, a in ((glow, 0.25), (glow * 0.55, 0.5)):
            self.stroke(rings, width + k, color, alpha * glow_alpha * a, progress)
        self.stroke(rings, width, color, alpha, progress)

    # ---------------------------------------------------------- shadow
    def shadow(self, rings, dx=0, dy=14, blur=14, alpha=0.55, ds=4):
        """Soft drop shadow (rendered at 1/ds resolution, gaussian blurred)."""
        if alpha <= 0 or not rings:
            return
        w, h = self.W // ds + 1, self.H // ds + 1
        m = cairo.ImageSurface(cairo.FORMAT_A8, w, h)
        mc = cairo.Context(m)
        mc.scale(1 / ds, 1 / ds)
        mc.translate(dx, dy)
        mc.new_path()
        for s in rings:
            mc.move_to(*s[0])
            for x, y in s[1:]:
                mc.line_to(x, y)
            mc.close_path()
        mc.set_fill_rule(cairo.FILL_RULE_EVEN_ODD)
        mc.set_source_rgba(0, 0, 0, 1)
        mc.fill()
        m.flush()
        stride = m.get_stride()
        arr = np.frombuffer(m.get_data(), np.uint8).reshape(h, stride)[:, :w]
        im = Image.fromarray(arr.copy(), "L").filter(ImageFilter.GaussianBlur(blur / ds))
        data = bytearray(np.ascontiguousarray(
            np.pad(np.asarray(im), ((0, 0), (0, stride - w)))).tobytes())
        m2 = cairo.ImageSurface.create_for_data(data, cairo.FORMAT_A8, w, h, stride)
        c = self.ctx
        c.save()
        c.scale(ds, ds)
        c.set_source_rgba(0, 0, 0, alpha)
        pat = cairo.SurfacePattern(m2)
        pat.set_filter(cairo.FILTER_BILINEAR)
        c.mask(pat)
        c.restore()

    # ---------------------------------------------------------- grading
    def grade(self, darken=0.18, desat=0.25, vignette=0.55):
        c = self.ctx
        if desat > 0:
            c.save()
            c.set_operator(cairo.OPERATOR_HSL_SATURATION)
            c.set_source_rgba(0.5, 0.5, 0.5, desat)
            c.paint()
            c.restore()
        if darken > 0:
            c.set_source_rgba(0, 0, 0, darken)
            c.paint()

    def vignette(self, strength=0.55):
        c = self.ctx
        W, H = self.W, self.H
        g = cairo.RadialGradient(W / 2, H / 2, min(W, H) * 0.35, W / 2, H / 2, math.hypot(W, H) * 0.62)
        g.add_color_stop_rgba(0, 0, 0, 0, 0)
        g.add_color_stop_rgba(1, 0, 0, 0, strength)
        c.set_source(g)
        c.paint()

    def borders(self, border_list, alpha=0.18, width=1.2):
        """Faint context borders of all countries (from geo.all_borders()).
        Handles unwrapped camera positions by drawing world copies."""
        if alpha <= 0:
            return
        v = self.view
        h = v.w * self.H / self.W
        X0, X1, Y0, Y1 = v.cx - v.w / 2, v.cx + v.w / 2, v.cy - h / 2, v.cy + h / 2
        c = self.ctx
        c.new_path()
        for k in self.world_copies():
            for m, (x0, y0, x1, y1) in border_list:
                if x1 + k < X0 or x0 + k > X1 or y1 < Y0 or y0 > Y1:
                    continue
                s = self.to_screen(m + (k, 0)) if k else self.to_screen(m)
                c.move_to(*s[0])
                for x, y in s[1:]:
                    c.line_to(x, y)
                c.close_path()
        c.set_source_rgba(1, 1, 1, alpha)
        c.set_line_width(width)
        c.set_line_join(cairo.LINE_JOIN_ROUND)
        c.stroke()

    def world_copies(self):
        """Integer world offsets whose copy of [0,1] overlaps the view."""
        v = self.view
        x0, x1 = v.cx - v.w / 2, v.cx + v.w / 2
        return [k for k in range(math.floor(x0) - 1, math.ceil(x1) + 1) if k + 1 > x0 and k < x1]

    def nearest_copy(self, mx):
        """offset k so that mx+k is closest to the camera centre."""
        return round(self.view.cx - mx)

    def graticule(self, alpha=0.15, step=15, width=1.2):
        if alpha <= 0:
            return
        from .geo import merc
        c = self.ctx
        c.set_source_rgba(1, 1, 1, alpha)
        c.set_line_width(width)
        c.set_dash([6, 8])
        for lat in range(-75, 90, step):
            _, my = merc(0, lat)
            _, y = self.pt(0, float(my))
            if -2 < y < self.H + 2:
                c.move_to(0, y)
                c.line_to(self.W, y)
        for lon in range(-180, 180, step):
            mx, _ = merc(lon, 0)
            x, _ = self.pt(float(mx), 0)
            if -2 < x < self.W + 2:
                c.move_to(x, 0)
                c.line_to(x, self.H)
        c.stroke()
        c.set_dash([])


def rings_bbox(rings):
    a = np.concatenate(rings)
    return a[:, 0].min(), a[:, 1].min(), a[:, 0].max(), a[:, 1].max()


def scale_about(cx, cy, k):
    def f(s):
        return (s - (cx, cy)) * k + (cx, cy)
    return f
