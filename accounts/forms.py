from django import forms
from .models import User, StudentProfile


class UserProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["first_name", "last_name", "email"]

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip()
        return email


class PersonalDetailsUserForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["first_name", "last_name", "email"]


class PersonalDetailsProfileForm(forms.ModelForm):
    class Meta:
        model = StudentProfile
        fields = [
            "middle_name",
            "extension_name",
            "gender",
            "birth_date",
            "place_of_birth",
            "civil_status",
            "citizenship",
            "dual_citizenship",
            "religion",
            "mobile_no",
            "facebook_name",
            "facebook_link",
        ]
        widgets = {
            "birth_date": forms.DateInput(attrs={"type": "date"}),
        }


class AddressDetailsForm(forms.ModelForm):
    class Meta:
        model = StudentProfile
        fields = [
            "current_address_line",
            "current_country",
            "current_province",
            "current_city",
            "current_postal_code",
            "same_as_current",
            "permanent_address_line",
            "permanent_country",
            "permanent_province",
            "permanent_city",
            "permanent_postal_code",
        ]


class CourseDetailsForm(forms.ModelForm):
    class Meta:
        model = StudentProfile
        fields = [
            "program",
            "year_level",
            "campus",
            "college",
            "curriculum",
            "intake",
            "learning_modality",
            "advisor_name",
            "mentor_name",
        ]


class PhotoSignatureForm(forms.ModelForm):
    class Meta:
        model = StudentProfile
        fields = ["photo_file", "signature_file"]
