"""Upshift must not spam until the game confirms the gear change."""

from pathlib import Path

import virtual_tcu.logic.tcu as tcu_module
from tests.conftest import CAR_KEY, FakeOutput, make_telemetry
from virtual_tcu.config.store import ConfigStore
from virtual_tcu.logic.tcu import TCULogic
from virtual_tcu.storage.profiles import ProfileStore
from virtual_tcu.telemetry.logger import TelemetryLogger
from virtual_tcu.telemetry.parser import parse_fh6_packet
from virtual_tcu.telemetry.replay_reader import iter_replay_records


def test_upshift_pending_blocks_repeat(make_logic, out, clock):
    tcu = make_logic("COMFORT")
    td = make_telemetry(
        gear=2,
        current_rpm=6800,
        engine_max_rpm=8000.0,
        speed_ms=80.0 / 3.6,
        accel_raw=255,
        brake_raw=0,
    )
    for _ in range(120):
        clock.now += 0.016
        out.now = clock.now
        tcu.process(td)
    ups = [s for s in out.shifts if s[0] == "UP"]
    assert len(ups) == 1


def test_failed_upshift_soft_caps_and_retries_top_gear(make_logic, out, clock):
    tcu = make_logic("COMFORT")
    td = make_telemetry(
        gear=6,
        current_rpm=7600,
        engine_max_rpm=8000.0,
        speed_ms=200.0 / 3.6,
        accel_raw=255,
        brake_raw=0,
    )
    for _ in range(300):
        clock.now += 0.016
        out.now = clock.now
        tcu.process(td)
    ups = [s for s in out.shifts if s[0] == "UP"]
    assert 2 <= len(ups) <= 4
    assert tcu._upshift_cap_by_key[CAR_KEY] == 6


def test_midshift_encoding_does_not_confirm_upshift(make_logic, out, clock):
    tcu = make_logic("RACE")
    tcu._pending_upshift_from = 1
    tcu._pending_upshift_until = clock.now + 0.1
    tcu._we_shifted = True
    tcu._prev_gear = 1

    shifting = make_telemetry(
        gear=11,
        is_shifting=True,
        current_rpm=7200,
        engine_max_rpm=8000.0,
        speed_ms=50.0 / 3.6,
        accel_raw=255,
    )
    clock.now += 0.2
    out.now = clock.now
    tcu.process(shifting)

    assert tcu._pending_upshift_from == 1
    assert tcu._pending_upshift_until > clock.now

    confirmed = make_telemetry(
        gear=2,
        current_rpm=5600,
        engine_max_rpm=8000.0,
        speed_ms=55.0 / 3.6,
        accel_raw=255,
    )
    clock.now += 0.05
    out.now = clock.now
    tcu.process(confirmed)

    assert tcu._pending_upshift_from is None
    assert tcu._prev_gear == 2
    assert not tcu._we_shifted


def test_high_gear_cap_uses_bounded_backoff(make_logic, out, clock):
    tcu = make_logic("COMFORT")
    td = make_telemetry(
        gear=8,
        current_rpm=7600,
        engine_max_rpm=8000.0,
        speed_ms=260.0 / 3.6,
        accel_raw=255,
        brake_raw=0,
    )
    for _ in range(2000):
        clock.now += 0.016
        out.now = clock.now
        tcu.process(td)

    ups = [shift for shift in out.shifts if shift[0] == "UP"]
    assert 3 <= len(ups) <= 8
    assert tcu._upshift_fail_count[CAR_KEY] >= 3


def test_real_downshift_clears_stale_cap(make_logic, out, clock):
    tcu = make_logic("COMFORT")
    tcu._prev_gear = 8
    tcu._upshift_cap_by_key[CAR_KEY] = 8
    tcu._upshift_cap_set_at[CAR_KEY] = clock.now
    tcu._upshift_fail_count[CAR_KEY] = 3

    td = make_telemetry(gear=7, current_rpm=4200, speed_ms=180.0 / 3.6)
    clock.now += 0.016
    out.now = clock.now
    tcu.process(td)

    assert tcu._upshift_cap_by_key[CAR_KEY] == 10
    assert CAR_KEY not in tcu._upshift_fail_count


def test_failed_low_gear_upshift_retries_at_redline(make_logic, out, clock):
    tcu = make_logic("COMFORT")
    td = make_telemetry(
        gear=1,
        current_rpm=7600,
        engine_max_rpm=8000.0,
        speed_ms=45.0 / 3.6,
        vel_z=12.0,
        accel_raw=255,
        brake_raw=0,
    )
    for _ in range(250):
        clock.now += 0.016
        out.now = clock.now
        tcu.process(td)
    ups = [s for s in out.shifts if s[0] == "UP"]
    assert len(ups) >= 2
    assert len(ups) <= 6


