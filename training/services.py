import hashlib
import secrets
from datetime import timedelta
from django.utils import timezone
from .models import Invitation, FTPRecord

def issue_invitation(athlete, purpose='invite'):
    raw = secrets.token_urlsafe(32)
    Invitation.objects.filter(athlete=athlete,purpose=purpose,used_at=None).update(used_at=timezone.now())
    Invitation.objects.create(athlete=athlete,token_hash=hashlib.sha256(raw.encode()).hexdigest(),expires_at=timezone.now()+timedelta(hours=48),purpose=purpose)
    return raw

def ftp_for_activity(athlete, start_time):
    r = FTPRecord.objects.filter(athlete=athlete,is_active=True,date__lte=timezone.localtime(start_time).date()).order_by('-date','-id').first()
    return r

def summarize(activities):
    acts = list(activities)
    tss = [a.metrics.get('tss') for a in acts if a.metrics.get('tss') is not None]
    return {'activity_count':len(acts),'total_hours':round(sum(a.duration_seconds for a in acts)/3600,1),'total_distance':round(sum(a.distance_km or 0 for a in acts),1),'total_tss':round(sum(tss),1) if tss else None,'missing_count':sum(a.metrics.get('avg_power') is None for a in acts)}
