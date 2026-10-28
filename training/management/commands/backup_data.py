"""Consistent SQLite + original-upload backup, without environment secrets."""
import hashlib
import json
import os
import sqlite3
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


def create_backup(output):
    output = Path(output).expanduser().resolve()
    if output.exists():
        raise CommandError("기존 백업을 덮어쓰지 않습니다. 새 파일명을 지정하세요.")
    output.parent.mkdir(parents=True, exist_ok=True)
    db_config = settings.DATABASES["default"]
    if db_config["ENGINE"] != "django.db.backends.sqlite3":
        raise CommandError("이 명령은 SQLite용입니다. 서버 DB는 해당 DB의 공식 백업 도구를 사용하세요.")
    db_path = Path(db_config["NAME"]).resolve()
    if not db_path.is_file():
        raise CommandError("백업할 SQLite 데이터베이스를 찾을 수 없습니다.")
    media_root = Path(settings.MEDIA_ROOT).resolve()
    checksums = {}
    handle, temp_archive = tempfile.mkstemp(prefix=".lesson-backup-", suffix=".zip", dir=output.parent)
    os.close(handle)
    try:
        with tempfile.TemporaryDirectory(prefix="lesson-db-backup-") as temporary:
            snapshot = Path(temporary) / "db.sqlite3"
            # SQLite backup API obtains a consistent database snapshot even when serving readers.
            with sqlite3.connect(str(db_path)) as source, sqlite3.connect(str(snapshot)) as destination:
                source.backup(destination)
            with zipfile.ZipFile(temp_archive, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.write(snapshot, "db.sqlite3")
                checksums["db.sqlite3"] = hashlib.sha256(snapshot.read_bytes()).hexdigest()
                if media_root.is_dir():
                    for original in sorted(media_root.rglob("*")):
                        if original.is_symlink():
                            raise CommandError("업로드 폴더에 심볼릭 링크가 있어 안전한 백업을 중단했습니다.")
                        if not original.is_file():
                            continue
                        resolved = original.resolve()
                        if resolved == output or resolved == Path(temp_archive).resolve():
                            continue
                        relative = original.relative_to(media_root)
                        name = "uploads/" + relative.as_posix()
                        archive.write(original, name)
                        checksums[name] = hashlib.sha256(original.read_bytes()).hexdigest()
                manifest = {
                    "format": "lesson-lab-backup-v1", "created_at": datetime.now(timezone.utc).isoformat(),
                    "database": "db.sqlite3", "uploads": "uploads/", "sha256": checksums,
                    "note": "개인정보 포함. 암호화되지 않은 백업이므로 접근통제 저장소에 보관하세요. 환경 비밀키는 별도 보관하세요.",
                }
                archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        # Atomically publish only a complete, validated archive.
        with zipfile.ZipFile(temp_archive) as archive:
            if archive.testzip() is not None:
                raise CommandError("백업 ZIP 무결성 검사에 실패했습니다.")
        os.replace(temp_archive, output)
        try:
            output.chmod(0o600)
        except OSError:
            pass
        return output
    finally:
        if os.path.exists(temp_archive):
            os.unlink(temp_archive)


class Command(BaseCommand):
    help = "SQLite 일관성 스냅샷과 원본 업로드를 ZIP으로 백업합니다. 비밀키/.env는 포함하지 않습니다."

    def add_arguments(self, parser):
        parser.add_argument("--output", required=True, help="새 ZIP 백업 파일 경로")

    def handle(self, *args, **options):
        destination = create_backup(options["output"])
        self.stdout.write(self.style.SUCCESS(f"백업 완료: {destination}"))
