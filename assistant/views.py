from django.http import JsonResponse
from django.shortcuts import render


def home(request):
    context = {
        "title": "Google Drive AI Assistant",
        "description": "Connect your Google Drive and run AI-powered search over your documents.",
    }
    return render(request, "assistant/home.html", context)


def dashboard(request):
    # For now these are placeholders – later we will populate them
    # from the database or the Flask API (Google Drive sync service).
    context = {
        "documents_total": 0,
        "documents_indexed": 0,
        "last_sync": "Not synced yet",
    }
    return render(request, "assistant/dashboard.html", context)


def flask_api_status(request):
    return JsonResponse(
        {
            "message": "Django is running.",
            "flask_api_example": "http://127.0.0.1:5001/health",
        }
    )

