from django.urls import path
from .views.firma_views import (
    ValidarTokenView, ConfirmarFirmaView, FirmaPDFProxyView,
    FirmaNoProrrogaPDFProxyView, ConfirmarFirmaNoProrrogaView,
)
from .views.contratos_views import (
    ContratosListView, ContratoDetailView,
    ProrrogarContratoView, TerminarContratoView, SubirDocumentoAdicionalView,
    CondicionesGHView, NotificarEmpleadoView, CrearContratoDemoView,
    ActualizarContactoView, ReenviarNotificacionView,
)
from .views.panel_views import PanelResumenView, AsignacionesSedView, EscanearSiesaView, ContratacionesView, ReporteContratacionesView
from .views.firma_gh_views import (
    FirmaGHView, FirmaGHToggleView, FirmaProvisionaView,
    RegistroFirmaEmpleadorListView, ReporteRegistroFirmaView,
    UsuariosParaProvisionaView,
)

urlpatterns = [
    # Públicas — acceso del empleado para firma (sin auth)
    path('contratos/firma/<uuid:token>/', ValidarTokenView.as_view(), name='firma-validar'),
    path('contratos/firma/<uuid:token>/confirmar/', ConfirmarFirmaView.as_view(), name='firma-confirmar'),
    path('contratos/firma/<uuid:token>/pdf/', FirmaPDFProxyView.as_view(), name='firma-pdf-proxy'),
    path('contratos/firma/<uuid:token>/pdf-no-prorroga/', FirmaNoProrrogaPDFProxyView.as_view(), name='firma-pdf-no-prorroga'),
    path('contratos/firma/<uuid:token>/confirmar-no-prorroga/', ConfirmarFirmaNoProrrogaView.as_view(), name='firma-confirmar-no-prorroga'),
    # Panel GH / Director (autenticadas)
    path('contratos/', ContratosListView.as_view(), name='contratos-list'),
    path('contratos/resumen/', PanelResumenView.as_view(), name='contratos-resumen'),
    path('contratos/escanear/', EscanearSiesaView.as_view(), name='contratos-escanear'),
    path('contratos/crear-demo/', CrearContratoDemoView.as_view(), name='contratos-crear-demo'),
    path('contratos/contrataciones/', ContratacionesView.as_view(), name='contratos-contrataciones'),
    path('contratos/contrataciones/reporte/', ReporteContratacionesView.as_view(), name='contratos-contrataciones-reporte'),
    path('contratos/asignaciones/', AsignacionesSedView.as_view(), name='contratos-asignaciones'),
    path('contratos/asignaciones/<int:pk>/', AsignacionesSedView.as_view(), name='contratos-asignaciones-detail'),
    path('contratos/<int:pk>/', ContratoDetailView.as_view(), name='contratos-detail'),
    path('contratos/<int:pk>/prorrogar/', ProrrogarContratoView.as_view(), name='contratos-prorrogar'),
    path('contratos/<int:pk>/terminar/', TerminarContratoView.as_view(), name='contratos-terminar'),
    path('contratos/<int:pk>/condiciones/', CondicionesGHView.as_view(), name='contratos-condiciones'),
    path('contratos/<int:pk>/notificar-empleado/', NotificarEmpleadoView.as_view(), name='contratos-notificar-empleado'),
    path('contratos/<int:pk>/documentos/', SubirDocumentoAdicionalView.as_view(), name='contratos-documentos'),
    path('contratos/<int:pk>/contacto/', ActualizarContactoView.as_view(), name='contratos-contacto'),
    path('contratos/<int:pk>/reenviar-notificacion/', ReenviarNotificacionView.as_view(), name='contratos-reenviar-notificacion'),
    # Firma GH (empleador)
    path('contratos/firma-gh/usuarios/', UsuariosParaProvisionaView.as_view(), name='firma-gh-usuarios'),
    path('contratos/firma-gh/', FirmaGHView.as_view(), name='firma-gh'),
    path('contratos/firma-gh/toggle/', FirmaGHToggleView.as_view(), name='firma-gh-toggle'),
    path('contratos/firma-gh/provisional/', FirmaProvisionaView.as_view(), name='firma-gh-provisional'),
    path('contratos/firma-gh/registros/', RegistroFirmaEmpleadorListView.as_view(), name='firma-gh-registros'),
    path('contratos/firma-gh/registros/reporte/', ReporteRegistroFirmaView.as_view(), name='firma-gh-registros-reporte'),
]
