from django.shortcuts import render


def home(request):
    return render(request, "assistant/home.html")


def dashboard(request):
    return render(request, "assistant/dashboard.html")


def drive_files(request):
    return render(request, "assistant/files.html")
