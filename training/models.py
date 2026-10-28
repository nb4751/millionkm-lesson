import secrets
import uuid
from pathlib import Path
from django.conf import settings
from django.db import models
from django.utils import timezone

def athlete_code():
    return 'R-' + secrets.token_hex(4).upper()

def upload_path(instance, filename):
    return f'athletes/{instance.athlete_id}/{uuid.uuid4().hex}{Path(filename).suffix.lower()}'

class Athlete(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='athlete')
    name = models.CharField('이름', max_length=80)
    code = models.CharField('선수 ID', max_length=30, unique=True, default=athlete_code)
    group = models.CharField('그룹', max_length=80, blank=True)
    discipline = models.CharField('종목', max_length=40, default='로드')
    weight_kg = models.FloatField('체중(kg)', null=True, blank=True)
    weight_date = models.DateField('체중 측정일', null=True, blank=True)
    is_demo = models.BooleanField('가상 데이터', default=False)
    is_active = models.BooleanField('활성 상태', default=True)
    coach_note = models.TextField('코치 메모', blank=True)
    consent_at = models.DateTimeField(null=True, blank=True)
    consent_note = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    @property
    def ftp(self):
        record = self.ftp_records.filter(is_active=True).order_by('-date','-id').first()
        return record.value if record else None

    def __str__(self):
        return f'{self.name} ({self.code})'

class FTPRecord(models.Model):
    KINDS = [('measured','테스트 측정'),('garmin','Garmin 추정'),('coach','코치 설정')]
    athlete = models.ForeignKey(Athlete, on_delete=models.CASCADE, related_name='ftp_records')
    value = models.FloatField('FTP(W)')
    kind = models.CharField('출처', max_length=16, choices=KINDS, default='coach')
    method = models.CharField('측정 방법', max_length=150, blank=True)
    date = models.DateField('적용일', default=timezone.localdate)
    comment = models.TextField('설명', blank=True)
    is_active = models.BooleanField('훈련존 기준으로 사용', default=True)

class Activity(models.Model):
    athlete = models.ForeignKey(Athlete, on_delete=models.CASCADE, related_name='activities')
    title = models.CharField(max_length=180)
    start_time = models.DateTimeField()
    duration_seconds = models.FloatField(default=0)
    distance_km = models.FloatField(null=True, blank=True)
    samples = models.JSONField(default=list)
    metrics = models.JSONField(default=dict)
    warnings = models.JSONField(default=list)
    laps = models.JSONField(default=list)
    source_metadata = models.JSONField(default=dict)
    source_hash = models.CharField(max_length=64)
    original_file = models.FileField(upload_to=upload_path, blank=True)
    kind = models.CharField('훈련 유형', max_length=20, choices=[('personal','개인 훈련'),('center','센터 수업')], default='personal')
    rpe = models.PositiveSmallIntegerField('RPE(1~10)', null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    class Meta:
        ordering = ['-start_time']
        constraints = [models.UniqueConstraint(fields=['athlete','source_hash','start_time'],name='unique_athlete_source_start')]

class Invitation(models.Model):
    athlete = models.ForeignKey(Athlete, on_delete=models.CASCADE)
    token_hash = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    purpose = models.CharField(max_length=12, choices=[('invite','초대'),('reset','비밀번호 재설정')], default='invite')

class AuditLog(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=80)
    athlete = models.ForeignKey(Athlete, null=True, on_delete=models.SET_NULL)
    detail = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)

class DataRequest(models.Model):
    athlete = models.ForeignKey(Athlete, on_delete=models.CASCADE)
    kind = models.CharField('요청', max_length=16, choices=[('export','개인 데이터 제공'),('delete','삭제 요청'),('reset','비밀번호 재설정')])
    status = models.CharField('처리 상태', max_length=16, choices=[('pending','대기'),('done','처리 완료')], default='pending')
    note = models.TextField('요청 내용', blank=True)
    created_at = models.DateTimeField(default=timezone.now)

class Interval(models.Model):
    activity = models.ForeignKey(Activity, on_delete=models.CASCADE, related_name='intervals')
    start_seconds = models.FloatField('시작(초)')
    end_seconds = models.FloatField('종료(초)')
    target_power = models.FloatField('목표 파워(W)', null=True, blank=True)
    note = models.CharField('메모', max_length=200, blank=True)
    metrics = models.JSONField(default=dict)

class LoginAttempt(models.Model):
    key = models.CharField(max_length=64, unique=True)
    count = models.PositiveIntegerField(default=0)
    since = models.DateTimeField(default=timezone.now)

class AthleteAccessLink(models.Model):
    athlete = models.ForeignKey(Athlete, on_delete=models.CASCADE, related_name='access_links')
    token_hash = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)
