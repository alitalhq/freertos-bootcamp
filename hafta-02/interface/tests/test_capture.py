"""capture.py testleri: RUN komutu ve firmware senaryo tablosuyla uyum."""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from capture import MATRIX, SCENARIOS, run_command, run_name  # noqa: E402

SCENARIO_C = Path(__file__).resolve().parents[2] / "firmware" / "odev02" / "App" / "scenario.c"


def test_scenarios_match_firmware_table():
    rows = re.findall(r'\{\s*"(S\d)",\s*(\d+),\s*(\d+),\s*(\d+)\s*\}', SCENARIO_C.read_text())
    fw = {name: (int(p), int(b), int(w)) for name, p, b, w in rows}
    assert fw == SCENARIOS


def test_run_command_fields():
    cmd = run_command("C", "S6", True, 35, 7, 12, 500, 1500)
    assert cmd.endswith("\n")
    assert cmd.split() == ["RUN", "name=C-S6a", "var=C", "period=100", "burst=4", "work=0",
                           "target=35", "inject=1", "gmin=500", "gmax=1500", "seed=7", "run=12"]


def test_run_name_fits_board_buffer():
    # RunConfig.name 16 bayt (NUL dahil)
    assert all(len(run_name(v, s, True)) <= 15 for v in "ABC" for s in SCENARIOS)


def test_matrix_is_assignment_set():
    assert MATRIX == [("A", "S5"), ("B", "S5"), ("C", "S5"), ("B", "S6"), ("C", "S6")]
