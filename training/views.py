import hashlib
import json
import logging
import tempfile
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login as auth_login, logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.db import transaction
from django.db.models import F
from django.http import Http404, HttpResponse, FileResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST
from .models import Athlete, Activity, FTPRecord, Invitation, AuditLog, DataRequest, Interval, LoginAttempt, AthleteAccessLink
from .forms import AthleteForm, FTPForm, UploadForm, ActivateForm, RequestForm, IntervalForm
from .services import issue_invitation, ftp_for_activity, summarize
from .analysis import analyze, training_load
from .parsers import parse_file, MappingRequired
from .exports import workbook_bytes

logger = logging.getLogger(__name__)

def audit(request,action,athlete=None,detail=''):
    AuditLog.objects.create(actor=request.user if request.user.is_authenticated else None,action=action,athlete=athlete,detail=detail[:1000])

def coach(request):
    if not request.user.is_staff:
        raise Http404()

def allowed_athletes(request):
    if request.user.is_staff:
        return Athlete.objects.all()
    if getattr(request,'is_portal',False):
        return Athlete.objects.filter(is_active=True)
    return Athlete.objects.filter(user=request.user,is_active=True)

def athlete_or_404(request,pk):
    return get_object_or_404(allowed_athletes(request),pk=pk)

def activity_or_404(request,pk):
    return get_object_or_404(Activity.objects.select_related('athlete').filter(athlete__in=allowed_athletes(request)),pk=pk)

def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    form=AuthenticationForm(request,data=request.POST or None)
    if request.method=='POST':
        username=request.POST.get('username','')[:150].lower()
        # Neither proxy headers nor raw usernames are stored as rate limit identifiers.
        identifiers=['user:'+username,'ip:'+request.META.get('REMOTE_ADDR','unknown')]
        attempts=[]
        for identifier in identifiers:
            key=hashlib.sha256(identifier.encode()).hexdigest()
            a,_=LoginAttempt.objects.get_or_create(key=key)
            if a.since < timezone.now()-timedelta(minutes=15):
                a.count=0; a.since=timezone.now(); a.save()
            attempts.append(a)
        if any(a.count>=10 for a in attempts):
            form.add_error(None,'로그인 시도가 너무 많습니다. 15분 뒤 다시 시도하세요.')
            return render(request,'login.html',{'form':form},status=429)
        if form.is_valid():
            u=form.get_user()
            if not u.is_staff and not Athlete.objects.filter(user=u,is_active=True).exists():
                form.add_error(None,'비활성 계정입니다. 코치에게 문의하세요.')
            else:
                LoginAttempt.objects.filter(pk__in=[a.pk for a in attempts]).delete()
                auth_login(request,u); audit(request,'login')
                return redirect('dashboard')
        LoginAttempt.objects.filter(pk__in=[a.pk for a in attempts]).update(count=F('count')+1)
    return render(request,'login.html',{'form':form})

@require_POST
def logout_view(request):
    if request.user.is_authenticated:
        audit(request,'logout')
    auth_logout(request)
    return redirect('login')

def period(request):
    today=timezone.localdate()
    try:
        start=date.fromisoformat(request.GET.get('start') or (today-timedelta(days=27)).isoformat())
        end=date.fromisoformat(request.GET.get('end') or today.isoformat())
        if end<start or (end-start).days>3660:
            raise ValueError()
    except ValueError:
        raise Http404('올바른 날짜 범위를 입력하세요 (최대 10년).')
    return start,end

def in_period(qs,start,end):
    tz=ZoneInfo('Asia/Seoul')
    return qs.filter(start_time__gte=datetime.combine(start,time.min,tz),start_time__lt=datetime.combine(end+timedelta(days=1),time.min,tz))

