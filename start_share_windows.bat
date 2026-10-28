@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
where conda >nul 2>&1
if errorlevel 1 (
    echo [안내] Anaconda Prompt에서 이 파일을 실행하세요.
    pause
    exit /b 1
)
call conda activate kwon-lesson
if errorlevel 1 goto failed
set APP_LOCAL_COACH=0
set APP_DEBUG=0
set APP_SECURE=1
set APP_TRUST_PROXY=1
python manage.py check
if errorlevel 1 goto failed
echo.
echo 선수 외부 공유용 서버를 127.0.0.1:8001 에서 실행합니다.
echo .env의 운영 비밀키, 실제 도메인과 HTTPS 주소가 필요합니다.
echo HTTPS 터널은 반드시 8001 포트에 연결하세요. 8000은 코치 전용입니다.
echo 기본 공통 주소 모드에서는 모든 활성 선수 기록을 서로 볼 수 있습니다.
echo 코치 화면에서 등록한 선수 이름을 선택해 업로드합니다.
echo 이 창과 터널을 종료하면 외부 업로드가 중단됩니다.
echo.
waitress-serve --listen=127.0.0.1:8001 --trusted-proxy=127.0.0.1 --trusted-proxy-headers=x-forwarded-proto config.wsgi:application
if errorlevel 1 goto failed
exit /b 0
:failed
echo [오류] 외부 공유 서버를 실행하지 못했습니다. docs의 배포 안내와 .env를 확인하세요.
pause
exit /b 1
