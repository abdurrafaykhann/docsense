from django.urls import path

from . import views

W = "workspaces/<int:workspace_id>/analytics/"

urlpatterns = [
    path(f"{W}spend/", views.Spend.as_view(), name="spend"),
    path(f"{W}summary/", views.Summary.as_view(), name="summary"),
    path(f"{W}flags/", views.FlagList.as_view(), name="flags"),
    path(f"{W}flags/<int:pk>/", views.FlagDetail.as_view(), name="flag"),
    path(f"{W}detect/", views.Detect.as_view(), name="detect"),
    path(f"{W}vendors/", views.VendorList.as_view(), name="vendors"),
    path(f"{W}vendors/<int:pk>/price-history/", views.PriceHistory.as_view(), name="price-history"),
]
