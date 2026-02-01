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
    def ease_in_back(t: float) -> float:
        """Ease-in with overshoot (pull back then accelerate)."""
        c1 = 1.70158
        c3 = c1 + 1
        return c3 * t * t * t - c1 * t * t

    @staticmethod
    def ease_out_back(t: float) -> float:
        """Ease-out with overshoot (bounce past target then settle)."""
        c1 = 1.70158
        c3 = c1 + 1
        return 1 + c3 * pow(t - 1, 3) + c1 * pow(t - 1, 2)

    @staticmethod
    def ease_in_out_back(t: float) -> float:
        """Ease-in-out with overshoot on both ends."""
        c1 = 1.70158
        c2 = c1 * 1.525
        if t < 0.5:
            return (pow(2 * t, 2) * ((c2 + 1) * 2 * t - c2)) / 2
        else:
            return (pow(2 * t - 2, 2) * ((c2 + 1) * (t * 2 - 2) + c2) + 2) / 2

    @staticmethod
    def ease_in_elastic(t: float) -> float:
        """Elastic ease-in (reverse spring effect)."""
        if t == 0:
            return 0
        if t == 1:
            return 1
        c4 = (2 * math.pi) / 3
        return -pow(2, 10 * t - 10) * math.sin((t * 10 - 10.75) * c4)

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
    def ease_in_out_elastic(t: float) -> float:
        """Elastic ease-in-out."""
        if t == 0:
            return 0
        if t == 1:
            return 1
        c5 = (2 * math.pi) / 4.5
        if t < 0.5:
            return -(pow(2, 20 * t - 10) * math.sin((20 * t - 11.125) * c5)) / 2
        else:
            return (pow(2, -20 * t + 10) * math.sin((20 * t - 11.125) * c5)) / 2 + 1

    @staticmethod
    def ease_in_bounce(t: float) -> float:
        """Bounce ease-in."""
        return 1 - Easing.ease_out_bounce(1 - t)

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

    @staticmethod
    def ease_in_out_bounce(t: float) -> float:
        """Bounce ease-in-out."""
        if t < 0.5:
            return (1 - Easing.ease_out_bounce(1 - 2 * t)) / 2
        else:
            return (1 + Easing.ease_out_bounce(2 * t - 1)) / 2

    @staticmethod
    def spring(t: float, stiffness: float = 100, damping: float = 10) -> float:
        """Physics-based spring easing."""
        if t == 0:
            return 0
        if t == 1:
            return 1
        # Damped harmonic oscillator approximation
        omega = math.sqrt(stiffness)
        zeta = damping / (2 * omega)
        if zeta < 1:  # Underdamped
            omega_d = omega * math.sqrt(1 - zeta * zeta)
            return 1 - math.exp(-zeta * omega * t) * (
                math.cos(omega_d * t) + (zeta * omega / omega_d) * math.sin(omega_d * t)
            )
        else:  # Critically damped or overdamped
            return 1 - (1 + omega * t) * math.exp(-omega * t)

    @staticmethod
    def bezier(t: float, p1x: float = 0.42, p1y: float = 0.0,
               p2x: float = 0.58, p2y: float = 1.0) -> float:
        """Cubic bezier easing (CSS-style)."""
        # Newton-Raphson iteration to find t for x
        epsilon = 1e-6
        x = t
        for _ in range(8):
            # Calculate x(t) for current t estimate
            x_t = 3 * (1-x)**2 * x * p1x + 3 * (1-x) * x**2 * p2x + x**3
            if abs(x_t - t) < epsilon:
                break
            # Derivative
            dx = 3 * (1-x)**2 * p1x + 6 * (1-x) * x * (p2x - p1x) + 3 * x**2 * (1 - p2x)
            if abs(dx) < epsilon:
                break
            x = x - (x_t - t) / dx
        # Calculate y for the found t
        return 3 * (1-x)**2 * x * p1y + 3 * (1-x) * x**2 * p2y + x**3

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
            'ease_in_back': cls.ease_in_back,
            'ease_out_back': cls.ease_out_back,
            'ease_in_out_back': cls.ease_in_out_back,
            'ease_in_elastic': cls.ease_in_elastic,
            'ease_out_elastic': cls.ease_out_elastic,
            'ease_in_out_elastic': cls.ease_in_out_elastic,
            'ease_in_bounce': cls.ease_in_bounce,
            'ease_out_bounce': cls.ease_out_bounce,
            'ease_in_out_bounce': cls.ease_in_out_bounce,
            'spring': cls.spring,
            'bezier': cls.bezier,
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
