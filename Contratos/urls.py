from django.urls import path
from .views.firma_views import ValidarTokenView, ConfirmarFirmaView
from .views.contratos_views import (
    ContratosListView, ContratoDetailView,
    ProrrogarContratoView, TerminarContratoView, SubirDocumentoAdicionalView,
)
from .views.panel_views import PanelResumenView, AsignacionesSedView, EscanearSiesaView

urlpatterns = [
    # Públicas — acceso del empleado para firma (sin auth)
    path('contratos/firma/<uuid:token>/', ValidarTokenView.as_view(), name='firma-validar'),
    path('contratos/firma/<uuid:token>/confirmar/', ConfirmarFirmaView.as_view(), name='firma-confirmar'),
    # Panel GH / Director (autenticadas)
    path('contratos/', ContratosListView.as_view(), name='contratos-list'),
    path('contratos/resumen/', PanelResumenView.as_view(), name='contratos-resumen'),
    path('contratos/escanear/', EscanearSiesaView.as_view(), name='contratos-escanear'),
    path('contratos/asignaciones/', AsignacionesSedView.as_view(), name='contratos-asignaciones'),
    path('contratos/asignaciones/<int:pk>/', AsignacionesSedView.as_view(), name='contratos-asignaciones-detail'),
    path('contratos/<int:pk>/', ContratoDetailView.as_view(), name='contratos-detail'),
    path('contratos/<int:pk>/prorrogar/', ProrrogarContratoView.as_view(), name='contratos-prorrogar'),
    path('contratos/<int:pk>/terminar/', TerminarContratoView.as_view(), name='contratos-terminar'),
    path('contratos/<int:pk>/documentos/', SubirDocumentoAdicionalView.as_view(), name='contratos-documentos'),
]
