"""Time-weighted cycling metrics. Missing sensor values are never replaced by zero."""
from bisect import bisect_right
from datetime import date, timedelta
import math
import statistics

CURVE_DURATIONS = (5, 10, 30, 60, 180, 300, 600, 1200, 1800, 3600)
SENSOR_LIMITS = {'power': 10_000, 'heart_rate': 300, 'cadence': 400}


def _number(value):
    try:
        value = float(value)
        return value if math.isfinite(value) and value >= 0 else None
    except (ValueError, TypeError):
        return None


def _sensor_value(sample, key):
    value = _number(sample.get(key))
    return value if value is not None and value <= SENSOR_LIMITS.get(key, math.inf) else None


def ftp_zones(ftp):
    """Integer watt ranges with inclusive bounds and no overlap or missing watt."""
    ftp = _number(ftp)
    if not ftp or not 1 <= ftp <= 3000:
        return []
    zones, lower = [], 0
    for index, fraction in enumerate((.55, .75, .90, 1.05, 1.20, 1.50, None), 1):
        upper = math.floor(ftp * fraction + 1e-9) if fraction else None
        zones.append({'name': f'Z{index}', 'min': lower, 'max': upper,
                      'description': f'{lower}W 이상' if upper is None else f'{lower}–{upper}W'})
        if upper is not None:
            lower = upper + 1
    return zones


def _prepare(samples):
    records = []
    warnings = []
    previous = -1
    for sample in samples:
        elapsed = _number(sample.get('elapsed_seconds'))
        if elapsed is None:
            warnings.append('타임스탬프가 없는 기록을 제외했습니다.')
            continue
        if elapsed <= previous:
            warnings.append('중복·역순 타임스탬프가 있어 분석에서 제외했습니다.')
            continue
        records.append((elapsed, sample))
        previous = elapsed
    if not records:
        return [], 0, list(dict.fromkeys(warnings))
    differences = [records[i + 1][0] - t for i, (t, _) in enumerate(records[:-1])]
    # A last record represents one nominal sampling interval, capped at five seconds.
    nominal = min(5.0, statistics.median(differences)) if differences else 1.0
    threshold = max(3.0, nominal * 3)
    segments = []
    for i, (start, record) in enumerate(records):
        dt = records[i + 1][0] - start if i + 1 < len(records) else nominal
        if i + 1 == len(records) and record.get('interval_seconds') is not None:
            dt = _number(record['interval_seconds']) or 0.0
        if dt > threshold:
            warnings.append('기록 공백이 있어 공백을 가로지르는 파워커브를 계산하지 않았습니다.')
            dt = nominal
        segments.append((start, start + dt, record))
    duration = segments[-1][1]
    if segments[0][0] > 0:
        warnings.append('활동 시작과 첫 센서 기록 사이의 공백은 미측정으로 처리했습니다.')
    return segments, duration, list(dict.fromkeys(warnings))


def _blocks(segments, key):
    blocks, current = [], []
    for start, end, sample in segments:
        value = _sensor_value(sample, key)
        if value is None or sample.get('paused'):
            if current:
                blocks.append(current)
                current = []
            continue
        if current and abs(current[-1][1] - start) > 1e-7:
            blocks.append(current)
            current = []
        current.append((start, end, value))
    if current:
        blocks.append(current)
    return blocks


def _integral_function(block):
    starts = [item[0] for item in block]
    totals = [0.0]
    for start, end, value in block:
        totals.append(totals[-1] + (end - start) * value)
    def integral(time):
        if time >= block[-1][1]:
            return totals[-1]
        i = max(0, bisect_right(starts, time) - 1)
        return totals[i] + max(0, time - block[i][0]) * block[i][2]
    return integral


def _best_average(blocks, seconds):
    best = None
    for block in blocks:
        start, end = block[0][0], block[-1][1]
        if end - start + 1e-7 < seconds:
            continue
        integral = _integral_function(block)
        boundaries = [item[0] for item in block] + [end]
        candidates = {start, end - seconds}
        for boundary in boundaries:
            if start <= boundary <= end - seconds:
                candidates.add(boundary)
            if start <= boundary - seconds <= end - seconds:
                candidates.add(boundary - seconds)
        value = max((integral(t + seconds) - integral(t)) / seconds for t in candidates)
        best = value if best is None else max(best, value)
    return best


