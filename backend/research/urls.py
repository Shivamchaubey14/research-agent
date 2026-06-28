from django.urls import path

from .views import (
    DocumentListCreateView,
    RunCancelView,
    RunDetailView,
    RunListCreateView,
)

urlpatterns = [
    path("runs", RunListCreateView.as_view(), name="run-list"),
    path("runs/<uuid:pk>", RunDetailView.as_view(), name="run-detail"),
    path("runs/<uuid:pk>/cancel", RunCancelView.as_view(), name="run-cancel"),
    path("documents", DocumentListCreateView.as_view(), name="document-list"),
]
