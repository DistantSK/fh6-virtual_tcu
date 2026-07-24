from collections import deque

from virtual_tcu.telemetry.model import Telemetry


class RevLimiterDetector:
    """Learn the real fuel-cut RPM without trusting a shift-created plateau."""

    MIN_THROTTLE = 0.92
    POST_DOWNSHIFT_IGNORE_S = 0.6
    POST_UPSHIFT_IGNORE_S = 0.8
    WINDOW = 24
    STABLE_FRAMES = 18
    CANDIDATE_STABLE_FRAMES = 4
    # The custom detector's torque-collapse gate safely supports old cars whose
    # fuel cut sits unusually far below Forza's nominal maximum.
    MIN_PEAK_PCT = 0.62
    MIN_COMMIT_NOMINAL_FRAC = 0.62
    LEGACY_MIN_COMMIT_NOMINAL_FRAC = 0.62
    PEAK_EPS = 40.0
    MIN_OSCILLATION = 150.0
    MIN_EDGE_RPM = 40.0
    MIN_RISES = 2
    MIN_DROPS = 2
    PEAK_DRIFT_DOWN_EPS = 120.0
    LIMITER_TORQUE_COLLAPSE_RATIO = 0.45
    CROSS_GEAR_CONFIRMS = 2
    CROSS_GEAR_EPS_FRAC = 0.015
    MAX_BANKED_OBSERVATIONS = 8

    def __init__(self):
        self._redline: dict[tuple, float] = {}
        self._rpm_window: dict[tuple, deque[float]] = {}
        self._torque_window: dict[tuple, deque[float]] = {}
        self._peak_torque: dict[tuple, float] = {}
        self._peak_hold: dict[tuple, tuple[float, int]] = {}
        self._active_gear: dict[tuple, int] = {}
        self._verified: set[tuple] = set()
        self._candidate: dict[tuple, float] = {}
        self._episode_peak: dict[tuple, float] = {}
        self._observations: dict[tuple, list[float]] = {}

    def clear(self, car: tuple) -> None:
        self._redline.pop(car, None)
        self._rpm_window.pop(car, None)
        self._torque_window.pop(car, None)
        self._peak_torque.pop(car, None)
        self._peak_hold.pop(car, None)
        self._active_gear.pop(car, None)
        self._verified.discard(car)
        self._candidate.pop(car, None)
        self._episode_peak.pop(car, None)
        self._observations.pop(car, None)

    def _reset_window(self, car: tuple) -> None:
        self._bank_episode(car)
        self._rpm_window.pop(car, None)
        self._torque_window.pop(car, None)
        self._peak_hold.pop(car, None)
        self._candidate.pop(car, None)

    def _bank_episode(self, car: tuple) -> None:
        peak = self._episode_peak.pop(car, None)
        if peak is None:
            return
        observations = self._observations.setdefault(car, [])
        observations.append(peak)
        if len(observations) > self.MAX_BANKED_OBSERVATIONS:
            del observations[: len(observations) - self.MAX_BANKED_OBSERVATIONS]
        self._try_cross_gear_confirm(car)

    def _try_cross_gear_confirm(self, car: tuple) -> None:
        if car in self._verified:
            return
        observations = self._observations.get(car, [])
        if len(observations) < self.CROSS_GEAR_CONFIRMS:
            return
        best = max(observations)
        tolerance = best * self.CROSS_GEAR_EPS_FRAC
        if sum(best - peak <= tolerance for peak in observations) >= self.CROSS_GEAR_CONFIRMS:
            self._redline[car] = best
            self._verified.add(car)

    def observe(
        self,
        td: Telemetry,
        last_downshift_time: float,
        now: float,
        *,
        last_upshift_time: float = 0.0,
    ) -> None:
        car = td.car_key
        if self._active_gear.get(car) != td.gear:
            self._reset_window(car)
            self._active_gear[car] = td.gear

        if (
            car[0] <= 0
            or td.is_shifting
            or td.gear < 1
            or td.gear > 10
            or td.engine_max_rpm <= 0
            or td.throttle < self.MIN_THROTTLE
            or now - last_downshift_time < self.POST_DOWNSHIFT_IGNORE_S
            or now - last_upshift_time < self.POST_UPSHIFT_IGNORE_S
            or td.rear_slip > 0.8
            or td.front_slip > 0.8
        ):
            self._reset_window(car)
            return

        if td.torque_nm > self._peak_torque.get(car, 0.0):
            self._peak_torque[car] = td.torque_nm

        rpm_window = self._rpm_window.setdefault(car, deque(maxlen=self.WINDOW))
        torque_window = self._torque_window.setdefault(car, deque(maxlen=self.WINDOW))
        rpm_window.append(td.current_rpm)
        torque_window.append(td.torque_nm)
        if len(rpm_window) < self.WINDOW:
            return

        peak = max(rpm_window)
        trough = min(rpm_window)
        if peak < td.engine_max_rpm * self.MIN_PEAK_PCT or peak - trough < self.MIN_OSCILLATION:
            self._bank_episode(car)
            self._peak_hold.pop(car, None)
            self._candidate.pop(car, None)
            return

        recent = list(rpm_window)
        deltas = [new - old for old, new in zip(recent, recent[1:], strict=False)]
        rises = sum(delta >= self.MIN_EDGE_RPM for delta in deltas)
        drops = sum(delta <= -self.MIN_EDGE_RPM for delta in deltas)
        if rises < self.MIN_RISES or drops < self.MIN_DROPS:
            self._bank_episode(car)
            self._peak_hold.pop(car, None)
            self._candidate.pop(car, None)
            return

        anchor, held_frames = self._peak_hold.get(car, (peak, 0))
        if peak > anchor + self.PEAK_EPS:
            anchor, held_frames = peak, 0
            self._candidate.pop(car, None)
            self._episode_peak.pop(car, None)
        elif peak < anchor - self.PEAK_DRIFT_DOWN_EPS:
            anchor, held_frames = peak, 0
            self._candidate.pop(car, None)
        else:
            held_frames += 1
        self._peak_hold[car] = (anchor, held_frames)

        peak_torque = self._peak_torque.get(car, 0.0)
        torque_collapsed = (
            peak_torque > 0.0
            and len(torque_window) == self.WINDOW
            and min(torque_window) <= peak_torque * self.LIMITER_TORQUE_COLLAPSE_RATIO
        )
        if not torque_collapsed:
            self._candidate.pop(car, None)
            self._episode_peak.pop(car, None)
            return

        confirmed_peak = max(anchor, peak)
        if held_frames >= self.CANDIDATE_STABLE_FRAMES:
            self._candidate[car] = confirmed_peak
            self._episode_peak[car] = max(
                self._episode_peak.get(car, 0.0),
                confirmed_peak,
            )

        if held_frames >= self.STABLE_FRAMES:
            if confirmed_peak < td.engine_max_rpm * self.MIN_COMMIT_NOMINAL_FRAC:
                return
            if car not in self._verified or confirmed_peak > self._redline.get(car, 0.0):
                self._redline[car] = confirmed_peak
            self._verified.add(car)

    def effective_redline(self, td: Telemetry) -> float | None:
        return self._redline.get(td.car_key)

    def candidate_redline(self, td: Telemetry) -> float | None:
        return self._candidate.get(td.car_key)

    def is_verified(self, car: tuple) -> bool:
        return car in self._verified

    def dump(self, car: tuple) -> float | None:
        return self._redline.get(car)

    def load(self, car: tuple, redline: float | dict) -> None:
        if isinstance(redline, dict):
            redline = redline.get("rpm")
        if isinstance(redline, (int, float)) and redline > 0:
            self._redline[car] = float(redline)
            # Existing custom profiles were already learned with the
            # torque-collapse guard, so they remain trusted after migration.
            self._verified.add(car)
