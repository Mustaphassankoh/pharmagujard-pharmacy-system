from django.http import JsonResponse
from django.shortcuts import render


def health_check(request):
    """Public liveness check with no database or configuration disclosure."""
    return JsonResponse({'status': 'ok'})


def _error_response(request, status, title, message):
    return render(
        request,
        'errors/error.html',
        {'status_code': status, 'error_title': title, 'error_message': message},
        status=status,
    )


def error_400(request, exception=None):
    return _error_response(request, 400, 'Invalid request', 'The request could not be processed.')


def error_403(request, exception=None):
    return _error_response(request, 403, 'Access denied', 'You do not have permission to access this page.')


def csrf_failure(request, reason=''):
    return _error_response(request, 403, 'Security check failed', 'Please refresh the page and try again.')


def error_404(request, exception=None):
    return _error_response(request, 404, 'Page not found', 'The page you requested could not be found.')


def error_500(request):
    return _error_response(request, 500, 'Something went wrong', 'The request could not be completed. Please try again later.')
