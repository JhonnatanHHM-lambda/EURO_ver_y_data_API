from django.urls import path
from .views import (
    DashboardAusentismoView,
    DashboardAusentismoOpcionesView,
    DashboardNominaVentaView,
    DashboardAntiguedadView,
    DashboardRotacionView,
    DashboardRotacionOpcionesView,
    DashboardCacheReloadView,
)

urlpatterns = [
    path('dashboard/ausentismo/',          DashboardAusentismoView.as_view(),          name='dashboard-ausentismo'),
    path('dashboard/ausentismo/opciones/', DashboardAusentismoOpcionesView.as_view(),  name='dashboard-ausentismo-opciones'),
    path('dashboard/nomina-venta/',        DashboardNominaVentaView.as_view(),         name='dashboard-nomina-venta'),
    path('dashboard/antiguedad/',          DashboardAntiguedadView.as_view(),          name='dashboard-antiguedad'),
    path('dashboard/rotacion/',            DashboardRotacionView.as_view(),            name='dashboard-rotacion'),
    path('dashboard/rotacion/opciones/',   DashboardRotacionOpcionesView.as_view(),    name='dashboard-rotacion-opciones'),
    path('dashboard/reload-cache/',        DashboardCacheReloadView.as_view(),         name='dashboard-reload-cache'),
]
