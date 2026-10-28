from django.contrib import admin
from .models import Athlete,Activity,FTPRecord,AuditLog,DataRequest,Interval

@admin.register(Athlete)
class AthleteAdmin(admin.ModelAdmin):
    list_display=['code','name','group','is_active','is_demo']
    search_fields=['code','name']
    list_filter=['is_demo','is_active','group']

@admin.register(DataRequest)
class DataRequestAdmin(admin.ModelAdmin):
    list_display=['athlete','kind','status','created_at']
    list_filter=['status','kind']

@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display=['actor','action','athlete','created_at']
    readonly_fields=['actor','action','athlete','detail','created_at']
    def has_add_permission(self,request): return False
    def has_change_permission(self,request,obj=None): return False
    def has_delete_permission(self,request,obj=None): return False

admin.site.register(FTPRecord)
admin.site.site_header='권순영 코치 · 개인정보 관리'
admin.site.site_title='LESSON LAB 관리'
