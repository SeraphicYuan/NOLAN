"""
Easing functions for smooth animations.

All functions take a value t in [0, 1] and return a value in [0, 1].
"""

import math
from typing import Callable

EasingFunc = Callable[[float], float]


class Easing:
    """Collection of easing functions for animations."""

    @staticmethod
    def linear(t: float) -> float:
        """Linear interpolation (no easing)."""
        return t

    @staticmethod
    def ease_in_quad(t: float) -> float:
        """Quadratic ease-in (slow start)."""
        return t * t

    @staticmethod
    def ease_out_quad(t: float) -> float:
        """Quadratic ease-out (slow end)."""
        return 1 - (1 - t) * (1 - t)

    @staticmethod
    def ease_in_out_quad(t: float) -> float:
        """Quadratic ease-in-out."""
        if t < 0.5:
            return 2 * t * t
        else:
            return 1 - pow(-2 * t + 2, 2) / 2

    @staticmethod
    def ease_in_cubic(t: float) -> float:
        """Cubic ease-in (slow start)."""
        return t * t * t

    @staticmethod
    def ease_out_cubic(t: float) -> float:
        """Cubic ease-out (slow end). Most common for UI animations."""
        return 1 - pow(1 - t, 3)

    @staticmethod
    def ease_in_out_cubic(t: float) -> float:
        """Cubic ease-in-out. Smooth start and end."""
        if t < 0.5:
            return 4 * t * t * t
        else:
            return 1 - pow(-2 * t + 2, 3) / 2

    @staticmethod
    def ease_in_quart(t: float) -> float:
        """Quartic ease-in."""
        return t * t * t * t

    @staticmethod
    def ease_out_quart(t: float) -> float:
        """Quartic ease-out."""
        return 1 - pow(1 - t, 4)

    @staticmethod
    def ease_in_out_quart(t: float) -> float:
        """Quartic ease-in-out."""
        if t < 0.5:
            return 8 * t * t * t * t
        else:
            return 1 - pow(-2 * t + 2, 4) / 2

    @staticmethod
    def ease_in_expo(t: float) -> float:
        """Exponential ease-in."""
        return 0 if t == 0 else pow(2, 10 * t - 10)

    @staticmethod
    def ease_out_expo(t: float) -> float:
        """Exponential ease-out."""
        return 1 if t == 1 else 1 - pow(2, -10 * t)

    @staticmethod
    def ease_in_out_expo(t: float) -> float:
        """Exponential ease-in-out."""
        if t == 0:
            return 0
        if t == 1:
            return 1
        if t < 0.5:
            return pow(2, 20 * t - 10) / 2
        else:
            return (2 - pow(2, -20 * t + 10)) / 2

    @staticmethod
    def ease_out_back(t: float) -> float:
        """Ease-out with overshoot (bounce past target then settle)."""
        c1 = 1.70158
        c3 = c1 + 1
        return 1 + c3 * pow(t - 1, 3) + c1 * pow(t - 1, 2)

    @staticmethod
    def ease_out_elastic(t: float) -> float:
        """Elastic ease-out (spring effect)."""
        if t == 0:
            return 0
        if t == 1:
            return 1
        c4 = (2 * math.pi) / 3
        return pow(2, -10 * t) * math.sin((t * 10 - 0.75) * c4) + 1

    @staticmethod
    def ease_out_bounce(t: float) -> float:
        """Bounce ease-out."""
        n1 = 7.5625
        d1 = 2.75

        if t < 1 / d1:
            return n1 * t * t
        elif t < 2 / d1:
            t -= 1.5 / d1
            return n1 * t * t + 0.75
        elif t < 2.5 / d1:
            t -= 2.25 / d1
            return n1 * t * t + 0.9375
        else:
            t -= 2.625 / d1
            return n1 * t * t + 0.984375

    @classmethod
    def get(cls, name: str) -> EasingFunc:
        """Get easing function by name."""
        easing_map = {
            'linear': cls.linear,
            'ease_in': cls.ease_in_cubic,
            'ease_out': cls.ease_out_cubic,
            'ease_in_out': cls.ease_in_out_cubic,
            'ease_in_quad': cls.ease_in_quad,
            'ease_out_quad': cls.ease_out_quad,
            'ease_in_out_quad': cls.ease_in_out_quad,
            'ease_in_cubic': cls.ease_in_cubic,
            'ease_out_cubic': cls.ease_out_cubic,
            'ease_in_out_cubic': cls.ease_in_out_cubic,
            'ease_in_quart': cls.ease_in_quart,
            'ease_out_quart': cls.ease_out_quart,
            'ease_in_out_quart': cls.ease_in_out_quart,
            'ease_in_expo': cls.ease_in_expo,
            'ease_out_expo': cls.ease_out_expo,
            'ease_in_out_expo': cls.ease_in_out_expo,
            'ease_out_back': cls.ease_out_back,
            'ease_out_elastic': cls.ease_out_elastic,
            'ease_out_bounce': cls.ease_out_bounce,
        }
        return easing_map.get(name, cls.linear)


def lerp(start: float, end: float, t: float) -> float:
    """Linear interpolation between start and end."""
    return start + (end - start) * t


def lerp_color(
    start: tuple,
    end: tuple,
    t: float
) -> tuple:
    """Interpolate between two RGB/RGBA colors."""
    return tuple(int(lerp(s, e, t)) for s, e in zip(start, end))
