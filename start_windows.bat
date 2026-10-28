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
set APP_LOCAL_COACH=1
set APP_SECURE=0
set APP_TRUST_PROXY=0
set APP_ALLOWED_HOSTS=localhost,127.0.0.1
python manage.py check
if errorlevel 1 goto failed
echo.
echo 권순영 코치 개인레슨 데이터 관리 - 코치 PC 전용
echo 이 PC에서 http://127.0.0.1:8000 을 열고 선수 이름을 선택하세요.
echo 로그인 없이 사용할 수 있습니다.
echo 이 8000 포트는 외부 터널에 연결하면 안 됩니다.
echo 선수 외부 접속은 별도 start_share_windows.bat와 HTTPS가 필요합니다.
echo 이 창을 닫거나 Ctrl+C를 누르면 서버가 종료됩니다.
echo.
waitress-serve --listen=127.0.0.1:8000 config.wsgi:application
if errorlevel 1 goto failed
exit /b 0
:failed
echo [오류] 서버가 실행되지 않았습니다. setup_windows.bat와 설정 파일을 확인하세요.
pause
exit /b 1