def scoped_selection(request):
    athletes=allowed_athletes(request).order_by('is_demo','name')
    # Demo and live records never contribute to the same dashboard/report.
    dataset=request.GET.get('dataset','real')
    if dataset not in ('real','demo'):
        dataset='real'
    if request.user.is_staff or getattr(request,'is_portal',False):
        athletes=athletes.filter(is_demo=dataset=='demo')
    ids=request.GET.getlist('athletes')
    if ids:
        if any(not (v.isascii() and v.isdecimal()) for v in ids):
            raise Http404()
        permitted=set(athletes.values_list('id',flat=True))
        if not set(map(int,ids)).issubset(permitted):
            raise Http404()
        athletes=athletes.filter(pk__in=ids)
    return athletes,dataset

@login_required
def dashboard(request):
    athletes,dataset=scoped_selection(request)
    start,end=period(request)
    activities=in_period(Activity.objects.filter(athlete__in=athletes).select_related('athlete'),start,end)
    stats=summarize(activities)
    stats['athlete_count']=athletes.count()
    stats['missing_count']=athletes.exclude(activities__start_time__gte=timezone.now()-timedelta(days=7)).count()
    return render(request,'dashboard.html',{'athletes':athletes,'activities':activities[:12],'stats':stats,'demo':dataset=='demo','start':start.isoformat(),'end':end.isoformat(),'data_requests':DataRequest.objects.filter(status='pending',athlete__in=athletes) if request.user.is_staff else []})

@login_required
def athlete_add(request):
    coach(request)
    form=AthleteForm(request.POST or None)
    if request.method=='POST' and form.is_valid():
        a=form.save(); audit(request,'athlete_created',a)
        return redirect('athlete_detail',pk=a.pk)
    return render(request,'athlete_form.html',{'form':form,'title':'새 선수 등록'})

@login_required
def athlete_edit(request,pk):
    coach(request); a=athlete_or_404(request,pk)
    form=AthleteForm(request.POST or None,instance=a)
    if request.method=='POST' and form.is_valid():
        form.save()
        if a.user:
            a.user.is_active=a.is_active; a.user.save(update_fields=['is_active'])
        audit(request,'athlete_updated',a)
        return redirect('athlete_detail',pk=pk)
    return render(request,'athlete_form.html',{'form':form,'athlete':a,'title':'선수 정보 수정'})

@login_required
def athlete_detail(request,pk):
    a=athlete_or_404(request,pk); start,end=period(request)
    acts=in_period(a.activities.all(),start,end)
    summary=summarize(acts); summary['current_ftp']=a.ftp
    # Explicitly initialized from zero on the start of the selected range.
    daily={}
    for act in acts:
        if act.metrics.get('tss') is not None:
            d=timezone.localtime(act.start_time).date().isoformat()
            daily[d]=daily.get(d,0)+act.metrics['tss']
    loads={}
    for offset in range((end-start).days+1):
        d=start+timedelta(days=offset)
        loads[d.isoformat()]=daily.get(d.isoformat())
    load=training_load(loads) if daily else []
    return render(request,'athlete_detail.html',{'athlete':a,'activities':acts,'ftp_history':a.ftp_records.order_by('-date','-id'),'load':load,'summary':summary,'start':start.isoformat(),'end':end.isoformat()})

@login_required
def ftp_add(request,pk):
    coach(request); a=athlete_or_404(request,pk)
    form=FTPForm(request.POST or None)
    if request.method=='POST' and form.is_valid():
        f=form.save(commit=False); f.athlete=a; f.save()
        # Past activities retain the FTP applied at upload for reproducibility.
        audit(request,'ftp_added',a,f'{f.value}W / {f.kind}')
        messages.success(request,'FTP 이력을 저장했습니다. 기존 활동은 업로드 당시 FTP를 유지합니다.')
        return redirect('athlete_detail',pk=pk)
    return render(request,'generic_form.html',{'form':form,'title':'FTP 출처와 기준 설정'})

