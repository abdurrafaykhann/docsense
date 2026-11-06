from django.urls import path

from . import views

urlpatterns = [
    path("evaluation/runs/", views.RunList.as_view(), name="eval-runs"),
    path("evaluation/runs/<int:pk>/", views.RunDetail.as_view(), name="eval-run"),
]
