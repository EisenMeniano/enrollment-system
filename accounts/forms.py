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
            "address_line",
            "city",
            "province",
            "postal_code",
            "country",
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
        ]
