from django import forms
from .models import Subject, Category, SchoolYear, Semester, Program

class EnlistmentCreateForm(forms.Form):
    category = forms.ModelChoiceField(
        queryset=Category.objects.filter(is_active=True).order_by("name"),
        empty_label="Select category",
    )
    program = forms.ModelChoiceField(
        queryset=Program.objects.filter(is_active=True).order_by("name"),
        empty_label="Select program",
    )
    school_year = forms.ModelChoiceField(
        queryset=SchoolYear.objects.filter(is_active=True).order_by("-label"),
        empty_label="Select school year",
    )
    semester = forms.ModelChoiceField(
        queryset=Semester.objects.filter(is_active=True).order_by("name"),
        empty_label="Select semester",
    )
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
    amount = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=0,
        help_text="Enter payment amount.",
    )
    reference = forms.CharField(max_length=100, required=False, help_text="Optional payment reference / OR number.")

class FinanceAmountForm(forms.Form):
    amount = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=0,
        help_text="Set the amount the student needs to pay.",
    )

class StudentSubjectSelectForm(forms.Form):
    subjects = forms.ModelMultipleChoiceField(
        queryset=Subject.objects.all().order_by("code"),
        widget=forms.CheckboxSelectMultiple,
        help_text="Select the subjects you want to take.",
    )
