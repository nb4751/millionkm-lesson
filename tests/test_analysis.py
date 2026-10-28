import math
import pytest
from training.analysis import analyze, ftp_zones, training_load


def constant(power=250, duration=3600):
    return [{'elapsed_seconds': i, 'power': power, 'heart_rate': 150, 'cadence': 90} for i in range(duration)]


def test_constant_np_tss_and_energy():
    metrics = analyze(constant(), ftp=250, weight=50)
    assert metrics['np'] == pytest.approx(250)
    assert metrics['if'] == 1
    assert metrics['tss'] == pytest.approx(100)
    assert metrics['kj'] == pytest.approx(900)
    assert metrics['avg_wkg'] == 5
    assert metrics['power_curve']['3600'] == 250
    assert metrics['zones'][3]['seconds'] == 3600


def test_np_fourth_power_formula():
    samples = constant(100, 60)
    for record in samples[30:]:
        record['power'] = 300
    rolling = [sum(r['power'] for r in samples[i:i+30]) / 30 for i in range(31)]
    expected = (sum(value ** 4 for value in rolling) / len(rolling)) ** .25
    metrics = analyze(samples, ftp=200)
    assert metrics['np'] == pytest.approx(expected, abs=.001)
    assert metrics['tss'] == pytest.approx(60 / 3600 * (expected / 200) ** 2 * 100, abs=.001)


def test_short_curve_and_actual_continuous_maximum():
    samples = constant(100, 40)
    for record in samples[10:15]:
        record['power'] = 500
    metrics = analyze(samples)
    assert metrics['power_curve']['5'] == 500
    assert metrics['power_curve']['10'] == 300
    assert metrics['power_curve']['60'] is None
    assert metrics['power_curve']['3600'] is None
    assert metrics['tss'] is None


def test_time_weighting_and_missing_gap_not_zero_filled():
    samples = [{'elapsed_seconds': 0, 'power': 100}, {'elapsed_seconds': 2, 'power': 300},
               {'elapsed_seconds': 4, 'power': 300}]
    result = analyze(samples)
    assert result['avg_power'] == pytest.approx(700 / 3, abs=.001)
    assert result['power_curve']['5'] == 260
    gapped = constant(200, 10) + [{'elapsed_seconds': 100+i, 'power': 400} for i in range(10)]
    result = analyze(gapped, ftp=250)
    assert result['power_curve']['30'] is None
    assert result['avg_power'] == 300
    assert result['np'] is None
    assert result['tss'] is None
    assert result['power_coverage'] < .2


def test_missing_power_and_paused_periods_never_imply_zero():
    samples = constant(200, 40)
    samples[15]['power'] = None
    samples[20]['paused'] = True
    result = analyze(samples, ftp=200)
    assert result['avg_power'] == 200
    assert result['power_recording_seconds'] == 38
    assert result['np'] is None
    assert result['power_curve']['30'] is None


def test_250w_ftp_zone_boundaries_no_overlap():
    zones = ftp_zones(250)
    assert [(z['min'], z['max']) for z in zones] == [(0,137),(138,187),(188,225),(226,262),(263,300),(301,375),(376,None)]
    readings = [0,137,138,187,188,225,226,262,263,300,301,375,376]
    result = analyze([{'elapsed_seconds': i, 'power': p} for i,p in enumerate(readings)], ftp=250)
    assert [z['seconds'] for z in result['zones']] == [2,2,2,2,2,2,1]
    assert sum(z['seconds'] for z in result['zones']) == len(readings)


def test_empty_and_nonfinite_values_are_missing():
    result = analyze([{'elapsed_seconds': 0, 'power': float('nan')}], ftp=0)
    assert result['avg_power'] is None
    assert result['kj'] is None
    assert result['zones'] == []
    assert all(v is None for v in result['power_curve'].values())


def test_training_load_initialization_and_unknown_days():
    result = training_load({'2026-01-01': 100, '2026-01-03': 50})
    assert len(result) == 3
    assert result[0]['ctl'] == pytest.approx(100 * (1-math.exp(-1/42)), abs=.001)
    assert result[0]['tsb'] == 0
    assert result[1]['tss'] is None
    assert result[1]['assumed_zero'] is True


def test_vi_is_np_over_average_and_undefined_for_no_power_or_zero():
    samples = constant(100, 60)
    for record in samples[30:]:
        record['power'] = 300
    result = analyze(samples, ftp=200)
    assert result['vi'] == pytest.approx(result['np'] / 200, abs=.001)
    assert analyze(constant(0, 60), ftp=200)['vi'] is None
    assert analyze([])['vi'] is None


def test_extreme_sensor_values_cannot_overflow_np_or_fabricate_load():
    samples = constant(1e100, 60)
    result = analyze(samples, ftp=1e-300)
    assert result['avg_power'] is None
    assert result['np'] is None
    assert result['vi'] is None
    assert result['tss'] is None
    assert result['power_recording_seconds'] == 0
    assert any('센서 범위' in warning for warning in result['warnings'])


def test_training_load_known_zero_is_distinct_from_unknown():
    result = training_load({'2026-01-01': 100, '2026-01-02': 0, '2026-01-03': None})
    assert result[1]['tss'] == 0
    assert result[1]['assumed_zero'] is False
    assert result[2]['tss'] is None
    assert result[2]['assumed_zero'] is True
    # TSB is yesterday's fitness minus fatigue, before today's load update.
    assert result[1]['tsb'] == pytest.approx(result[0]['ctl'] - result[0]['atl'], abs=.001)


def test_missing_beginning_of_ride_is_not_reported_as_complete_coverage():
    samples = [{'elapsed_seconds': 60+i, 'power': 200} for i in range(60)]
    result = analyze(samples, ftp=250)
    assert result['duration_seconds'] == 120
    assert result['power_coverage'] == .5
    assert result['avg_power'] == 200
    assert result['np'] is None
    assert result['power_curve']['60'] == 200
