import logging
from django.http import JsonResponse
from django.utils.deprecation import MiddlewareMixin

logger = logging.getLogger(__name__)

class ApiMiddleware(MiddlewareMixin):
    def process_request(self, request):
        if request.path.startswith('/api/'):
            # Disable CSRF for all /api/ endpoints to make it act like a pure REST API
            request._dont_enforce_csrf_checks = True

    def process_exception(self, request, exception):
        if request.path.startswith('/api/'):
            import traceback
            logger.error("API unhandled exception: %s\n%s", exception, traceback.format_exc())
            return JsonResponse({"error": str(exception)}, status=500)
