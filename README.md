# 권순영 코치 개인레슨 데이터 관리

사이클 선수의 FIT·CSV 훈련 기록을 한눈에 보는 한국어 웹프로그램입니다. **로그인 없이 선수 이름을 선택해 파일을 올리고 분석**합니다. Garmin에서 내려받은 파일을 사용하므로 Garmin 비밀번호나 자동 연동은 필요하지 않습니다.

코치는 자기 PC에서 전체 관리를 합니다. 선수가 직접 사용할 때는 **공통 주소 하나**를 보내고 이름을 선택하게 할 수 있습니다. 기본 공통 모드에서는 주소를 아는 누구나 활성 선수 이름·기록을 보고 업로드·비교·엑셀 출력을 할 수 있습니다. 선수 간 기록을 서로 공유하는 운영 방식입니다. 선수 수정·삭제·백업은 코치 전용입니다.

- [Windows 설치와 사용 설명서](README_한국어.md)
- [PC 외부 접속 / 인터넷 서버 배포](docs/배포.md)
- [개인정보와 운영 범위](docs/개인정보_운영.md)
- [백업·복구](docs/백업_복구.md)
- [분석 지표와 제한](docs/분석_제한.md)

Python 3.12 / Django 5.2 / SQLite / Garmin FIT SDK / openpyxl 기반입니다.

```bash
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo
python manage.py runserver 127.0.0.1:8000
```

`seed_demo`는 가상 선수 3명과 샘플 활동을 만듭니다. 외부 사용에는 HTTPS 연결과 코치 자동접속을 끈 별도 공유 서버가 필요합니다. 코치 PC의 관리 포트는 인터넷에 공개하지 않습니다. 운영 주소·호스팅 계정은 포함되지 않습니다. 선수별 비공개 운영이 필요하면 `APP_OPEN_PORTAL=0`으로 바꾸고 개인 공유 링크를 사용할 수 있습니다.
