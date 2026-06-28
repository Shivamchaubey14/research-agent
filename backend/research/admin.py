from django.contrib import admin

from .models import Citation, Document, Report, ResearchRun


class CitationInline(admin.TabularInline):
    model = Citation
    extra = 0


@admin.register(ResearchRun)
class ResearchRunAdmin(admin.ModelAdmin):
    list_display = ["id", "user", "status", "depth", "total_tokens", "cost_usd", "created_at"]
    list_filter = ["status", "depth", "created_at"]
    search_fields = ["id", "question", "user__email"]
    readonly_fields = ["id", "created_at", "started_at", "ended_at"]


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ["id", "run", "created_at"]
    inlines = [CitationInline]
    readonly_fields = ["id", "created_at"]


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ["id", "user", "filename", "status", "chunk_count", "created_at"]
    list_filter = ["status", "created_at"]
    search_fields = ["id", "filename", "user__email"]
    readonly_fields = ["id", "created_at"]
