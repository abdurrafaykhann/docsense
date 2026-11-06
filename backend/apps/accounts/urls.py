from django.urls import path

from . import views

urlpatterns = [
    path("auth/signup/", views.SignupView.as_view(), name="signup"),
    path("auth/login/", views.LoginView.as_view(), name="login"),
    path("auth/refresh/", views.RefreshView.as_view(), name="refresh"),
    path("me/", views.MeView.as_view(), name="me"),
]
