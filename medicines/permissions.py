from functools import wraps
from django.core.exceptions import PermissionDenied
from django.contrib.auth.decorators import login_required


def is_admin(user):
    """Check if the user has Administrator role or is a superuser."""
    return user.is_authenticated and (getattr(user, 'role', None) == 'ADMIN' or user.is_superuser)


def admin_required(view_func):
    """Decorator ensuring that only authenticated users with ADMIN privileges can access the view."""
    @login_required
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not is_admin(request.user):
            raise PermissionDenied("You do not have administrative privileges to perform this action.")
        return view_func(request, *args, **kwargs)
    return _wrapped_view
