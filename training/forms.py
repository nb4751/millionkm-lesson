import json
from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from .models import Athlete, FTPRecord, DataRequest, Interval

class AthleteForm(forms.ModelForm):
    class Meta:
        model = Athlete
        fields = ['name','group','discipline','weight_kg','weight_date','is_active','coach_note','consent_note']
        widgets = {'weight_date':forms.DateInput(attrs={'type':'date'}),'coach_note':forms.Textarea(attrs={'rows':3}),'consent_note':forms.Textarea(attrs={'rows':2})}
    def clean_weight_kg(self):
        v = self.cleaned_data['weight_kg']
        if v is not None and not 15 <= v <= 250:
            raise forms.ValidationError('체중은 15~250kg 범위로 입력하세요.')
        return v
    def clean(self):
        d = super().clean()
        if d.get('weight_kg') and not d.get('weight_date'):
            self.add_error('weight_date','체중 측정일을 입력하세요.')
        return d

class FTPForm(forms.ModelForm):
    class Meta:
        model = FTPRecord
        fields = ['value','kind','method','date','comment','is_active']
        widgets = {'date':forms.DateInput(attrs={'type':'date'})}
    def clean_value(self):
        v = self.cleaned_data['value']
        if not 30 <= v <= 700:
            raise forms.ValidationError('FTP는 30~700W 범위로 입력하세요.')
        return v

class UploadForm(forms.Form):
    athlete = forms.ModelChoiceField(label='선수', queryset=Athlete.objects.none(), required=False)
    file = forms.FileField(label='FIT 또는 CSV 파일 (최대 20MB)')
    mapping = forms.CharField(label='CSV 열 매핑 (JSON, 자동 인식 실패 시)', required=False, widget=forms.Textarea(attrs={'rows':3,'placeholder':'{"timestamp":"기록시각", "power":"출력"}'}))
    kind = forms.ChoiceField(label='훈련 유형', choices=[('personal','개인 훈련'),('center','센터 수업')])
    rpe = forms.IntegerField(label='RPE (선택, 1~10)', min_value=1, max_value=10, required=False)
    def clean_mapping(self):
        raw = self.cleaned_data['mapping']
        if not raw:
            return None
        try:
            v = json.loads(raw)
            if not isinstance(v,dict) or not all(isinstance(k,str) and isinstance(x,str) for k,x in v.items()):
                raise ValueError()
            return v
        except (ValueError,TypeError):
            raise forms.ValidationError('열 매핑은 {"power":"파워열"} 형식의 JSON 객체여야 합니다.')

class ActivateForm(UserCreationForm):
    consent = forms.BooleanField(label='개인정보 처리 안내를 확인했고 훈련 데이터 처리에 동의합니다. 미성년자는 필요한 보호자 동의를 코치에게 제출했습니다.')
    class Meta:
        model = User
        fields = ['username','password1','password2']
    def __init__(self,*args,reset_user=None,**kwargs):
        self.reset_user = reset_user
        super().__init__(*args,**kwargs)
        if reset_user:
            self.fields['username'].initial = reset_user.username
            self.fields['username'].disabled = True
    def clean_username(self):
        v = self.cleaned_data['username']
        if self.reset_user:
            return self.reset_user.username
        if User.objects.filter(username=v).exists():
            raise forms.ValidationError('이미 사용 중인 아이디입니다.')
        return v

class RequestForm(forms.ModelForm):
    class Meta:
        model = DataRequest
        fields = ['kind','note']

class IntervalForm(forms.ModelForm):
    class Meta:
        model = Interval
        fields = ['start_seconds','end_seconds','target_power','note']
    def clean(self):
        d = super().clean()
        if d.get('start_seconds',0) < 0 or d.get('end_seconds',0) <= d.get('start_seconds',0):
            raise forms.ValidationError('종료는 시작보다 커야 하며 시작은 0초 이상이어야 합니다.')
        if d.get('target_power') is not None and d['target_power'] <= 0:
            self.add_error('target_power','목표 파워는 0보다 커야 합니다.')
        return d
