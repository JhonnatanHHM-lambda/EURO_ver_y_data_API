from django.urls import path
from .views import (
    DashboardAusentismoView,
    DashboardNominaVentaView,
    DashboardAntiguedadView,
    DashboardCacheReloadView,
)

urlpatterns = [
    path('dashboard/ausentismo/',   DashboardAusentismoView.as_view(),  name='dashboard-ausentismo'),
    path('dashboard/nomina-venta/', DashboardNominaVentaView.as_view(), name='dashboard-nomina-venta'),
    path('dashboard/antiguedad/',   DashboardAntiguedadView.as_view(),  name='dashboard-antiguedad'),
    path('dashboard/reload-cache/', DashboardCacheReloadView.as_view(), name='dashboard-reload-cache'),
]
