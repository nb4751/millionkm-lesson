from datetime import datetime, timedelta, timezone
from pathlib import Path
import pytest
from training.parsers import parse_file, MappingRequired


def test_csv_timestamp_seoul_and_sensor_missing():
    data = 'timestamp,power,heart_rate,cadence\n2026-10-28 09:00:00,250,140,90\n2026-10-28 09:00:01,,141,91\n'
    result = parse_file(data.encode(), 'ride.csv')['activities'][0]
    assert result['start_time'] == datetime(2026,10,28,0,0,tzinfo=timezone.utc)
    assert result['samples'][1]['power'] is None
    assert result['samples'][1]['elapsed_seconds'] == 1
    assert result['duration_seconds'] == 2


def test_explicit_timezone_preserved_in_utc():
    result = parse_file(b'timestamp,power\n2026-10-28T12:00:00-04:00,200\n', 'ride.csv')
    assert result['activities'][0]['start_time'].hour == 16


def test_cp949_and_explicit_column_mapping():
    data = '시작,초수,출력값,심박계\n2026-10-28 09:00:00,0,200,135\n2026-10-28 09:00:00,2,220,140\n'.encode('cp949')
    with pytest.raises(MappingRequired) as error:
        parse_file(data, 'ride.csv')
    assert '출력값' in error.value.columns
    result = parse_file(data, 'ride.csv', {'start_time': '시작', 'elapsed_seconds': '초수', 'power': '출력값', 'heart_rate': '심박계'})
    assert result['activities'][0]['samples'][1]['power'] == 220
    assert result['activities'][0]['source_metadata']['encoding'] == 'cp949'


def test_garmin_activity_summary_does_not_fake_samples():
    data = 'Activity Type,Date,Title,Distance,Time,Avg HR,Avg Power\nCycling,2026-10-28 09:00:00,실내,32.5,01:00:00,140,200\n'
    activity = parse_file(data.encode(), 'activities.csv')['activities'][0]
    assert activity['duration_seconds'] == 3600
    assert activity['distance_km'] == 32.5
    assert activity['samples'] == []
    assert activity['source_metadata']['summary']['avg_power'] == 200


def make_fit():
    # Official SDK encoder creates record/session/lap messages and valid header/file CRCs.
    from garmin_fit_sdk import Encoder
    start = datetime(2026,10,28,0,0,tzinfo=timezone.utc)
    encoder = Encoder()
    encoder.write_mesg({'mesg_num': 0, 'type': 'activity', 'manufacturer': 'garmin', 'product': 1, 'time_created': start})
    for i in range(61):
        encoder.write_mesg({'mesg_num': 20, 'timestamp': start+timedelta(seconds=i),
                            'power': 200+i, 'heart_rate': 140, 'cadence': 90,
                            'distance': i*10, 'altitude': 100})
    encoder.write_mesg({'mesg_num': 19, 'start_time': start, 'timestamp': start+timedelta(seconds=60),
                        'total_elapsed_time': 60, 'total_timer_time': 60, 'avg_power': 230,
                        'avg_heart_rate': 140, 'avg_cadence': 90})
    encoder.write_mesg({'mesg_num': 18, 'start_time': start, 'timestamp': start+timedelta(seconds=60),
                        'sport': 'cycling', 'total_elapsed_time': 60, 'total_timer_time': 60,
                        'total_distance': 600, 'avg_power': 230})
    return bytes(encoder.close())


def test_official_sdk_fit_records_sessions_laps_and_crc():
    data = make_fit()
    result = parse_file(data, 'virtual.fit')
    activity = result['activities'][0]
    assert activity['start_time'] == datetime(2026,10,28,0,0,tzinfo=timezone.utc)
    assert activity['duration_seconds'] == 60
    assert activity['distance_km'] == .6
    assert len(activity['samples']) == 61
    assert activity['samples'][1]['power'] == 201
    assert activity['samples'][1]['heart_rate'] == 140
    assert activity['laps'][0]['avg_power'] == 230
    assert activity['source_metadata']['crc_verified'] is True
    from training.analysis import analyze
    assert analyze(activity['samples'], ftp=250)['power_recording_seconds'] == 60
    corrupted = bytearray(data)
    corrupted[-1] ^= 1
    with pytest.raises(ValueError, match='CRC'):
        parse_file(corrupted, 'bad.fit')


def test_reject_untrusted_content_and_non_finite_and_reverse_times():
    with pytest.raises(ValueError):
        parse_file(b'MZ executable', 'ride.fit')
    with pytest.raises(ValueError):
        parse_file(b'<html>not csv</html>', 'ride.csv')
    with pytest.raises(ValueError):
        parse_file(b'timestamp,power\n2026-01-01T00:00:01Z,200\n2026-01-01T00:00:00Z,200\n', 'ride.csv')
    with pytest.raises(ValueError):
        parse_file(b'x', 'ride.exe')


def test_unrecognized_mapping_lists_real_columns():
    with pytest.raises(MappingRequired) as error:
        parse_file(b'a,b\n1,2\n','unknown.csv')
    assert error.value.columns == ['a','b']


def test_decimal_comma_and_korean_pm_are_parsed_without_unit_changes():
    data = 'timestamp,power\n2026-10-28 오후 01:00:00,"200,5"\n'.encode()
    activity = parse_file(data, 'ride.csv')['activities'][0]
    assert activity['start_time'] == datetime(2026,10,28,4,0,tzinfo=timezone.utc)
    assert activity['samples'][0]['power'] == 200.5


def test_extreme_csv_sensor_value_is_missing_with_explanation():
    result = parse_file(b'timestamp,power,heart_rate,cadence\n2026-10-28T00:00:00Z,1e100,9999,9999\n','ride.csv')
    sample = result['activities'][0]['samples'][0]
    assert sample['power'] is None
    assert sample['heart_rate'] is None
    assert sample['cadence'] is None
    assert any('센서 범위' in warning for warning in result['warnings'])
