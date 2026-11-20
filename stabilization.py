"""Output hysteresis: suppress small oscillations without a time-based lag."""
import math

def approach_depth(reference, span):
    """Map relative face scale to a bounded forward offset in metres."""
    if not reference or not span or span <= reference:
        return 0.0
    return -min(.12, max(0., 1-reference/span-.035)*.45)

def smoothing_alpha(error,dt,smoothing,responsive=True):
    tau=.012+smoothing*.25
    if responsive:
        tau=max(.025,tau/(1+abs(error)/2.5))
    elif error>12:
        tau*=.55
    return 1-math.exp(-dt/max(.001,tau))

def stabilize(value, previous, radius):
    if radius <= 0 or previous is None:
        return float(value)
    difference = value - previous
    if abs(difference) <= radius:
        return previous
    return value - math.copysign(radius, difference)


def smoothstep(value, start, end):
    fraction = max(0., min(1., (value-start)/(end-start)))
    return fraction*fraction*(3-2*fraction)


CABIN_SIDE_VIEW = 118.
CABIN_YAW_LIMIT = 150.


class CabinMotion:
    """Blend normal head motion into a wide turn on either side of the cab."""

    def __init__(self):
        self.span = self.reference = None
        self.output = (0., 0., 0., 0.)  # yaw, pitch, depth, lateral

    def recenter(self):
        self.reference = self.span
        self.output = (0., 0., 0., 0.)

    def update(self, yaw, pitch, span, smoothing, dt):
        valid_span = span is not None and math.isfinite(span) and span > .025
        if valid_span:
            if self.span is None:
                self.span = span
            else:
                # Bound isolated jumps from noisy facial landmarks before smoothing.
                measured = self.span * max(.76, min(1.24, span / self.span))
                self.span += (measured-self.span)*(1-math.exp(-dt/.12))
            if self.reference is None:
                self.reference = self.span
        lean = smoothstep(self.span/self.reference, 1.04, 1.16) if valid_span and self.reference else 0.
        heading = abs(yaw)
        turn = smoothstep(heading, 12., 46.)
        assist = lean * turn
        normal = heading * (1. + .65 * smoothstep(heading, 8., 72.))
        wide = normal + max(0., CABIN_SIDE_VIEW - normal) * assist
        target = (math.copysign(min(CABIN_YAW_LIMIT, wide), yaw), pitch,
                  -.12*lean, math.copysign(.24*assist, yaw))
        angle_change = max(abs(target[i]-self.output[i]) for i in range(2))
        angle_tau = .075 + smoothing*.22 / (1 + angle_change/30)
        self.output = tuple(
            previous + max(-rate*dt, min(rate*dt, (desired-previous)*(1-math.exp(-dt/tau))))
            for previous, desired, rate, tau in zip(self.output, target, (420., 310., .55, .55),
                                                     (angle_tau, angle_tau, .16, .16))
        )
        return self.output

    def lost(self, elapsed, dt):
        if elapsed > .95:
            self.span = None
            self.output = (0., 0., 0., 0.)
        elif elapsed > .12:
            self.output = tuple(value*math.exp(-dt/.18) for value in self.output)
        return self.output