@login_required
@require_POST
def athlete_invite(request,pk):
    coach(request); a=athlete_or_404(request,pk)
    if not a.is_active:
        raise Http404()
    import secrets
    raw=secrets.token_urlsafe(32)
    with transaction.atomic():
        a=Athlete.objects.select_for_update().get(pk=a.pk)
        AthleteAccessLink.objects.filter(athlete=a,revoked_at=None).update(revoked_at=timezone.now())
        AthleteAccessLink.objects.create(athlete=a,token_hash=hashlib.sha256(raw.encode()).hexdigest(),expires_at=timezone.now()+timedelta(days=90))
    audit(request,'personal_link_issued',a,'90일 유효 / 이전 링크 회수')
    base=settings.APP_PUBLIC_URL
    if not base:
        messages.warning(request,'외부 주소가 아직 설정되지 않았습니다. 이 링크는 로컬 시험용입니다. 선수에게 보내려면 APP_PUBLIC_URL과 별도 공유 서버를 설정하세요.')
        base=request.build_absolute_uri('/').rstrip('/')
    return render(request,'invitation_created.html',{'athlete':a,'invite_url':base+reverse('shared_workspace',args=[raw])})

def shared_workspace(request,token):
    hashed=hashlib.sha256(token.encode()).hexdigest()
    link=get_object_or_404(AthleteAccessLink.objects.select_related('athlete__user'),token_hash=hashed,revoked_at=None,expires_at__gt=timezone.now(),athlete__is_active=True)
    from django.contrib.auth import get_user_model
    a=link.athlete
    with transaction.atomic():
        a=Athlete.objects.select_for_update().get(pk=a.pk)
        if not a.user_id:
            user=get_user_model().objects.create_user(username='athlete_'+a.code,password=None)
            a.user=user; a.save(update_fields=['user'])
        else:
            user=a.user
    auth_login(request,user,backend='django.contrib.auth.backends.ModelBackend')
    request.session['athlete_link_id']=link.pk
    request.session.set_expiry(12*3600)
    audit(request,'personal_link_access',a)
    return redirect('athlete_detail',pk=a.pk)

def activate(request,token):
    hashed=hashlib.sha256(token.encode()).hexdigest()
    inv=get_object_or_404(Invitation.objects.select_related('athlete__user'),token_hash=hashed,used_at=None,expires_at__gt=timezone.now(),athlete__is_active=True)
    reset_user=inv.athlete.user if inv.purpose=='reset' else None
    form=ActivateForm(request.POST or None,reset_user=reset_user)
    if request.method=='POST' and form.is_valid():
        with transaction.atomic():
            claimed=Invitation.objects.filter(pk=inv.pk,used_at=None,expires_at__gt=timezone.now()).update(used_at=timezone.now())
            if not claimed:
                raise Http404()
            a=inv.athlete
            if reset_user:
                u=reset_user; u.set_password(form.cleaned_data['password1']); u.save()
            else:
                if a.user_id:
                    raise Http404()
                u=form.save(); a.user=u
            a.consent_at=timezone.now(); a.save()
            AuditLog.objects.create(actor=u,action='account_activated',athlete=a)
        messages.success(request,'계정 설정을 완료했습니다. 로그인하세요.')
        return redirect('login')
    return render(request,'invite.html',{'form':form,'athlete':inv.athlete})

