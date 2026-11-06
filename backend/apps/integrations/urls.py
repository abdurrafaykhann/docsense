from django.urls import path

from . import views

W = "workspaces/<int:workspace_id>/webhooks/"

urlpatterns = [
    path(W, views.WebhookList.as_view(), name="webhooks"),
    path(f"{W}<int:pk>/", views.WebhookDetail.as_view(), name="webhook"),
    path(f"{W}<int:pk>/deliveries/", views.WebhookDeliveries.as_view(), name="webhook-deliveries"),
    path(f"{W}<int:pk>/test/", views.WebhookTest.as_view(), name="webhook-test"),
    path("integrations/inbound/", views.Inbound.as_view(), name="inbound"),
    path("integrations/documents/<int:pk>/", views.InboundDocument.as_view(), name="inbound-doc"),
]
