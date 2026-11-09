"""Easing curves + small timeline helpers."""
import math


def clamp01(x):
    return 0.0 if x < 0 else 1.0 if x > 1 else x


def linear(t):
    return t


def smooth(t):  # smoothstep
    return t * t * (3 - 2 * t)


def smoother(t):
    return t * t * t * (t * (t * 6 - 15) + 10)


def in_out_cubic(t):
    return 4 * t ** 3 if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2


def in_out_quint(t):
    return 16 * t ** 5 if t < 0.5 else 1 - (-2 * t + 2) ** 5 / 2


def in_out_sine(t):
    return -(math.cos(math.pi * t) - 1) / 2


def out_cubic(t):
    return 1 - (1 - t) ** 3


def out_quint(t):
    return 1 - (1 - t) ** 5


def out_expo(t):
    return 1.0 if t >= 1 else 1 - 2 ** (-10 * t)


def in_cubic(t):
    return t ** 3


def out_back(t, s=1.70158):
    t -= 1
    return 1 + (s + 1) * t ** 3 + s * t ** 2


def in_out_expo(t):
    if t <= 0:
        return 0.0
    if t >= 1:
        return 1.0
    return 2 ** (20 * t - 10) / 2 if t < 0.5 else (2 - 2 ** (-20 * t + 10)) / 2


def prog(t, t0, t1, ease=linear):
    """Progress 0..1 of time t inside [t0,t1] with easing."""
    if t1 <= t0:
        return 1.0 if t >= t1 else 0.0
    return ease(clamp01((t - t0) / (t1 - t0)))


def window(t, t_in, t_out, fade_in=0.4, fade_out=0.4, ease=smooth):
    """0 -> 1 (fade in starting at t_in) ... 1 -> 0 (fade out ending at t_out)."""
    a = prog(t, t_in, t_in + fade_in, ease)
    b = 1 - prog(t, t_out - fade_out, t_out, ease)
    return min(a, b)


def lerp(a, b, t):
    return a + (b - a) * t
