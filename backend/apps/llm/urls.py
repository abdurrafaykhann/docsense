from django.urls import path

from . import views

urlpatterns = [path("admin/llm-usage/", views.UsageStats.as_view(), name="llm-usage")]
