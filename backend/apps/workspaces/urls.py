from django.urls import path

from . import views

urlpatterns = [
    path("workspaces/", views.WorkspaceListCreate.as_view(), name="workspace-list"),
    path(
        "workspaces/<int:workspace_id>/", views.WorkspaceDetail.as_view(), name="workspace-detail"
    ),
    path("workspaces/<int:workspace_id>/members/", views.MemberList.as_view(), name="member-list"),
    path(
        "workspaces/<int:workspace_id>/members/<int:pk>/",
        views.MemberDetail.as_view(),
        name="member-detail",
    ),
    path("workspaces/<int:workspace_id>/api-keys/", views.ApiKeyList.as_view(), name="apikey-list"),
    path(
        "workspaces/<int:workspace_id>/api-keys/<int:pk>/",
        views.ApiKeyDetail.as_view(),
        name="apikey-detail",
    ),
    path("workspaces/<int:workspace_id>/usage/", views.UsageView.as_view(), name="usage"),
]
