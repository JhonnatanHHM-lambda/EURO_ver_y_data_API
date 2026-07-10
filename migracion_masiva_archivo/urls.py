from django.urls import path

from .views import (
    CargaMasivaArchivoDetailView,
    CargaMasivaArchivoListCreateView,
    ConfiguracionCorreoView,
    DescargarReporteCargaView,
    DocumentoMarcarOkView,
    DocumentoRevisadoView,
    EstadoCargaView,
    LogsCargaView,
    PararCargaView,
    ProcesarCargaView,
    ResultadosCargaView,
)


urlpatterns = [
    path('migracion-masiva-archivo/cargas/', CargaMasivaArchivoListCreateView.as_view(), name='mma-cargas'),
    path('migracion-masiva-archivo/cargas/<int:pk>/', CargaMasivaArchivoDetailView.as_view(), name='mma-carga-detail'),
    path('migracion-masiva-archivo/cargas/<int:pk>/procesar/', ProcesarCargaView.as_view(), name='mma-carga-procesar'),
    path('migracion-masiva-archivo/cargas/<int:pk>/parar/', PararCargaView.as_view(), name='mma-carga-parar'),
    path('migracion-masiva-archivo/cargas/<int:pk>/estado/', EstadoCargaView.as_view(), name='mma-carga-estado'),
    path('migracion-masiva-archivo/cargas/<int:pk>/resultados/', ResultadosCargaView.as_view(), name='mma-carga-resultados'),
    path('migracion-masiva-archivo/cargas/<int:pk>/logs/', LogsCargaView.as_view(), name='mma-carga-logs'),
    path('migracion-masiva-archivo/cargas/<int:pk>/descargar/', DescargarReporteCargaView.as_view(), name='mma-carga-descargar'),
    path(
        'migracion-masiva-archivo/cargas/<int:pk>/documentos/<int:doc_id>/revisado/',
        DocumentoRevisadoView.as_view(),
        name='mma-documento-revisado',
    ),
    path(
        'migracion-masiva-archivo/cargas/<int:pk>/documentos/<int:doc_id>/marcar-ok/',
        DocumentoMarcarOkView.as_view(),
        name='mma-documento-marcar-ok',
    ),
    path('migracion-masiva-archivo/config/', ConfiguracionCorreoView.as_view(), name='mma-config'),
]



