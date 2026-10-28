@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
where conda >nul 2>&1
if errorlevel 1 (
    echo [안내] Miniconda를 설치한 뒤 Anaconda Prompt에서 이 파일을 실행하세요.
    pause
    exit /b 1
)
call conda run -n kwon-lesson python --version >nul 2>&1
if errorlevel 1 (
    call conda env create -f environment.yml
    if errorlevel 1 goto failed
)
call conda activate kwon-lesson
if errorlevel 1 goto failed
python -m pip install -r requirements.txt
if errorlevel 1 goto failed
if not exist .env copy .env.example .env >nul
python manage.py migrate
if errorlevel 1 goto failed
python manage.py collectstatic --noinput
if errorlevel 1 goto failed
echo.
echo 설치 완료. 기존 계정은 변경하지 않았습니다.
echo 로컬 코치 화면은 로그인 없이 사용할 수 있습니다.
echo 가상 데이터가 필요하면: python manage.py seed_demo
echo 이후 start_windows.bat를 실행하세요.
pause
exit /b 0
:failed
echo.
echo [오류] 설치를 완료하지 못했습니다. 위 오류 메시지를 확인하세요.
pause
exit /b 1
