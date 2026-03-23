from django import forms
from .models import Subject, Category, SchoolYear, Semester, Program, EnlistmentBlock

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
    enlistment_amount = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=0,
        help_text="Set enlistment fee amount (Down Payment page).",
        label="Enlistment Fee Amount",
    )
    tuition_amount = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=0,
        help_text="Set tuition/enrollment fee amount (My Payment page).",
        label="Tuition Fee Amount",
    )


class FinanceBlockSetupForm(forms.Form):
    block_name = forms.CharField(
        max_length=120,
        help_text="Example: BSCS1 (Block 1)",
    )
    tuition_amount = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=0,
        label="Block Tuition Amount",
        help_text="Final tuition amount for this block.",
    )
    enlistment_amount = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=0,
        label="Enlistment Fee Amount",
        help_text="Required. Finance sets this before adviser final approval.",
    )
    schedule_lines = forms.CharField(
        widget=forms.Textarea(
            attrs={
                "rows": 6,
                "placeholder": "ENG 101 - 7:30 - 9:00\nMATH - 9:00 - 2:20",
            }
        ),
        label="Schedule (eg ENG 101 - 7:30 - 9:00)",
        help_text="One entry per line. Schedule is optional (defaults to TBA).",
    )


class StudentBlockSelectForm(forms.Form):
    block = forms.ModelChoiceField(
        queryset=EnlistmentBlock.objects.none(),
        empty_label="Select block / schedule",
    )

    def __init__(self, *args, block_queryset=None, **kwargs):
        super().__init__(*args, **kwargs)
        if block_queryset is not None:
            self.fields["block"].queryset = block_queryset


class StudentSubjectSelectForm(forms.Form):
    subjects = forms.ModelMultipleChoiceField(
        queryset=Subject.objects.all().order_by("code"),
        widget=forms.CheckboxSelectMultiple,
        help_text="Select the subjects you want to take.",
    )

    def __init__(self, *args, subject_queryset=None, **kwargs):
        super().__init__(*args, **kwargs)
        if subject_queryset is not None:
            self.fields["subjects"].queryset = subject_queryset
