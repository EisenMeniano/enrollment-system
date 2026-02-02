from django import forms
from .models import Subject

class EnlistmentCreateForm(forms.Form):
    school_year = forms.CharField(max_length=20, help_text="e.g., 2025-2026")
    semester = forms.CharField(max_length=20, help_text="e.g., 1st / 2nd / Summer")
    notes = forms.CharField(widget=forms.Textarea, required=False)

class ReturnReasonForm(forms.Form):
    reason = forms.CharField(widget=forms.Textarea, help_text="Reason / action needed", max_length=2000)

class SubjectSelectForm(forms.Form):
    subjects = forms.ModelMultipleChoiceField(
        queryset=Subject.objects.all().order_by("code"),
        widget=forms.CheckboxSelectMultiple,
        help_text="Select subjects to add for next semester."
    )

class PaymentForm(forms.Form):
    reference = forms.CharField(max_length=100, required=False, help_text="Optional payment reference / OR number.")
