from django.urls import path
from .views.consolidacion_views import (
    EjecutarConsolidacionView,
    ListaEjecucionesView,
    DetalleEjecucionView,
    ResultadosEjecucionView,
    ExportarExcelView,
)

urlpatterns = [
    path('optimizacion-correos/ejecutar/',
         EjecutarConsolidacionView.as_view(), name='oc-ejecutar'),
    path('optimizacion-correos/ejecuciones/',
         ListaEjecucionesView.as_view(), name='oc-ejecuciones'),
    path('optimizacion-correos/ejecuciones/<int:ejecucion_id>/',
         DetalleEjecucionView.as_view(), name='oc-ejecucion-detalle'),
    path('optimizacion-correos/ejecuciones/<int:ejecucion_id>/resultados/',
         ResultadosEjecucionView.as_view(), name='oc-resultados'),
    path('optimizacion-correos/ejecuciones/<int:ejecucion_id>/exportar/',
         ExportarExcelView.as_view(), name='oc-exportar'),
]
