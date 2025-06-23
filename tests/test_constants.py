import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def test_single_months_constant():
    occurrences = []
    for p in ROOT.rglob('*.py'):
        if 'venv' in p.parts or 'tests' in p.parts:
            continue
        text = p.read_text(encoding='utf-8')
        if 'MONTHS_RU =' in text:
            occurrences.append(p)
    expected = ROOT / 'app' / 'core' / 'constants.py'
    assert occurrences == [expected]

def test_single_banks_constant():
    occurrences = []
    for p in ROOT.rglob('*.py'):
        if 'venv' in p.parts or 'tests' in p.parts:
            continue
        text = p.read_text(encoding='utf-8')
        if 'BANKS =' in text:
            occurrences.append(p)
    expected = ROOT / 'app' / 'core' / 'constants.py'
    assert occurrences == [expected]
