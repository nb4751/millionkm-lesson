"""Garmin FIT and CSV adapters. All persisted timestamps are UTC."""
import csv
from datetime import datetime, timedelta, timezone
from io import StringIO
import math
from pathlib import Path
import re
from zoneinfo import ZoneInfo

SEOUL = ZoneInfo('Asia/Seoul')
MAX_RECORDS = 200_000


class MappingRequired(ValueError):
    def __init__(self, columns, message='CSV 열을 인식하지 못했습니다. 날짜/시간과 센서 열을 직접 연결해 주세요.'):
        self.columns = list(columns)
        super().__init__(message)


ALIASES = {
    'timestamp': ['timestamp', 'datetime', 'date_time', '시간기록', '측정시각', '시각', '타임스탬프'],
    'start_time': ['date', 'start_time', 'starttime', 'activity date', '날짜', '시작시간', '시작시각', '활동날짜'],
    'elapsed_seconds': ['elapsed_seconds', 'elapsed', 'seconds', 'time', '시간', '경과시간', '경과초', '초'],
    'duration_seconds': ['duration_seconds', 'duration', 'total time', 'moving time', '총시간', '운동시간', '이동시간'],
    'power': ['power', 'watts', 'watt', 'power_w', 'power (w)', '파워', '파워(w)', '파워 (w)', '출력'],
    'heart_rate': ['heart_rate', 'heartrate', 'heart rate', 'hr', '심박', '심박수', '심박수(bpm)'],
    'cadence': ['cadence', 'cadence_rpm', 'rpm', '케이던스', '케이던스(rpm)'],
    'altitude': ['altitude', 'elevation', '고도', '고도(m)'],
    'distance_km': ['distance_km', 'distance', 'distance (km)', '거리', '거리(km)', '거리 (km)'],
    'title': ['title', 'activity name', 'activity_name', '제목', '활동명', '이름'],
    'avg_power': ['avg power', 'average power', 'avg_power', '평균파워', '평균 파워'],
    'max_power': ['max power', 'max_power', '최대파워', '최대 파워'],
    'avg_heart_rate': ['avg hr', 'avg heart rate', 'avg_heart_rate', '평균심박수', '평균 심박수'],
    'max_heart_rate': ['max hr', 'max_heart_rate', '최대심박수', '최대 심박수'],
}


def _normalize(value):
    return re.sub(r'[\s_\-]+', '', str(value).strip().casefold())


def _number(value, default=None):
    if value is None or str(value).strip() in ('', '--', '-', 'N/A', 'null', 'NaN'):
        return default
    text = re.sub(r'\s*(?:watts|bpm|rpm|km|w|m)$', '', str(value).strip(), flags=re.I)
    # Quoted decimal-comma values with one/two decimal places are distinguishable
    # from conventional thousands groups (e.g. 1,234).
    text = text.replace(',', '.') if re.fullmatch(r'\d+,\d{1,2}', text) else text.replace(',', '')
    try:
        result = float(text)
        return result if math.isfinite(result) and result >= 0 else default
    except ValueError:
        return default


def _duration(value):
    if value is None:
        return None
    text = str(value).strip()
    if ':' in text:
        try:
            parts = [float(part) for part in text.split(':')]
            if len(parts) not in (2, 3) or any(not math.isfinite(p) or p < 0 for p in parts):
                return None
            return sum(v * 60 ** i for i, v in enumerate(reversed(parts)))
        except ValueError:
            return None
    return _number(value)


def _datetime(value):
    if isinstance(value, datetime):
        result = value
    else:
        text = str(value).strip()
        korean_pm = '오후' in text
        korean_am = '오전' in text
        text = text.replace('오전 ', '').replace('오후 ', '')
        try:
            result = datetime.fromisoformat(text.replace('Z', '+00:00'))
        except ValueError:
            result = None
            for fmt in ('%Y/%m/%d %H:%M:%S', '%Y-%m-%d %H:%M', '%m/%d/%Y %H:%M:%S', '%Y.%m.%d %H:%M:%S'):
                try:
                    result = datetime.strptime(text, fmt)
                    break
                except ValueError:
                    continue
            if result is None:
                raise ValueError('날짜 형식을 읽을 수 없습니다. 예: 2026-10-28T09:00:00+09:00')
    if not isinstance(value, datetime):
        if korean_pm and result.hour < 12:
            result += timedelta(hours=12)
        if korean_am and result.hour == 12:
            result -= timedelta(hours=12)
    if result.tzinfo is None:
        result = result.replace(tzinfo=SEOUL)
    return result.astimezone(timezone.utc)