@login_required
def upload(request):
    form=UploadForm(request.POST or None,request.FILES or None)
    choices=allowed_athletes(request).filter(is_active=True)
    form.fields['athlete'].queryset=choices
    if request.method=='GET' and request.GET.get('athlete','').isdigit():
        selected=choices.filter(pk=request.GET['athlete']).first()
        if selected:
            form.fields['athlete'].initial=selected.pk
    if not request.user.is_staff and not getattr(request,'is_portal',False):
        form.fields['athlete'].widget=__import__('django.forms',fromlist=['HiddenInput']).HiddenInput()
    columns=[]
    if request.method=='POST' and form.is_valid():
        a=form.cleaned_data['athlete'] if request.user.is_staff or getattr(request,'is_portal',False) else choices.first()
        if a is None:
            form.add_error('athlete','선수를 선택하세요.')
        else:
            f=form.cleaned_data['file']
            try:
                if f.size>settings.MAX_UPLOAD_BYTES:
                    raise ValueError('파일은 20MB 이하여야 합니다.')
                if Path(f.name).suffix.lower() not in ('.fit','.csv'):
                    raise ValueError('FIT·CSV 파일만 업로드할 수 있습니다.')
                data=f.read(settings.MAX_UPLOAD_BYTES+1)
                if len(data)>settings.MAX_UPLOAD_BYTES:
                    raise ValueError('파일 크기를 초과했습니다.')
                digest=hashlib.sha256(data).hexdigest()
                # Public upload mode needs bounded storage and request rates.
                if getattr(request,'is_portal',False):
                    ipkey=hashlib.sha256(('upload:'+request.META.get('REMOTE_ADDR','unknown')).encode()).hexdigest()
                    attempt,_=LoginAttempt.objects.get_or_create(key=ipkey)
                    if attempt.since<timezone.now()-timedelta(hours=1):
                        attempt.count=0; attempt.since=timezone.now(); attempt.save()
                    if attempt.count>=50:
                        raise ValueError('시간당 업로드 한도(50회)에 도달했습니다. 잠시 후 다시 시도하세요.')
                    LoginAttempt.objects.filter(pk=attempt.pk).update(count=F('count')+1)
                max_storage=int(__import__('os').getenv('APP_MAX_STORAGE_MB','2048'))*1024*1024
                used=sum(p.stat().st_size for p in Path(settings.MEDIA_ROOT).rglob('*') if p.is_file())
                if used+len(data)>max_storage:
                    raise ValueError('원본 파일 저장공간 한도에 도달했습니다. 코치가 백업·정리 후 다시 올리세요.')
                if Activity.objects.filter(athlete=a,source_hash=digest).exists():
                    raise ValueError('이미 등록한 파일입니다. 중복 합산하지 않았습니다.')
                parsed=parse_file(data,f.name,form.cleaned_data['mapping'])
                if not parsed['activities']:
                    raise ValueError('분석할 활동이 없습니다.')
                if len(parsed['activities'])>1000:
                    raise ValueError('한 파일은 최대 1,000개 활동까지 지원합니다. 기간을 나누어 내보내세요.')
                if used+len(data)*len(parsed['activities'])>max_storage:
                    raise ValueError('활동별 원본 저장 시 저장공간 한도를 초과합니다. 활동 수를 줄이거나 코치가 공간을 정리하세요.')
                # Each source timestamp is unique per athlete even when a file is reformatted.
                if any(a.activities.filter(start_time=x['start_time']).exists() for x in parsed['activities']):
                    raise ValueError('같은 시작 시각의 활동이 이미 있습니다. 원본을 확인하세요.')
                created=[]
                try:
                    with transaction.atomic():
                        for item in parsed['activities']:
                            ftp=ftp_for_activity(a,item['start_time'])
                            weight=a.weight_kg if a.weight_date and a.weight_date<=timezone.localtime(item['start_time']).date() else None
                            metrics=analyze(item.get('samples',[]),ftp.value if ftp else None,weight)
                            summary=item.get('source_metadata',{}).get('summary',{})
                            for key in ['avg_power','max_power','avg_heart_rate','max_heart_rate']:
                                if metrics.get(key) is None and summary.get(key) is not None:
                                    metrics[key]=summary[key]
                            metrics.update({'ftp_used':ftp.value if ftp else None,'ftp_source':ftp.kind if ftp else None,'ftp_policy':'업로드 시 활동일 이전의 최신 기준 FTP','weight_used':weight})
                            obj=Activity.objects.create(athlete=a,title=item['title'][:180],start_time=item['start_time'],duration_seconds=item['duration_seconds'],distance_km=item.get('distance_km'),samples=item.get('samples',[]),laps=item.get('laps',[]),metrics=metrics,warnings=parsed.get('warnings',[])+metrics.get('warnings',[]),source_metadata=item.get('source_metadata',{}),source_hash=digest,kind=form.cleaned_data['kind'],rpe=form.cleaned_data['rpe'])
                            obj.original_file.save(f.name,ContentFile(data),save=True); created.append(obj)
                except Exception:
                    for obj in created:
                        obj.original_file.delete(save=False)
                    raise
                audit(request,'upload',a,f'{len(created)}개 활동')
                messages.success(request,f'{len(created)}개 활동을 분석했습니다.')
                return redirect('activity_detail',pk=created[0].pk)
            except MappingRequired as e:
                columns=e.columns; form.add_error(None,str(e))
            except ValueError as e:
                form.add_error(None,str(e))
    return render(request,'upload.html',{'form':form,'columns':columns})

