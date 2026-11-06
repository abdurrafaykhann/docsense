from django.urls import path

from . import views

urlpatterns = [
    path("admin/models/", views.ModelList.as_view(), name="models"),
    path("admin/models/rollback/", views.Rollback.as_view(), name="model-rollback"),
    path("admin/models/<int:pk>/activate/", views.Activate.as_view(), name="model-activate"),
    path("admin/retrain/", views.Retrain.as_view(), name="retrain"),
    path("admin/retrain/<int:pk>/", views.RetrainDetail.as_view(), name="retrain-job"),
]
