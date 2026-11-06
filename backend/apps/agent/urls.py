from django.urls import path

from . import views

urlpatterns = [
    path("workspaces/<int:workspace_id>/agent/ask/", views.AgentAsk.as_view(), name="agent-ask"),
]
