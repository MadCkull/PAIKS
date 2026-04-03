from django.shortcuts import render


def home(request):
    return render(request, "assistant/home.html")

def login(request):
    return render(request, "assistant/login.html")
