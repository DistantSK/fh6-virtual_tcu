from tests.conftest import CAR_KEY, make_telemetry
from virtual_tcu.learning.rev_limiter import RevLimiterDetector


def _feed_candidate(detector: RevLimiterDetector, gear: int, now: float) -> float:
    rpms = (7200.0, 6980.0, 7180.0, 7000.0)
    torques = (320.0, 0.0, 300.0, -10.0)
    for index in range(32):
        td = make_telemetry(
            gear=gear,
            current_rpm=rpms[index % len(rpms)],
            engine_max_rpm=8000.0,
            torque_nm=torques[index % len(torques)],
            accel_raw=255,
            speed_ms=(80 + gear * 20) / 3.6,
        )
        now += 0.016
        detector.observe(td, 0.0, now, last_upshift_time=0.0)
    assert detector.candidate_redline(td) is not None
    return now


def test_cross_gear_candidates_confirm_real_limiter():
    detector = RevLimiterDetector()
    now = _feed_candidate(detector, 1, 100.0)
    now = _feed_candidate(detector, 2, now)

    # Leaving the second candidate episode banks it and combines the two
    # independent gear observations.
    td = make_telemetry(
        gear=3,
        current_rpm=5000.0,
        engine_max_rpm=8000.0,
        torque_nm=200.0,
        accel_raw=0,
        speed_ms=120 / 3.6,
    )
    detector.observe(td, 0.0, now + 0.016, last_upshift_time=0.0)

    assert detector.is_verified(CAR_KEY)
    assert detector.effective_redline(td) == 7200.0


def test_steady_power_plateau_is_not_a_limiter():
    detector = RevLimiterDetector()
    now = 100.0
    td = None
    for index in range(80):
        td = make_telemetry(
            gear=4,
            current_rpm=7100.0 + (index % 4) * 60.0,
            engine_max_rpm=8000.0,
            torque_nm=320.0,
            accel_raw=255,
            speed_ms=180 / 3.6,
        )
        now += 0.016
        detector.observe(td, 0.0, now, last_upshift_time=0.0)

    assert td is not None
    assert detector.candidate_redline(td) is None
    assert detector.effective_redline(td) is None
