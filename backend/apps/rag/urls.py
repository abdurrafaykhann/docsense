from django.urls import path

from . import views

W = "workspaces/<int:workspace_id>/chat/"

urlpatterns = [
    path(f"{W}ask/", views.Ask.as_view(), name="chat-ask"),
    path(f"{W}conversations/", views.ConversationList.as_view(), name="conversations"),
    path(f"{W}conversations/<int:pk>/", views.ConversationDetail.as_view(), name="conversation"),
    path(f"{W}reindex/", views.Reindex.as_view(), name="chat-reindex"),
]