def analyze(samples, ftp=None, weight=None):
    segments, duration, warnings = _prepare(samples)
    result = {'duration_seconds': round(duration, 3), 'warnings': warnings}
    for field, output in (('power', 'power'), ('heart_rate', 'heart_rate'), ('cadence', 'cadence')):
        valid = [(end - start, _sensor_value(sample, field)) for start, end, sample in segments
                 if _sensor_value(sample, field) is not None and not sample.get('paused')]
        seconds = sum(dt for dt, value in valid)
        result[f'avg_{output}'] = round(sum(dt * value for dt, value in valid) / seconds, 3) if seconds else None
        result[f'max_{output}'] = max((value for dt, value in valid), default=None)
        if field == 'power':
            result['power_recording_seconds'] = round(seconds, 3)
            result['kj'] = round(sum(dt * value for dt, value in valid) / 1000, 3) if seconds else None
    if any(_number(sample.get(field)) is not None and _sensor_value(sample, field) is None
           for _, _, sample in segments for field in SENSOR_LIMITS):
        warnings.append('현실적인 센서 범위를 벗어난 값은 미측정으로 처리했습니다 (파워 10,000W·심박 300bpm·케이던스 400rpm 초과).')
    blocks = _blocks(segments, 'power')
    coverage = result['power_recording_seconds'] / duration if duration else 0
    result['power_coverage'] = round(coverage, 4)
    result['power_curve'] = {str(seconds): _round(_best_average(blocks, seconds)) for seconds in CURVE_DURATIONS}
    # Require a complete contiguous stream; a partial NP would misleadingly characterize a whole ride.
    np = None
    if len(blocks) == 1 and coverage >= .999 and duration >= 30:
        block = blocks[0]
        integral = _integral_function(block)
        start, end = block[0][0], block[-1][1]
        count = int(math.floor(end - start - 30 + 1e-7)) + 1
        fourths = (((integral(start + i + 30) - integral(start + i)) / 30) ** 4 for i in range(count))
        np = (sum(fourths) / count) ** .25
    else:
        warnings.append('NP·IF·TSS 미산출: 30초 이상의 연속적이고 결측 없는 파워 기록이 필요합니다.')
    ftp, weight = _number(ftp), _number(weight)
    if ftp is not None and not 1 <= ftp <= 3000:
        ftp = None
        warnings.append('FTP가 유효 범위(1–3,000W)를 벗어나 IF·TSS·파워존을 계산하지 않았습니다.')
    if weight is not None and not 1 <= weight <= 500:
        weight = None
    intensity = np / ftp if np is not None and ftp else None
    result.update({'np': _round(np), 'if': _round(intensity),
                   'vi': _round(np / result['avg_power']) if np is not None and result['avg_power'] else None,
                   'tss': _round(result['power_recording_seconds'] / 3600 * intensity ** 2 * 100) if intensity is not None else None,
                   'avg_wkg': _round(result['avg_power'] / weight) if result['avg_power'] is not None and weight else None})
    zones = ftp_zones(ftp)
    seconds_total = result['power_recording_seconds']
    for zone in zones:
        # Floating readings use exact percentage cut points; labels describe integer watts.
        idx = int(zone['name'][1:]) - 1
        bounds = (.55, .75, .9, 1.05, 1.2, 1.5, math.inf)
        low = bounds[idx - 1] * ftp if idx else -1
        high = bounds[idx] * ftp
        seconds = sum(end - start for start, end, sample in segments
                      if not sample.get('paused') and (value := _sensor_value(sample, 'power')) is not None and low < value <= high)
        zone.update(seconds=round(seconds, 3), percentage=round(seconds / seconds_total * 100, 2) if seconds_total else 0)
    result['zones'] = zones
    return result


def _round(value):
    return round(value, 3) if value is not None else None


def training_load(daily_tss):
    """42/7-day exponential estimates, initialized at zero; missing days are unknown.

    Accept date/ISO keys. A missing date is assumed zero load by this model, and
    explicitly marked as assumed; null input loads remain unknown.
    """
    if not daily_tss:
        return []
    daily = {(date.fromisoformat(day) if isinstance(day, str) else day): value for day, value in daily_tss.items()}
    current, last = min(daily), max(daily)
    ctl = atl = 0.0
    output = []
    while current <= last:
        load = daily.get(current)
        known = load is not None
        # Unknown days are a modelling assumption, never a measured rest day.
        model_load = float(load) if known else 0.0
        tsb = ctl - atl
        ctl += (1 - math.exp(-1 / 42)) * (model_load - ctl)
        atl += (1 - math.exp(-1 / 7)) * (model_load - atl)
        output.append({'date': current.isoformat(), 'tss': load, 'ctl': round(ctl, 3),
                       'atl': round(atl, 3), 'tsb': round(tsb, 3), 'assumed_zero': not known})
        current += timedelta(days=1)
    return output