def test_cold_awd_wheelspin_can_escape_first_gear(make_logic):
    tcu = make_logic("RACE", seed_ratios=False)
    awd = make_telemetry(
        gear=1,
        drivetrain=2,
        accel_raw=255,
        slip_fl=1.5,
        slip_fr=1.5,
        slip_rl=1.5,
        slip_rr=1.5,
    )
    assert not tcu._wheelspin_upshift_now(awd)
    assert not tcu._wheelspin_upshift_now(awd)
    assert tcu._wheelspin_upshift_now(awd)


def test_cold_rwd_wheelspin_waits_for_power_curve(make_logic):
    tcu = make_logic("RACE", seed_ratios=False)
    rwd = make_telemetry(
        gear=1,
        drivetrain=1,
        accel_raw=255,
        slip_rl=1.5,
        slip_rr=1.5,
    )
    for _ in range(5):
        assert not tcu._wheelspin_upshift_now(rwd)


def test_low_gear_unreachable_wot_target_uses_measured_ceiling(make_logic):
    tcu = make_logic("RACE", seed_ratios=False)
    tcu._rpm_pct_history.extend([0.858, 0.861, 0.859, 0.860, 0.861] * 2)
    td = make_telemetry(
        gear=1,
        current_rpm=0.86 * 8000,
        engine_max_rpm=8000.0,
        speed_ms=45.0 / 3.6,
        accel_raw=255,
        brake_raw=0,
    )

    assert tcu._wot_upshift_fallback(td) < 0.90


def test_comfort_uses_real_limiter_without_mutating_nominal_rpm(make_logic, out, clock):
    tcu = make_logic("COMFORT")
    tcu._rev_limiter.load(CAR_KEY, 6240.0)
    td = make_telemetry(
        gear=3,
        current_rpm=6400.0,
        engine_max_rpm=8000.0,
        speed_ms=100.0 / 3.6,
        accel_raw=255,
        brake_raw=0,
    )
    nominal = td.engine_max_rpm

    clock.now += 0.016
    out.now = clock.now
    tcu.process(td)

    assert any(shift[0] == "UP" for shift in out.shifts)
    assert td.engine_max_rpm == nominal


def test_high_gear_plateau_requires_time_normalized_evidence(make_logic, clock):
    tcu = make_logic("RACE")
    td = make_telemetry(
        gear=8,
        current_rpm=0.83 * 8000,
        engine_max_rpm=8000.0,
        speed_ms=260.0 / 3.6,
        accel_raw=255,
        brake_raw=0,
    )

    for index in range(100):
        clock.now += 0.016
        td.current_rpm = (0.83 + index * 0.0005) * 8000
        td.speed_ms = (260.0 + index * 0.10) / 3.6
        tcu._observe_high_gear_load_plateau(td, tcu.mode, clock.now)

    assert not tcu._load_plateau_reached

    tcu._reset_load_plateau()
    td.current_rpm = 0.84 * 8000
    td.speed_ms = 280.0 / 3.6
    for _ in range(180):
        clock.now += 0.016
        tcu._observe_high_gear_load_plateau(td, tcu.mode, clock.now)

    assert tcu._load_plateau_reached
    assert tcu._wot_upshift_fallback(td) < 0.90


def test_reverse_exit_does_not_block_launch_upshift(make_logic, out, clock):
    tcu = make_logic("COMFORT")
    td_r = make_telemetry(gear=0, speed_ms=0, accel_raw=0, vel_z=0)
    tcu.process(td_r)

    td = make_telemetry(
        gear=1,
        current_rpm=7500,
        engine_max_rpm=8000.0,
        speed_ms=25.0 / 3.6,
        vel_z=7.0,
        accel_raw=255,
        brake_raw=0,
    )
    for _ in range(80):
        clock.now += 0.016
        out.now = clock.now
        tcu.process(td)
    ups = [s for s in out.shifts if s[0] == "UP"]
    assert len(ups) >= 1


def test_ski_log_no_6_to_7_spam(clock, tmp_path):
    log_path = Path(__file__).resolve().parent.parent / "logs" / "滑雪越野赛事不换挡.gz"
    if not log_path.is_file():
        return

    cfg = ConfigStore(path=str(tmp_path / "cfg.json"))
    prof_path = Path(__file__).resolve().parent.parent / "tcu_profiles.json"
    prof = ProfileStore(path=str(prof_path if prof_path.is_file() else tmp_path / "prof.json"))

    class CountOut(FakeOutput):
        def __init__(self):
            super().__init__()
            self.pairs: list[tuple[int, int]] = []

        def shift_to(self, from_gear: int, target_gear: int):
            self.pairs.append((from_gear, target_gear))
            super().shift_to(from_gear, target_gear)

    out = CountOut()
    tcu = TCULogic(out, prof, cfg, TelemetryLogger())
    tcu.set_mode("COMFORT")
    tcu_module.time.time = clock

    for ms, raw in iter_replay_records(log_path):
        td = parse_fh6_packet(raw)
        if td is None:
            continue
        clock.now = ms / 1000.0
        tcu.process(td, raw)

    six_to_seven = sum(1 for fg, tg in out.pairs if fg == 6 and tg == 7)
    assert six_to_seven <= 2
