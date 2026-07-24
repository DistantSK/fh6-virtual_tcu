from virtual_tcu.telemetry.model import Telemetry


class GearRatioCalibrator:
    """Learns rpm/kmh ratio per car/gear. The ratio is a fixed property of
    the transmission — valid whenever the wheels grip and no shift is in
    progress, under positive drive torque. Uses a running mean with outlier
    rejection: an estimate exists from the first valid sample and converges
    within a second of driving in each gear."""

    MIN_SPEED_KMH = 25.0
    OUTLIER_TOLERANCE = 0.18
    LEARN_RATE = 0.08
    OUTLIER_GRACE = 5  # samples before outlier rejection kicks in
    INITIAL_STABLE_SAMPLES = 3
    INITIAL_STABILITY_TOLERANCE = 0.08
    CLUTCH_INPUT_THRESHOLD = 20
    # Reject samples that would collapse spacing between adjacent gears.
    ORDER_TOLERANCE = 0.03
    # Plausible rpm-per-km/h envelope for a valid gear-ratio sample. The lower
    # bound used to be 15, which silently discarded the tall top gear of very
    # fast cars: a hypercar pulling 410 km/h in 5th reads ~14 rpm/(km/h), below
    # 15, so 5th never learned and the box was stuck "learning 4/5". 8.0 still
    # rejects genuine garbage (it implies >500 km/h at idle) while admitting any
    # real top gear. MIN_SPEED_KMH + the per-gear ordering check guard the rest.
    RATIO_MIN_RPM_PER_KMH = 8.0
    RATIO_MAX_RPM_PER_KMH = 500.0

    def __init__(self):
        self._ratios: dict[tuple, dict[int, float]] = {}
        self._counts: dict[tuple, dict[int, int]] = {}
        self._candidates: dict[tuple, dict[int, list[float]]] = {}

    @staticmethod
    def _is_driven_sample(td: Telemetry) -> bool:
        """Ratio is only meaningful when the engine drives the wheels."""
        if td.torque_nm <= 0:
            return False
        # Overrun / snow-downhill drag: full throttle but wheels turning the crank.
        if td.throttle > 0.45 and td.power_w < 0:
            return False
        return True

    def _order_ok(self, car_ratios: dict[int, float], gear: int, ratio: float) -> bool:
        """Higher gears must have a lower rpm/kmh ratio than lower gears."""
        tol = self.ORDER_TOLERANCE
        lower = car_ratios.get(gear - 1)
        if lower is not None and ratio >= lower * (1.0 - tol):
            return False
        higher = car_ratios.get(gear + 1)
        if higher is not None and ratio <= higher * (1.0 + tol):
            return False
        return True

    def observe(self, td: Telemetry):
        ck = td.car_key
        if ck[0] <= 0 or td.gear < 1 or td.gear > 10:
            return
        if td.is_shifting:
            return
        if td.clutch_raw > self.CLUTCH_INPUT_THRESHOLD:
            return
        if td.speed_kmh < self.MIN_SPEED_KMH or td.current_rpm <= 0:
            return
        if not self._is_driven_sample(td):
            return
        # Wheelspin breaks the wheel-ground relationship → invalid ratio
        if td.rear_slip > 0.8 or td.front_slip > 0.8:
            return
        ratio = td.current_rpm / td.speed_kmh
        if ratio < self.RATIO_MIN_RPM_PER_KMH or ratio > self.RATIO_MAX_RPM_PER_KMH:
            return

        car_ratios = self._ratios.setdefault(ck, {})
        car_counts = self._counts.setdefault(ck, {})
        gear = td.gear

        if gear not in car_ratios:
            candidates = self._candidates.setdefault(ck, {}).setdefault(gear, [])
            if candidates and abs(ratio - candidates[-1]) / candidates[-1] > (
                self.INITIAL_STABILITY_TOLERANCE
            ):
                candidates.clear()
            candidates.append(ratio)
            if len(candidates) < self.INITIAL_STABLE_SAMPLES:
                return
            initial = sum(candidates) / len(candidates)
            if not self._order_ok(car_ratios, gear, initial):
                candidates.clear()
                return
            car_ratios[gear] = initial
            car_counts[gear] = len(candidates)
            self._candidates[ck].pop(gear, None)
            return

        current = car_ratios[gear]
        n = car_counts[gear]
        # Reject outliers once a base is established (a mid-shift glitch or
        # slip spike that slipped past the filters)
        if n >= self.OUTLIER_GRACE:
            if abs(ratio - current) / current > self.OUTLIER_TOLERANCE:
                return
        if not self._order_ok(car_ratios, gear, ratio):
            return
        # Running mean: true average early, stable low-pass once mature
        rate = max(self.LEARN_RATE, 1.0 / (n + 1))
        car_ratios[gear] = current + rate * (ratio - current)
        car_counts[gear] = n + 1

    def project_rpm_after_shift(self, td: Telemetry, target_gear: int) -> float | None:
        car_ratios = self._ratios.get(td.car_key)
        if not car_ratios:
            return None
        target_ratio = car_ratios.get(target_gear)
        if not target_ratio:
            return None
        return target_ratio * td.speed_kmh

    def get_ratios(self, car_key: tuple) -> dict[int, float]:
        """Public accessor — learned rpm/kmh ratios for a car, or empty."""
        return self._ratios.get(car_key, {})

    def clear(self, car_key: tuple) -> None:
        self._ratios.pop(car_key, None)
        self._counts.pop(car_key, None)
        self._candidates.pop(car_key, None)

    def has_data(self, car_key: tuple) -> bool:
        return car_key in self._ratios and len(self._ratios[car_key]) >= 2

    def gear_sample_counts(self, car_key: tuple) -> dict[int, int]:
        """Per-gear sample counts for *car_key* — how converged each gear is."""
        return self._counts.get(car_key, {})

    def mature_gear_count(self, car_key: tuple, min_samples: int = 5) -> int:
        """Number of gears whose ratio has converged past outlier grace.

        A gear with only one or two samples (e.g. a brief 1->2 launch) does not
        count: its ratio is a single raw reading, not a settled estimate."""
        return sum(1 for n in self._counts.get(car_key, {}).values() if n >= min_samples)

    def max_gear_seen(self, car_key: tuple) -> int:
        """Highest forward gear with any learned sample — a lower bound on the
        car's real top gear (telemetry never reports the gear count directly)."""
        counts = self._counts.get(car_key)
        return max(counts) if counts else 0

    def dump(self, car_key: tuple) -> dict | None:
        """Serialise learned ratios for *car_key*, or None if no data."""
        if not self.has_data(car_key):
            return None
        return {
            "ratios": dict(self._ratios.get(car_key, {})),
            "counts": dict(self._counts.get(car_key, {})),
        }

    def load(self, car_key: tuple, data: dict):
        """Restore ratios from a previously-saved dump."""
        if not isinstance(data, dict):
            return
        self._candidates.pop(car_key, None)
        ratios = data.get("ratios")
        counts = data.get("counts")
        if isinstance(ratios, dict):
            parsed: dict[int, float] = {}
            for key, value in ratios.items():
                try:
                    gear = int(key)
                    ratio = float(value)
                except (TypeError, ValueError):
                    continue
                if (
                    1 <= gear <= 10
                    and self.RATIO_MIN_RPM_PER_KMH <= ratio <= self.RATIO_MAX_RPM_PER_KMH
                ):
                    parsed[gear] = ratio

            # A transition frame saved against the destination gear commonly
            # leaves adjacent ratios equal or reversed. Drop only the suspect
            # gear so clean neighbours survive and the missing slot relearns.
            clean: dict[int, float] = {}
            for gear in sorted(parsed):
                ratio = parsed[gear]
                if self._order_ok(clean, gear, ratio):
                    clean[gear] = ratio
            self._ratios[car_key] = clean

            parsed_counts = counts if isinstance(counts, dict) else {}
            self._counts[car_key] = {}
            for gear in clean:
                raw_count = parsed_counts.get(gear, parsed_counts.get(str(gear), 0))
                try:
                    self._counts[car_key][gear] = max(0, int(raw_count))
                except (TypeError, ValueError):
                    self._counts[car_key][gear] = 0