def parse_file(data, filename, mapping=None):
    suffix = Path(filename).suffix.lower()
    if suffix == '.fit':
        return _fit(data, filename)
    if suffix == '.csv':
        return _csv(data, filename, mapping)
    raise ValueError('FIT 또는 CSV 파일만 업로드할 수 있습니다.')


def _csv(data, filename, mapping):
    text = None
    for encoding in ('utf-8-sig', 'cp949'):
        try:
            text = data.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if text is None or '\x00' in text:
        raise ValueError('CSV 파일이 아닙니다. UTF-8 또는 CP949 인코딩을 사용해 주세요.')
    if text.lstrip().lower().startswith(('<!doctype', '<html', '<?xml', '#!')):
        raise ValueError('CSV 콘텐츠가 아닙니다.')
    try:
        reader = csv.DictReader(StringIO(text))
        columns = reader.fieldnames
        if not columns or len(columns) > 100 or len(set(columns)) != len(columns):
            raise ValueError('CSV 헤더가 없거나 중복되어 있습니다.')
        rows = []
        for row in reader:
            if len(rows) >= MAX_RECORDS:
                raise ValueError('CSV는 최대 200,000행까지 지원합니다.')
            if None in row:
                raise ValueError('CSV의 열 개수가 일치하지 않습니다. 쉼표가 들어간 값은 큰따옴표로 감싸 주세요.')
            if any(str(value or '').strip() for value in row.values()):
                rows.append(row)
    except csv.Error as error:
        raise ValueError('CSV 구조를 읽을 수 없습니다.') from error
    if not rows:
        raise ValueError('CSV에 데이터 행이 없습니다.')
    normalized = {_normalize(column): column for column in columns}
    selected = {}
    for field, aliases in ALIASES.items():
        for alias in aliases:
            if _normalize(alias) in normalized:
                selected[field] = normalized[_normalize(alias)]
                break
    if mapping:
        for field, column in mapping.items():
            if field in ALIASES and column:
                if column not in columns:
                    raise ValueError(f'선택한 CSV 열이 없습니다: {column}')
                selected[field] = column
    get = lambda row, field: row.get(selected.get(field, ''))
    warnings = []
    # Garmin activity-list exports have one row per activity and contain no sensor stream.
    summary = ('duration_seconds' in selected and ('start_time' in selected or 'timestamp' in selected)
               and 'elapsed_seconds' not in selected)
    if ('start_time' in selected and 'elapsed_seconds' in selected and 'timestamp' not in selected
            and any(field in selected for field in ('avg_power', 'avg_heart_rate'))
            and not any(field in selected for field in ('power', 'heart_rate', 'cadence'))):
        summary = True
    if summary:
        activities = []
        for index, row in enumerate(rows, 2):
            start = _datetime(get(row, 'start_time') or get(row, 'timestamp'))
            duration = _duration(get(row, 'duration_seconds') or get(row, 'elapsed_seconds'))
            if duration is None:
                raise ValueError(f'{index}행의 운동시간을 읽을 수 없습니다.')
            metadata = {'format': 'csv_summary', 'timezone_assumption': '시간대 없는 시각은 Asia/Seoul',
                        'summary': {key: _number(get(row, key)) for key in ('avg_power', 'max_power', 'avg_heart_rate', 'max_heart_rate')}}
            activities.append({'title': get(row, 'title') or Path(filename).stem,
                               'start_time': start, 'duration_seconds': duration,
                               'distance_km': _number(get(row, 'distance_km')), 'samples': [], 'laps': [],
                               'source_metadata': metadata})
        return {'activities': activities, 'warnings': ['활동목록 요약 CSV: 시계열이 없어 NP·TSS·파워커브를 계산하지 않습니다.']}
    if not any(field in selected for field in ('power', 'heart_rate', 'cadence')):
        raise MappingRequired(columns)
    # A timestamp stream or a fixed activity start plus elapsed seconds is required.
    if 'timestamp' not in selected and not ('start_time' in selected and 'elapsed_seconds' in selected):
        # ISO date values in a conventional "time" column are timestamps, not elapsed seconds.
        candidate = get(rows[0], 'elapsed_seconds')
        if candidate and re.match(r'^\d{4}[-/]', str(candidate)):
            selected['timestamp'] = selected.pop('elapsed_seconds')
        else:
            raise MappingRequired(columns, '측정시각(timestamp) 또는 시작시각과 경과초 열을 연결해 주세요.')
    start = _datetime(get(rows[0], 'timestamp') or get(rows[0], 'start_time'))
    samples = []
    for index, row in enumerate(rows, 2):
        try:
            elapsed = ((_datetime(get(row, 'timestamp')) - start).total_seconds()
                       if 'timestamp' in selected else _duration(get(row, 'elapsed_seconds')))
        except ValueError as error:
            raise ValueError(f'{index}행: {error}') from error
        if elapsed is None or elapsed < 0:
            raise ValueError(f'{index}행의 경과시간이 잘못되었거나 시각이 역순입니다.')
        if elapsed > 7 * 24 * 3600:
            raise ValueError('한 활동의 기록 범위는 최대 7일입니다. 활동목록 CSV와 시계열 CSV를 구분해 주세요.')
        sample = {'elapsed_seconds': elapsed}
        for field in ('power', 'heart_rate', 'cadence', 'altitude'):
            raw = get(row, field)
            # Altitude can be below sea level.
            if field == 'altitude' and raw not in (None, ''):
                try:
                    value = float(str(raw).replace(',', ''))
                    sample[field] = value if math.isfinite(value) else None
                except ValueError:
                    sample[field] = None
            else:
                sample[field] = _number(raw)
                maximum = {'power': 10000, 'heart_rate': 300, 'cadence': 400}.get(field)
                if maximum is not None and sample[field] is not None and sample[field] > maximum:
                    sample[field] = None
                    warnings.append(f'{field}의 현실적인 센서 범위를 벗어난 값은 미측정으로 처리했습니다.')
            if raw not in (None, '', '-', '--') and sample[field] is None:
                warnings.append(f'{field}의 숫자가 아닌 값은 미측정으로 처리했습니다.')
        samples.append(sample)
    if any(samples[i]['elapsed_seconds'] <= samples[i-1]['elapsed_seconds'] for i in range(1, len(samples))):
        raise ValueError('중복 또는 역순 시각이 있습니다. 각 행의 기록 시각을 확인해 주세요.')
    deltas = [samples[i]['elapsed_seconds'] - samples[i-1]['elapsed_seconds'] for i in range(1, len(samples))]
    import statistics
    duration = samples[-1]['elapsed_seconds'] + (min(5, statistics.median(deltas)) if deltas else 1)
    return {'activities': [{'title': get(rows[0], 'title') or Path(filename).stem,
                            'start_time': start, 'duration_seconds': duration,
                            'distance_km': _number(get(rows[-1], 'distance_km')),
                            'samples': samples, 'laps': [],
                            'source_metadata': {'format': 'csv_timeseries', 'encoding': encoding,
                                                'original_start_time': get(rows[0], 'timestamp') or get(rows[0], 'start_time'),
                                                'column_mapping': selected,
                                                'timezone_assumption': '시간대 없는 시각은 Asia/Seoul'}}],
            'warnings': list(dict.fromkeys(warnings))}


