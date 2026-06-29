from django.urls import path

from .views import (
    DocumentListCreateView,
    RunCancelView,
    RunDetailView,
    RunEventsView,
    RunListCreateView,
)

urlpatterns = [
    path("runs", RunListCreateView.as_view(), name="run-list"),
    path("runs/<uuid:pk>", RunDetailView.as_view(), name="run-detail"),
    path("runs/<uuid:pk>/cancel", RunCancelView.as_view(), name="run-cancel"),
    path("runs/<uuid:pk>/events", RunEventsView.as_view(), name="run-events"),
    path("documents", DocumentListCreateView.as_view(), name="document-list"),
]
