"""Jerk/acceleration/speed limited camera recommendations in source coordinates."""
from dataclasses import dataclass
import math


def clamp(x, lo, hi):
    return max(lo, min(hi, x))


@dataclass
class Axis:
    position: float
    velocity: float = 0.
    acceleration: float = 0.

    def advance(self, target, seconds, speed, acceleration, jerk):
        # Fixed small integration steps make behavior independent of input frame rate.
        remaining = seconds
        while remaining > 1e-9:
            dt = min(.025, remaining)
            error = target-self.position
            desired_v = clamp(error*.65, -speed, speed)
            desired_a = clamp((desired_v-self.velocity)*4., -acceleration, acceleration)
            self.acceleration += clamp(desired_a-self.acceleration, -jerk*dt, jerk*dt)
            self.velocity = clamp(self.velocity+self.acceleration*dt, -speed, speed)
            self.position += self.velocity*dt
            remaining -= dt
        return self.position


class CameraMotion:
    def __init__(self, x=.5, y=.5, zoom=1.):
        self.x, self.y, self.zoom = Axis(x), Axis(y), Axis(zoom)
        self.target = [x, y, zoom]
        self.outside_since = None

    def move(self, target, t, dt, cfg):
        dx, dy = abs(target[0]-self.target[0]), abs(target[1]-self.target[1])
        outside = dx > cfg['horizontal_deadzone'] or dy > cfg['vertical_deadzone']
        suppressed = not outside and (dx > 1e-6 or dy > 1e-6)
        if outside:
            if self.outside_since is None:
                self.outside_since = t
            if t-self.outside_since >= cfg['movement_confirm_seconds']:
                self.target[:2] = target[:2]
        else:
            self.outside_since = None
        if abs(target[2]-self.target[2]) > cfg['zoom_deadzone']:
            self.target[2] = target[2]
        before = [self.x.position, self.y.position, self.zoom.position]
        for axis, goal in zip((self.x, self.y), self.target[:2]):
            axis.advance(goal, dt, cfg['max_pan_speed'], cfg['max_pan_acceleration'], cfg['max_pan_jerk'])
        self.zoom.advance(self.target[2], dt, cfg['max_zoom_speed'],
                          cfg['max_zoom_acceleration'], cfg['max_zoom_jerk'])
        after = [self.x.position, self.y.position, self.zoom.position]
        return before, after, suppressed

    def snapshot(self, time):
        return {'time': time, 'center': [self.x.position, self.y.position],
                'zoom': self.zoom.position, 'target': list(self.target),
                'velocity': [self.x.velocity, self.y.velocity, self.zoom.velocity],
                'acceleration': [self.x.acceleration, self.y.acceleration, self.zoom.acceleration]}