def _json_safe(value):
    if isinstance(value, datetime):
        return _datetime(value).isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _fit(data, filename):
    from garmin_fit_sdk import Decoder, Stream
    if len(data) < 14 or data[8:12] != b'.FIT':
        raise ValueError('Garmin FIT 파일 헤더가 아닙니다.')
    if not Decoder(Stream.from_byte_array(bytearray(data))).check_integrity():
        raise ValueError('FIT 체크섬(CRC) 검증에 실패했습니다. 원본 파일을 다시 내보내 주세요.')
    messages, errors = Decoder(Stream.from_byte_array(bytearray(data))).read(enable_crc_check=True)
    if errors:
        # A structural decoder error means that trusting a partial activity is unsafe.
        raise ValueError('FIT 메시지를 완전히 해석할 수 없습니다. 손상 여부를 확인해 주세요.')
    records = messages.get('record_mesgs', [])
    sessions = messages.get('session_mesgs', [])
    laps = messages.get('lap_mesgs', [])
    if len(records) > MAX_RECORDS:
        raise ValueError('FIT는 최대 200,000개 센서 기록까지 지원합니다.')
    if not sessions and not records:
        raise ValueError('FIT에 활동 또는 센서 기록이 없습니다.')
    if not sessions:
        sessions = [{'start_time': records[0].get('timestamp'), 'timestamp': records[-1].get('timestamp')}]
    activities = []
    warnings = []
    ignored = [key for key in messages if key not in ('record_mesgs', 'session_mesgs', 'lap_mesgs', 'event_mesgs', 'file_id_mesgs', 'device_info_mesgs', 'activity_mesgs')]
    if ignored:
        warnings.append('추가 FIT 메시지는 원본에 보존됩니다: ' + ', '.join(ignored[:12]))
    for session in sessions:
        raw_start = session.get('start_time') or (records[0].get('timestamp') if records else None)
        if raw_start is None:
            raise ValueError('FIT 활동 시작시각을 찾을 수 없습니다.')
        start = _datetime(raw_start)
        end = _datetime(session.get('timestamp')) if session.get('timestamp') else None
        samples = []
        for record in records:
            if record.get('timestamp') is None:
                warnings.append('시각이 없는 FIT record를 제외했습니다.')
                continue
            time = _datetime(record['timestamp'])
            if time < start or (end is not None and time > end):
                continue
            sample = {'elapsed_seconds': (time - start).total_seconds(),
                      'power': _number(record.get('power')),
                      'heart_rate': _number(record.get('heart_rate')),
                      'cadence': _number(record.get('cadence')),
                      'altitude': record.get('enhanced_altitude', record.get('altitude'))}
            # Deliberately omit GPS coordinates: no location consent is collected in MVP.
            samples.append(sample)
        # Mark stopped timer intervals. No power is synthesized during stops.
        events = sorted((e for e in messages.get('event_mesgs', []) if e.get('timestamp') and e.get('event') == 'timer'),
                        key=lambda e: _datetime(e['timestamp']))
        paused, event_index = False, 0
        for sample in samples:
            time = start + timedelta(seconds=sample['elapsed_seconds'])
            while event_index < len(events) and _datetime(events[event_index]['timestamp']) <= time:
                event_type = events[event_index].get('event_type')
                if event_type in ('stop', 'stop_all', 'stop_disable', 'stop_disable_all'):
                    paused = True
                elif event_type == 'start':
                    paused = False
                event_index += 1
            if paused:
                sample['paused'] = True
        # A record exactly at the session end is an instantaneous endpoint,
        # not an extra invented second of activity.
        if samples and end is not None and start + timedelta(seconds=samples[-1]['elapsed_seconds']) == end:
            samples[-1]['interval_seconds'] = 0.0
        activity_laps = []
        for lap in laps:
            if lap.get('start_time'):
                lap_start = _datetime(lap['start_time'])
                if lap_start < start or (end is not None and lap_start > end):
                    continue
                activity_laps.append({'start_seconds': (lap_start - start).total_seconds(),
                                      'duration_seconds': lap.get('total_timer_time', lap.get('total_elapsed_time')),
                                      'avg_power': lap.get('avg_power'), 'avg_heart_rate': lap.get('avg_heart_rate'),
                                      'avg_cadence': lap.get('avg_cadence')})
        duration = session.get('total_elapsed_time')
        if duration is None:
            duration = samples[-1]['elapsed_seconds'] + 1 if samples else ((end - start).total_seconds() if end else 0)
        distance = session.get('total_distance')
        if distance is None and records:
            distance = records[-1].get('distance')
        metadata = {'format': 'fit', 'decoder': 'garmin-fit-sdk', 'crc_verified': True,
                    'session': _json_safe(session), 'device_info': _json_safe(messages.get('device_info_mesgs', [])),
                    'record_fields': sorted({key for record in records for key in record if key not in ('position_lat', 'position_long')})}
        activities.append({'title': f'{Path(filename).stem}' + (f' · {len(activities)+1}' if len(sessions) > 1 else ''),
                           'start_time': start, 'duration_seconds': duration,
                           'distance_km': distance / 1000 if distance is not None else None,
                           'samples': samples, 'laps': activity_laps, 'source_metadata': metadata})
    return {'activities': activities, 'warnings': list(dict.fromkeys(warnings))}
