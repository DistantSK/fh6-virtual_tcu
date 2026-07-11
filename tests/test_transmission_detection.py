import time

from conftest import CAR_KEY, make_telemetry


def _enable_clutch_detection(tcu):
    tcu._config.set("feat_clutch_assist", True)
    tcu._config.set("vjoy_use_clutch", True)


def test_fast_clutchless_upshift_detects_sequential(make_logic, out):
    tcu = make_logic()
    _enable_clutch_detection(tcu)

    tcu._shift_to(2, 3)
    assert out.no_clutch_shifts == [(2, 3)]

    tcu._detect_transmission_frame(make_telemetry(gear=3))

    assert tcu._racing_transmission[CAR_KEY] is True
    assert tcu.snapshot(make_telemetry(gear=3))["transmission_type"] == "sequential"


def test_slow_clutchless_upshift_detects_clutch_gearbox(make_logic, out):
    tcu = make_logic()
    _enable_clutch_detection(tcu)

    tcu._shift_to(2, 3)
    for _ in range(5):
        tcu._detect_transmission_frame(make_telemetry(gear=2))
    tcu._detect_transmission_frame(make_telemetry(gear=3))

    assert tcu._racing_transmission[CAR_KEY] is False
    assert tcu.snapshot(make_telemetry(gear=3))["transmission_type"] == "clutch"


def test_intercepted_shift_keeps_transmission_unknown(make_logic, out):
    tcu = make_logic()
    _enable_clutch_detection(tcu)

    tcu._shift_to(2, 3)
    tcu._detect_deadline = time.monotonic() - 1.0
    tcu._detect_transmission_frame(make_telemetry(gear=2))

    assert CAR_KEY not in tcu._racing_transmission
    assert tcu._detect_active is None
    assert tcu.snapshot(make_telemetry(gear=2))["transmission_type"] == "unknown"
