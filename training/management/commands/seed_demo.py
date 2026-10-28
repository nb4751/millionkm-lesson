"""Create clearly labelled fictional data without modifying real athlete records."""
import csv
import hashlib
import math
from datetime import datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from training.analysis import analyze
from training.models import Activity, Athlete, FTPRecord


class Command(BaseCommand):
    help = "가상 선수 3명과 샘플 활동 18개를 생성합니다. 실제 계정이나 기본 비밀번호를 만들지 않습니다."

    @transaction.atomic
    def handle(self, *args, **options):
        created_count = 0
        # Stable source hashes keep repeated invocations idempotent across dates.
        day = timezone.localdate() - timedelta(days=14)
        for number, letter in enumerate("ABC"):
            code = f"DEMO-{letter}"
            athlete, new = Athlete.objects.get_or_create(
                code=code,
                defaults={
                    "name": f"가상선수 {letter}", "group": "샘플 데이터",
                    "discipline": "road", "weight_kg": 60 + number * 8,
                    "weight_date": day, "is_demo": True,
                    "coach_note": "기능 확인용 가상 선수입니다. 실제 선수 기록과 혼합하지 마세요.",
                },
            )
            if not athlete.is_demo:
                self.stderr.write(f"{code}: 기존 실제 선수 데이터 보존을 위해 건너뜁니다.")
                continue
            ftp = 200 + number * 25
            ftp_record, _ = FTPRecord.objects.get_or_create(
                athlete=athlete, method="가상 데이터", kind="coach",
                defaults={"date": day, "value": ftp, "is_active": True,
                          "comment": "분석 기능 확인을 위한 가상 FTP"},
            )
            athlete_day = ftp_record.date
            ftp = ftp_record.value
            for index in range(6):
                digest = hashlib.sha256(f"lesson-lab-demo-v1:{letter}:{index}".encode()).hexdigest()
                if Activity.objects.filter(athlete=athlete, source_hash=digest).exists():
                    continue
                start = datetime.combine(athlete_day + timedelta(days=index * 2), time(18, 0), ZoneInfo("Asia/Seoul"))
                samples = []
                for second in range(600):
                    interval = 40 if 180 <= second < 240 or 360 <= second < 420 else 0
                    power = max(0, round(ftp * (0.65 + index * 0.012) + 12 * math.sin(second / 30) + interval))
                    samples.append({
                        "elapsed_seconds": second, "power": power,
                        "heart_rate": round(118 + number * 3 + second / 55 + interval / 3),
                        "cadence": round(84 + 5 * math.sin(second / 20)),
                        "altitude": round(20 + 4 * math.sin(second / 60), 1),
                    })
                metrics = analyze(samples, ftp=ftp, weight=athlete.weight_kg)
                metrics.update({
                    "ftp_used": ftp, "ftp_source": ftp_record.kind,
                    "ftp_policy": "가상 데이터 생성 시 기준 FTP", "weight_used": athlete.weight_kg,
                })
                Activity.objects.create(
                    athlete=athlete, title=f"[가상] {letter} 선수 {'인터벌' if index % 2 else '지속주'} {index + 1}",
                    start_time=start, duration_seconds=600, distance_km=4.5 + number * 0.3,
                    samples=samples, metrics=metrics, warnings=["실제 훈련이 아닌 가상 샘플 데이터입니다."],
                    source_hash=digest, source_metadata={"source": "seed_demo", "fictional": True},
                    kind="center" if index % 2 else "personal",
                )
                created_count += 1

        sample_dir = Path(settings.APP_DATA_DIR) / "samples"
        sample_dir.mkdir(parents=True, exist_ok=True)
        sample_path = sample_dir / "가상_라이딩_업로드_예제.csv"
        if not sample_path.exists():
            with sample_path.open("w", encoding="utf-8-sig", newline="") as output:
                writer = csv.writer(output)
                writer.writerow(["timestamp", "power", "heart_rate", "cadence"])
                start = datetime.combine(day, time(9, 0), ZoneInfo("Asia/Seoul"))
                for second in range(600):
                    writer.writerow([(start + timedelta(seconds=second)).isoformat(), 150 + second % 20, 125 + second % 8, 88])
        self.stdout.write(self.style.SUCCESS(
            f"가상 선수 3명 준비, 활동 {created_count}개 새로 생성. 재실행 시 기존 기록을 보존합니다.\n"
            f"업로드 연습 CSV: {sample_path}\n"
            "기본 비밀번호 계정은 생성하지 않았습니다. 로컬 코치 모드는 로그인 없이 사용합니다.\n"
            "계정 보호 모드가 필요할 때만 createsuperuser로 별도 코치 계정을 만드세요."
        ))