@login_required
def activity_detail(request,pk):
    a=activity_or_404(request,pk)
    audit(request,'activity_view',a.athlete,str(pk))
    return render(request,'activity_detail.html',{'activity':a,'metrics':a.metrics,'samples_json':a.samples,'intervals':a.intervals.all()})

@login_required
def interval_add(request,pk):
    coach(request); a=activity_or_404(request,pk)
    form=IntervalForm(request.POST or None)
    if request.method=='POST' and form.is_valid():
        i=form.save(commit=False)
        if i.end_seconds>a.duration_seconds:
            form.add_error('end_seconds','활동 길이를 초과합니다.')
        else:
            samples=[dict(s,elapsed_seconds=s['elapsed_seconds']-i.start_seconds) for s in a.samples if i.start_seconds<=s['elapsed_seconds']<i.end_seconds]
            i.activity=a; i.metrics=analyze(samples,a.metrics.get('ftp_used'),a.metrics.get('weight_used'))
            avg=i.metrics.get('avg_power'); i.metrics['achievement']=round(avg/i.target_power*100,1) if avg is not None and i.target_power else None
            i.save(); audit(request,'interval_created',a.athlete,str(i.pk))
            return redirect('activity_detail',pk=pk)
    return render(request,'generic_form.html',{'form':form,'title':'수동 인터벌 분석'})

@login_required
def original_file(request,pk):
    a=activity_or_404(request,pk)
    if getattr(request,'is_portal',False):
        raise Http404('위치정보가 포함될 수 있는 원본은 공통 공유 화면에서 제공하지 않습니다.')
    if not a.original_file:
        raise Http404()
    audit(request,'original_download',a.athlete,str(pk))
    return FileResponse(a.original_file.open('rb'),as_attachment=True,filename=f'activity-{a.pk}{Path(a.original_file.name).suffix}',content_type='application/octet-stream')

@login_required
@require_POST
def activity_delete(request,pk):
    a=activity_or_404(request,pk)
    if not request.user.is_staff:
        DataRequest.objects.create(athlete=a.athlete,kind='delete',note=f'활동 {pk} 삭제 요청')
        messages.success(request,'코치에게 삭제 요청을 보냈습니다.')
        return redirect('activity_detail',pk=pk)
    athlete=a.athlete; a.original_file.delete(save=False); a.delete()
    audit(request,'activity_deleted',athlete,str(pk))
    return redirect('athlete_detail',pk=athlete.pk)

def comparison_rows(athletes,activities):
    activities=list(activities); rows=[]
    for a in athletes:
        acts=[x for x in activities if x.athlete_id==a.pk]; s=summarize(acts)
        row={'athlete':a,'ftp':a.ftp,'wkg':round(a.ftp/a.weight_kg,2) if a.ftp and a.weight_kg else None,'hours':s['total_hours'],'tss':s['total_tss'],'activity_count':len(acts)}
        for seconds,key in [(5,'mmp5'),(60,'mmp60'),(300,'mmp300'),(1200,'mmp1200')]:
            values=[x.metrics.get('power_curve',{}).get(str(seconds)) for x in acts]
            values=[v for v in values if v is not None]; row[key]=max(values) if values else None
        rows.append(row)
    return rows

