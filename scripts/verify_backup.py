"""Verify a Lesson Lab ZIP without extracting any file (Python standard library)."""
import argparse
import hashlib
import json
import re
import stat
import sys
import zipfile
from pathlib import PurePosixPath


def verify(path):
    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        names = [item.filename for item in entries]
        if len(names) != len(set(names)):
            raise ValueError('중복 파일명이 있습니다.')
        if 'manifest.json' not in names or 'db.sqlite3' not in names:
            raise ValueError('백업 매니페스트 또는 DB가 없습니다.')
        if len(entries) > 100_000 or sum(item.file_size for item in entries) > 20 * 1024**3:
            raise ValueError('검증 한도(파일 10만 개/압축 해제 후 20GB)를 초과합니다.')
        for item in entries:
            name = item.filename
            parts = PurePosixPath(name).parts
            if ('\\' in name or ':' in name or name.startswith('/') or '..' in parts
                    or stat.S_ISLNK(item.external_attr >> 16) or item.is_dir()):
                raise ValueError('허용하지 않는 아카이브 경로 또는 형식이 있습니다.')
            if name not in ('manifest.json', 'db.sqlite3') and not name.startswith('uploads/'):
                raise ValueError('알 수 없는 백업 파일이 있습니다.')
        info = archive.getinfo('manifest.json')
        if info.file_size > 20 * 1024**2:
            raise ValueError('매니페스트가 너무 큽니다.')
        manifest = json.loads(archive.read('manifest.json'))
        if manifest.get('format') != 'lesson-lab-backup-v1':
            raise ValueError('지원하지 않는 백업 형식입니다.')
        expected = manifest.get('sha256')
        if not isinstance(expected, dict) or set(expected) != set(names) - {'manifest.json'}:
            raise ValueError('해시 목록과 실제 파일 목록이 다릅니다.')
        for name, checksum in expected.items():
            if not isinstance(checksum, str) or not re.fullmatch(r'[0-9a-f]{64}', checksum):
                raise ValueError('올바르지 않은 해시 형식입니다.')
            digest = hashlib.sha256()
            with archive.open(name) as source:
                for chunk in iter(lambda: source.read(1024 * 1024), b''):
                    digest.update(chunk)
            if digest.hexdigest() != checksum:
                raise ValueError('파일 해시가 일치하지 않습니다.')
    return len(expected)


def main():
    parser = argparse.ArgumentParser(description='백업 ZIP 경로와 SHA-256을 검사합니다. 파일을 추출하지 않습니다.')
    parser.add_argument('backup')
    args = parser.parse_args()
    try:
        count = verify(args.backup)
    except (OSError, ValueError, KeyError, zipfile.BadZipFile, RuntimeError) as error:
        print('검증 실패:', str(error), file=sys.stderr)
        return 1
    print(f'검증 통과: {count}개 파일. 파일을 추출하거나 기존 DB를 변경하지 않았습니다.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
