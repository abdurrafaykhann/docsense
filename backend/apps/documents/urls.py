from django.urls import path

from . import views

W = "workspaces/<int:workspace_id>/documents/"

urlpatterns = [
    path(W, views.DocumentList.as_view(), name="document-list"),
    path(f"{W}<int:pk>/", views.DocumentDetail.as_view(), name="document-detail"),
    path(f"{W}<int:pk>/reprocess/", views.DocumentReprocess.as_view(), name="document-reprocess"),
    path(f"{W}<int:pk>/pages/<int:number>/image/", views.PageImage.as_view(), name="page-image"),
]
