from django.urls import path

from . import views

W = "workspaces/<int:workspace_id>/documents/"

urlpatterns = [
    path(W, views.DocumentList.as_view(), name="document-list"),
    path(f"{W}<int:pk>/", views.DocumentDetail.as_view(), name="document-detail"),
    path(f"{W}<int:pk>/reprocess/", views.DocumentReprocess.as_view(), name="document-reprocess"),
    path(f"{W}<int:pk>/pages/<int:number>/image/", views.PageImage.as_view(), name="page-image"),
    path(f"{W}<int:pk>/fields/<str:name>/", views.FieldEdit.as_view(), name="field-edit"),
    path(f"{W}<int:pk>/line-items/", views.LineItemsEdit.as_view(), name="line-items-edit"),
    path(f"{W}<int:pk>/approve/", views.Approve.as_view(), name="document-approve"),
    path("workspaces/<int:workspace_id>/review/queue/", views.ReviewQueue.as_view(), name="queue"),
    path(
        f"{W}<int:pk>/pages/<int:number>/regions/", views.RegionsEdit.as_view(), name="regions-edit"
    ),
]
