from functools import wraps
from rest_framework.response import Response
from rest_framework import status


def require_permission(permissions, app_label=None):
    def decorator(func):
        @wraps(func)
        def wrapper(self, request, *args, **kwargs):
            if not request.user.is_authenticated:
                return Response(
                    {'error': 'Autenticación requerida'},
                    status=status.HTTP_401_UNAUTHORIZED
                )
            required_perms = [
                f'{app_label}.{perm}' if app_label else perm
                for perm in permissions
            ]
            if not request.user.has_perms(required_perms):
                return Response(
                    {'error': 'Permiso denegado', 'required': required_perms},
                    status=status.HTTP_403_FORBIDDEN
                )
            return func(self, request, *args, **kwargs)
        return wrapper
    return decorator
