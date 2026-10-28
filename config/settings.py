import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
# Small .env loader: the actual environment always takes precedence.
if (BASE_DIR / '.env').exists():
    for line in (BASE_DIR / '.env').read_text(encoding='utf-8-sig').splitlines():
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            os.environ.setdefault(k.strip(), v.strip().strip('\"\''))
DEBUG = os.getenv('APP_DEBUG', '1') == '1'
DATA_DIR = Path(os.getenv('APP_DATA_DIR') or str(BASE_DIR / 'data')).resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)
APP_DATA_DIR = DATA_DIR
SECRET_KEY = os.getenv('APP_SECRET_KEY', '')
if not SECRET_KEY:
    if not DEBUG:
        raise RuntimeError('운영 환경에는 APP_SECRET_KEY를 설정하세요.')
    key_path = DATA_DIR / '.development-key'
    if not key_path.exists():
        try:
            fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'w') as f:
                f.write(secrets.token_urlsafe(64))
        except FileExistsError:
            pass
    SECRET_KEY = key_path.read_text().strip()
ALLOWED_HOSTS = [v.strip() for v in os.getenv('APP_ALLOWED_HOSTS', 'localhost,127.0.0.1,testserver').split(',') if v.strip()]
INSTALLED_APPS = ['django.contrib.admin','django.contrib.auth','django.contrib.contenttypes','django.contrib.sessions','django.contrib.messages','django.contrib.staticfiles','training']
MIDDLEWARE = ['django.middleware.security.SecurityMiddleware','whitenoise.middleware.WhiteNoiseMiddleware','django.contrib.sessions.middleware.SessionMiddleware','django.middleware.common.CommonMiddleware','django.middleware.csrf.CsrfViewMiddleware','django.contrib.auth.middleware.AuthenticationMiddleware','training.middleware.LocalCoachMiddleware','django.contrib.messages.middleware.MessageMiddleware','django.middleware.clickjacking.XFrameOptionsMiddleware']
ROOT_URLCONF = 'config.urls'
TEMPLATES = [{'BACKEND':'django.template.backends.django.DjangoTemplates','DIRS':[BASE_DIR / 'templates'],'APP_DIRS':True,'OPTIONS':{'context_processors':['django.template.context_processors.request','django.contrib.auth.context_processors.auth','django.contrib.messages.context_processors.messages']}}]
WSGI_APPLICATION = 'config.wsgi.application'
DATABASES = {'default':{'ENGINE':'django.db.backends.sqlite3','NAME':DATA_DIR / 'db.sqlite3','OPTIONS':{'timeout':30}}}
AUTH_PASSWORD_VALIDATORS = [{'NAME':'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},{'NAME':'django.contrib.auth.password_validation.MinimumLengthValidator','OPTIONS':{'min_length':10}},{'NAME':'django.contrib.auth.password_validation.CommonPasswordValidator'},{'NAME':'django.contrib.auth.password_validation.NumericPasswordValidator'}]
LANGUAGE_CODE = 'ko-kr'
TIME_ZONE = 'Asia/Seoul'
USE_I18N = True
USE_TZ = True
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'
MEDIA_ROOT = DATA_DIR / 'uploads'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'dashboard'
LOGOUT_REDIRECT_URL = 'login'
DATA_UPLOAD_MAX_MEMORY_SIZE = 22 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 1024 * 1024
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_AGE = 12 * 3600
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
APP_SECURE = os.getenv('APP_SECURE', '0') == '1'
APP_LOCAL_COACH = os.getenv('APP_LOCAL_COACH', '1') == '1'
APP_OPEN_PORTAL = os.getenv('APP_OPEN_PORTAL', '1') == '1'
APP_PUBLIC_URL = os.getenv('APP_PUBLIC_URL','').rstrip('/')
if APP_LOCAL_COACH and (APP_SECURE or os.getenv('APP_TRUST_PROXY','0') == '1'):
    raise RuntimeError('외부 공개 서버는 APP_LOCAL_COACH=0으로 실행하세요. 코치 전용 로컬 서버와 포트를 분리해야 합니다.')
SESSION_COOKIE_SECURE = APP_SECURE
CSRF_COOKIE_SECURE = APP_SECURE
SECURE_SSL_REDIRECT = APP_SECURE
SECURE_HSTS_SECONDS = 31536000 if APP_SECURE else 0
CSRF_TRUSTED_ORIGINS = [s for s in os.getenv('APP_CSRF_TRUSTED_ORIGINS','').split(',') if s]
# Enable ONLY when a trusted local reverse proxy strips untrusted forwarded headers.
if os.getenv('APP_TRUST_PROXY', '0') == '1':
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
