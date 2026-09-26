"""runs.py ve labctl.py testleri: depodaki gerçek ölçümlerle."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from labctl import FIX_BTN_PRIO, FIX_PRESETS, FIX_TC_CHAIN, FIX_UART_PRIO, LabConfig, fix_label  # noqa: E402
from runs import default_runs  # noqa: E402

RUNS = {r.cfg.get("scenario") + ("/official" if r.official else ""): r for r in default_runs()}


def test_defaults_include_official_and_lab_runs():
    assert {f"S{i}/official" for i in range(6)} <= set(RUNS)
    assert {"S5a", "S5-F1a", "S5-F4a", "S5-F5a"} <= set(RUNS)
    assert [m for _, _, m in FIX_PRESETS] == [0, FIX_BTN_PRIO, FIX_UART_PRIO, FIX_TC_CHAIN,
                                              FIX_UART_PRIO | FIX_BTN_PRIO]
    lab_runs = [r for r in RUNS.values() if not r.official]
    assert sorted(r.fix for r in lab_runs) == [0, 1, 4, 5, 8]    # 5 çözüm


def test_official_s5_is_diagnosed_as_uart_starvation():
    s5 = RUNS["S5/official"]
    assert s5.uart_starved()
    assert s5.backlog_slope_ms_per_event() > 1          # birikim var
    late = next(e for e in s5.events if e.late)
    dom, why = s5.diagnose(late)
    assert dom == "pretx" and "Kök neden" in why
    lost = next(e for e in s5.events if not e.ok)
    assert "txQ doluydu" in s5.diagnose(lost)[1]


def test_root_fix_removes_starvation_and_backlog():
    f1 = RUNS["S5-F1a"]
    assert not f1.uart_starved()
    assert abs(f1.backlog_slope_ms_per_event()) < 0.5
    assert f1.stat()["late"] == 0 and f1.stat()["lost"] == 0


def test_tc_chain_fixes_backlog_without_priority_change():
    chain = RUNS["S5-F8a"]
    assert not chain.uart_starved()
    assert chain.stat()["late"] == 0 and chain.stat()["lost"] == 0
    prios = {t["name"]: t["prio"] for t in chain.tasks}
    assert (prios["telemetry"], prios["button"], prios["uart_tx"]) == ("3", "2", "1")


def test_naive_fix_alone_keeps_backlog():
    naive = RUNS["S5-F4a"]
    assert naive.uart_starved()                          # UART hâlâ aç
    assert naive.stat()["late"] > 30
    assert naive.stage_means()["task"] < 0.1             # ama görev beklemesi kalktı


def test_optimal_is_fastest_fix():
    opt, root = RUNS["S5-F5a"], RUNS["S5-F1a"]
    assert opt.stat()["max"] < root.stat()["max"]
    assert opt.stage_means()["task"] < 0.1


def test_s0_events_are_line_dominated():
    s0 = RUNS["S0/official"]
    dom, why = s0.diagnose(s0.events[0])
    assert dom == "line" and "tutuldu" in why


def test_lab_command_format():
    cfg = LabConfig(period_ms=10, work_us=5000, fix=FIX_UART_PRIO | FIX_BTN_PRIO, inject=1, target=35,
                    gap_min_ms=500, gap_max_ms=1500, seed=7, run_id=3)
    assert cfg.command() == ("RUN name=S5-F5a period=10 work=5000 target=35 fix=5 inject=1 "
                             "gmin=500 gmax=1500 seed=7 run=3\n")
    assert LabConfig(period_ms=20, work_us=1500, inject=0).auto_name() == "C20W1500"
    assert fix_label(5).startswith("Optimal")
