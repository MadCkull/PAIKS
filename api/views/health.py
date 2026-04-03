from django.http import JsonResponse

def check(request):
    return JsonResponse({"status": "ok", "service": "django-api"})
