"""Gear ratio learning must ignore engine-braking / overrun samples."""

from tests.conftest import CAR_KEY, make_telemetry
from virtual_tcu.learning.gear_ratio import GearRatioCalibrator


def test_negative_torque_does_not_learn():
    cal = GearRatioCalibrator()
    td = make_telemetry(
        gear=4,
        current_rpm=6000,
        speed_ms=120.0 / 3.6,
        torque_nm=-80.0,
        power_w=-90000,
        accel_raw=255,
    )
    for _ in range(40):
        cal.observe(td)
    assert cal.get_ratios(CAR_KEY) == {}


def test_wot_negative_power_downhill_does_not_learn():
    cal = GearRatioCalibrator()
    cal.load(CAR_KEY, {"ratios": {4: 55.0}, "counts": {4: 20}})
    td = make_telemetry(
        gear=4,
        current_rpm=6000,
        speed_ms=120.0 / 3.6,
        torque_nm=120.0,
        power_w=-95000,
        accel_raw=255,
    )
    for _ in range(30):
        cal.observe(td)
    assert cal.get_ratios(CAR_KEY)[4] == 55.0


def test_positive_drive_updates_ratio():
    cal = GearRatioCalibrator()
    td = make_telemetry(
        gear=4,
        current_rpm=6000,
        speed_ms=120.0 / 3.6,
        torque_nm=250.0,
        power_w=180000,
        accel_raw=255,
    )
    for _ in range(10):
        cal.observe(td)
    assert 45 < cal.get_ratios(CAR_KEY)[4] < 55


def test_clutch_pressed_does_not_learn():
    cal = GearRatioCalibrator()
    td = make_telemetry(
        gear=3,
        current_rpm=5000,
        speed_ms=100.0 / 3.6,
        torque_nm=220.0,
        power_w=150000,
        accel_raw=220,
        clutch_raw=255,
    )
    for _ in range(20):
        cal.observe(td)
    assert cal.get_ratios(CAR_KEY) == {}


def test_new_gear_requires_consecutive_stable_samples():
    cal = GearRatioCalibrator()
    transient = make_telemetry(
        gear=4,
        current_rpm=7800,
        speed_ms=120.0 / 3.6,
        torque_nm=220.0,
        power_w=180000,
        accel_raw=255,
    )
    stable = make_telemetry(
        gear=4,
        current_rpm=6000,
        speed_ms=120.0 / 3.6,
        torque_nm=220.0,
        power_w=180000,
        accel_raw=255,
    )

    cal.observe(transient)
    cal.observe(stable)
    cal.observe(stable)
    assert cal.get_ratios(CAR_KEY) == {}

    cal.observe(stable)
    assert 49 < cal.get_ratios(CAR_KEY)[4] < 51


def test_tcu_pauses_learning_until_new_gear_settles(make_logic, out, clock):
    tcu = make_logic("MANUAL", seed_ratios=False)
    tcu._prev_gear = 2
    td = make_telemetry(
        gear=3,
        current_rpm=5000,
        speed_ms=100.0 / 3.6,
        torque_nm=220.0,
        power_w=150000,
        accel_raw=220,
        is_race_on=1,
    )

    clock.now += 0.016
    out.now = clock.now
    tcu.process(td)
    assert cal_ratio(tcu, 3) is None

    for _ in range(20):
        clock.now += 0.016
        out.now = clock.now
        tcu.process(td)
    assert cal_ratio(tcu, 3) is None

    clock.now += 0.46
    for _ in range(3):
        clock.now += 0.016
        out.now = clock.now
        tcu.process(td)
    assert 49 < cal_ratio(tcu, 3) < 51


def cal_ratio(tcu, gear):
    return tcu._calibrator.get_ratios(CAR_KEY).get(gear)


def test_load_drops_saved_ratio_assigned_to_wrong_gear():
    cal = GearRatioCalibrator()
    cal.load(
        CAR_KEY,
        {
            "ratios": {"1": 120.0, "2": 82.0, "3": 84.0, "4": 45.0},
            "counts": {"1": 30, "2": 30, "3": 30, "4": 30},
        },
    )

    assert cal.get_ratios(CAR_KEY) == {1: 120.0, 2: 82.0, 4: 45.0}
    assert cal.gear_sample_counts(CAR_KEY) == {1: 30, 2: 30, 4: 30}
