from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("files/", views.drive_files, name="drive_files"),
    path("login/", views.login, name="login"),
]
