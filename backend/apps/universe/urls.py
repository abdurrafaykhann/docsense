from django.urls import path

from . import views

W = "workspaces/<int:workspace_id>/universe/"

urlpatterns = [
    path(f"{W}points/", views.Points.as_view(), name="universe-points"),
    path(f"{W}rebuild/", views.Rebuild.as_view(), name="universe-rebuild"),
]
