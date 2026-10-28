from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.http import HttpResponse
from .models import AthleteAccessLink

class LocalCoachMiddleware:
    """Password-free owner only on the private, loopback-bound local listener.

    Never expose that listener through a tunnel. A second public process must
    disable APP_LOCAL_COACH, as documented in the Windows/public launch scripts.
    """
    def __init__(self,get_response): self.get_response=get_response
    def __call__(self,request):
        request.is_portal=False
        local=settings.APP_LOCAL_COACH and request.META.get('REMOTE_ADDR') in ('127.0.0.1','::1')
        # Share paths must switch into athlete scope, even when tested locally.
        shared=request.session.get('athlete_link_id')
        if shared:
            valid=AthleteAccessLink.objects.filter(pk=shared,revoked_at=None,expires_at__gt=timezone.now(),athlete__is_active=True,athlete__user=request.user).exists()
            if not valid and not request.path.startswith('/s/'):
                request.session.flush()
                from django.contrib.auth.models import AnonymousUser
                request.user=AnonymousUser()
                return HttpResponse('이 개인 링크는 만료 또는 회수되었습니다. 코치에게 새 링크를 받으세요.',status=403)
        if local and not shared and not request.path.startswith('/s/') and not request.user.is_authenticated:
            User=get_user_model()
            user,created=User.objects.get_or_create(username='__local_coach__',defaults={'is_staff':True,'is_superuser':True,'first_name':'권순영 코치'})
            if created:
                user.set_unusable_password(); user.save(update_fields=['password'])
            request.user=user
        if settings.APP_OPEN_PORTAL and not request.user.is_authenticated and not request.path.startswith(('/s/','/login/','/admin/','/activate/')):
            User=get_user_model()
            user,created=User.objects.get_or_create(username='__shared_portal__',defaults={'first_name':'공유 보관함'})
            if created:
                user.set_unusable_password(); user.save(update_fields=['password'])
            request.user=user
            request.is_portal=True
        response=self.get_response(request)
        # same-origin keeps Chrome HTTP form Origins valid for Django CSRF;
        # it still prevents sharing training URLs with external destinations.
        response['Referrer-Policy']='same-origin'
        if request.user.is_authenticated or request.path.startswith('/s/'):
            response['Cache-Control']='no-store'
        return response
