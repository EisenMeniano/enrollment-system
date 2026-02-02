from django.contrib import admin
from .models import Subject, StudentFinanceAccount, PreviousTermSubject, Enlistment, EnlistmentSubject, Payment

admin.site.register(Subject)
admin.site.register(StudentFinanceAccount)
admin.site.register(PreviousTermSubject)

class EnlistmentSubjectInline(admin.TabularInline):
    model = EnlistmentSubject
    extra = 0

@admin.register(Enlistment)
class EnlistmentAdmin(admin.ModelAdmin):
    list_display = ("id", "student", "school_year", "semester", "status", "created_at")
    list_filter = ("status", "school_year", "semester")
    search_fields = ("student__username", "student__email")
    inlines = [EnlistmentSubjectInline]

admin.site.register(Payment)