@login_required
def compare(request):
    if not request.user.is_staff and not getattr(request,'is_portal',False):
        raise Http404()
    athletes,dataset=scoped_selection(request); start,end=period(request)
    acts=in_period(Activity.objects.filter(athlete__in=athletes),start,end)
    options=allowed_athletes(request).filter(is_demo=dataset=='demo').order_by('name')
    return render(request,'compare.html',{'athletes':options,'rows':comparison_rows(athletes,acts),'start':start.isoformat(),'end':end.isoformat(),'demo':dataset=='demo','selected_ids':list(athletes.values_list('pk',flat=True))})

@login_required
def export(request):
    athletes,_=scoped_selection(request); start,end=period(request)
    acts=in_period(Activity.objects.filter(athlete__in=athletes).select_related('athlete'),start,end)
    content=workbook_bytes(athletes,acts,comparison_rows(athletes,acts))
    audit(request,'excel_export',detail=f'{start}~{end}')
    response=HttpResponse(content,content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition']='attachment; filename="lesson-report.xlsx"'
    response['Cache-Control']='no-store'
    return response

@login_required
@require_POST
def backup(request):
    coach(request)
    with tempfile.TemporaryDirectory() as folder:
        p=Path(folder)/'backup.zip'; call_command('backup_data',output=str(p))
        content=p.read_bytes()
    audit(request,'backup_download')
    response=HttpResponse(content,content_type='application/zip')
    response['Content-Disposition']='attachment; filename="lesson-backup.zip"'; response['Cache-Control']='no-store'
    return response

@login_required
def account_request(request):
    form=RequestForm(request.POST or None)
    if getattr(request,'is_portal',False) or request.user.is_staff:
        from django import forms
        form.fields['athlete']=forms.ModelChoiceField(label='요청 대상 선수',queryset=allowed_athletes(request))
    if request.method=='POST' and form.is_valid():
        a=form.cleaned_data['athlete'] if getattr(request,'is_portal',False) or request.user.is_staff else get_object_or_404(Athlete,user=request.user,is_active=True)
        obj=form.save(commit=False); obj.athlete=a; obj.save(); audit(request,'data_request',a,obj.kind)
        messages.success(request,'요청을 등록했습니다. 코치가 확인 후 처리합니다.')
        return redirect('dashboard')
    return render(request,'generic_form.html',{'form':form,'title':'데이터 제공·삭제 요청'})

def password_reset_request(request):
    from django import forms
    class ResetForm(forms.Form):
        username=forms.CharField(label='로그인 아이디',max_length=150)
    form=ResetForm(request.POST or None)
    if request.method=='POST' and form.is_valid():
        # Do not reveal whether an account exists; delivery is manual by coach.
        a=Athlete.objects.filter(user__username=form.cleaned_data['username'],is_active=True).first()
        if a and not DataRequest.objects.filter(athlete=a,kind='reset',status='pending').exists():
            DataRequest.objects.create(athlete=a,kind='reset',note='본인 확인 후 재설정 링크 발급 필요')
        messages.success(request,'요청을 접수했습니다. 코치에게 본인 확인 후 재설정 링크를 받으세요.')
        return redirect('login')
    return render(request,'generic_form.html',{'form':form,'title':'비밀번호 재설정 요청'})

@login_required
def athlete_delete(request,pk):
    coach(request); a=athlete_or_404(request,pk)
    if request.method=='POST' and request.POST.get('confirm')==a.code:
        for act in a.activities.all():
            act.original_file.delete(save=False)
        user=a.user; audit(request,'athlete_deleted',a,a.code)
        a.delete()
        if user: user.delete()
        messages.success(request,'선수와 훈련 데이터를 삭제했습니다. 별도 보관한 백업은 보존 정책에 따라 정리하세요.')
        return redirect('dashboard')
    return render(request,'confirm_delete.html',{'athlete':a})

def privacy(request):
    return render(request,'privacy.html')
