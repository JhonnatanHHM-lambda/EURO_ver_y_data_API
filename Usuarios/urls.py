from django.urls import path
from .views.auth_views import (
    LoginIniciarView, LoginVerificarOTPView, TokenRefreshView, LogoutView, MeView,
    RecuperacionIniciarView, RecuperacionValidarOTPView,
    NotificacionesAdminView, ResolverRecuperacionView,
)
from .views.usuarios_views import UsuariosCRUDView, CambiarPasswordView
from .views.grupos_views import GruposCRUDView, PermisosListView

urlpatterns = [
    # Auth
    path('auth/login/',         LoginIniciarView.as_view(),     name='auth-login'),
    path('auth/verificar-otp/', LoginVerificarOTPView.as_view(), name='auth-verificar-otp'),
    path('auth/refresh/',       TokenRefreshView.as_view(),     name='auth-refresh'),
    path('auth/logout/',        LogoutView.as_view(),           name='auth-logout'),
    path('auth/me/',            MeView.as_view(),               name='auth-me'),

    # Recuperación de contraseña
    path('auth/recuperar/',             RecuperacionIniciarView.as_view(),    name='recuperar-iniciar'),
    path('auth/recuperar/validar/',     RecuperacionValidarOTPView.as_view(), name='recuperar-validar'),

    # Notificaciones admin + resolución
    path('admin/notificaciones/',                              NotificacionesAdminView.as_view(),  name='notif-list'),
    path('admin/notificaciones/<int:pk>/',                     NotificacionesAdminView.as_view(),  name='notif-detail'),
    path('admin/recuperaciones/<int:pk>/resolver/',            ResolverRecuperacionView.as_view(), name='recuperar-resolver'),

    # Usuarios
    path('usuarios/', UsuariosCRUDView.as_view(), name='usuarios-list'),
    path('usuarios/<int:pk>/', UsuariosCRUDView.as_view(), name='usuarios-detail'),
    path('usuarios/cambiar-password/', CambiarPasswordView.as_view(), name='cambiar-password'),

    # Roles y permisos
    path('roles/', GruposCRUDView.as_view(), name='roles-list'),
    path('roles/<int:pk>/', GruposCRUDView.as_view(), name='roles-detail'),
    path('permisos/', PermisosListView.as_view(), name='permisos-list'),
]
