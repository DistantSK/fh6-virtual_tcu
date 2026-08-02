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


def test_failed_upshift_caps_top_gear(make_logic, out, clock):
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
    assert len(ups) == 1
    assert tcu._upshift_cap_by_key[CAR_KEY] == 6


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


def test_manual_downshift_cancels_pending_without_learning_false_top(make_logic, out, clock):
    tcu = make_logic("COMFORT")
    td = make_telemetry(
        gear=6,
        current_rpm=7600,
        engine_max_rpm=8000.0,
        speed_ms=180.0 / 3.6,
        accel_raw=255,
        brake_raw=0,
    )
    tcu._prev_gear = td.gear
    assert tcu._shift_up(td, 350, "UPSHIFT")

    clock.now += 0.10
    td.gear = 5
    td.current_rpm = 5000
    td.accel_raw = 0
    tcu.process(td)

    assert tcu._pending_upshift_from is None
    assert CAR_KEY not in tcu._upshift_cap_by_key

    clock.now += 2.0
    tcu.process(td)
    assert CAR_KEY not in tcu._upshift_cap_by_key
    assert CAR_KEY not in tcu._cap_confirm


def test_auto_upshift_recovers_after_manual_downshift_interrupt(make_logic, out, clock):
    tcu = make_logic("COMFORT")
    td = make_telemetry(
        gear=5,
        current_rpm=7600,
        engine_max_rpm=8000.0,
        speed_ms=160.0 / 3.6,
        accel_raw=255,
        brake_raw=0,
    )
    tcu._prev_gear = td.gear
    assert tcu._shift_up(td, 350, "UPSHIFT")

    clock.now += 0.10
    td.gear = 4
    td.current_rpm = 5000
    td.accel_raw = 0
    tcu.process(td)

    clock.now += 1.0
    out.now = clock.now
    td.current_rpm = 7600
    td.accel_raw = 255
    tcu.process(td)

    ups = [shift for shift in out.shifts if shift[0] == "UP"]
    assert len(ups) == 2
    assert tcu._pending_upshift_from == 4


def test_repeated_manual_interruptions_never_create_sticky_cap(make_logic, clock):
    tcu = make_logic("COMFORT")
    td = make_telemetry(current_rpm=5000, accel_raw=0)

    for from_gear, manual_gear in ((6, 5), (5, 4), (4, 3)):
        td.gear = from_gear
        tcu._prev_gear = from_gear
        assert tcu._shift_up(td, 350, "UPSHIFT")

        clock.now += 0.10
        td.gear = manual_gear
        tcu.process(td)

        assert tcu._pending_upshift_from is None
        assert CAR_KEY not in tcu._upshift_cap_by_key
        assert CAR_KEY not in tcu._cap_confirm


def test_in_progress_upshift_is_not_capped_on_timeout(make_logic, clock):
    tcu = make_logic("COMFORT")
    td = make_telemetry(gear=6, is_shifting=True)
    assert tcu._shift_up(td, 350, "UPSHIFT")

    clock.now += 1.5
    tcu._resolve_pending_upshift(td, clock.now)

    assert tcu._pending_upshift_from == 6
    assert tcu._pending_upshift_until > clock.now
    assert CAR_KEY not in tcu._upshift_cap_by_key


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
