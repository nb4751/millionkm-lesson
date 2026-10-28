from django.contrib import admin
from django.urls import path
from training import views as v

urlpatterns = [
    path('s/<str:token>/',v.shared_workspace,name='shared_workspace'),
    path('admin/',admin.site.urls),path('',v.dashboard,name='dashboard'),
    path('login/',v.login_view,name='login'),path('logout/',v.logout_view,name='logout'),
    path('athletes/new/',v.athlete_add,name='athlete_add'),
    path('athletes/<int:pk>/',v.athlete_detail,name='athlete_detail'),
    path('athletes/<int:pk>/edit/',v.athlete_edit,name='athlete_edit'),
    path('athletes/<int:pk>/invite/',v.athlete_invite,name='athlete_invite'),
    path('athletes/<int:pk>/ftp/',v.ftp_add,name='ftp_add'),
    path('athletes/<int:pk>/delete/',v.athlete_delete,name='athlete_delete'),
    path('activate/<str:token>/',v.activate,name='activate'),
    path('upload/',v.upload,name='upload'),path('activities/<int:pk>/',v.activity_detail,name='activity_detail'),
    path('activities/<int:pk>/original/',v.original_file,name='original_file'),
    path('activities/<int:pk>/delete/',v.activity_delete,name='activity_delete'),
    path('activities/<int:pk>/interval/',v.interval_add,name='interval_add'),
    path('compare/',v.compare,name='compare'),path('export/',v.export,name='export'),
    path('backup/',v.backup,name='backup'),path('account/request/',v.account_request,name='account_request'),
    path('password-reset/',v.password_reset_request,name='password_reset_request'),path('privacy/',v.privacy,name='privacy'),
]
