from django.urls import path
from .views.sedes_views import SedesView
from .views.carga_views import PreviewExcelView, CargarExcelView
from .views.historial_views import HistorialCargasView, RevertirCargaView
from .views.empleados_views import EmpleadosView, KPIsTrazabilidadView
from .views.resolver_sedes import ResolverSedesView
from .views.acta_views import FirmarActaView, DescargarActaView, FirmaImagenView
from .views.administracion_views import (
    SedesAdminView, SedeAdminDetalleView,
    OrigenesAdminView, OrigenAdminDetalleView,
)
from .views.edicion_views import (
    EditarRegistroView, HistorialRegistroView,
    CrearRegistroView, AdminRegistrosView, EliminarRegistroView,
)

urlpatterns = [
    path('sedes/', SedesView.as_view(), name='sedes-list'),
    # Administración de sedes y orígenes
    path('admin/sedes/', SedesAdminView.as_view(), name='admin-sedes'),
    path('admin/sedes/<int:pk>/', SedeAdminDetalleView.as_view(), name='admin-sede-detalle'),
    path('admin/origenes/', OrigenesAdminView.as_view(), name='admin-origenes'),
    path('admin/origenes/<int:pk>/', OrigenAdminDetalleView.as_view(), name='admin-origen-detalle'),
    # Alias público de orígenes (para el selector de carga)
    path('origenes/', OrigenesAdminView.as_view(), name='origenes-publico'),
    path('trazabilidad/preview/', PreviewExcelView.as_view(), name='preview-excel'),
    path('trazabilidad/cargar/', CargarExcelView.as_view(), name='cargar-excel'),
    path('trazabilidad/historial/', HistorialCargasView.as_view(), name='historial-cargas'),
    path('trazabilidad/cargas/<int:pk>/firmar/', FirmarActaView.as_view(),    name='firmar-acta'),
    path('trazabilidad/cargas/<int:pk>/firma-imagen/', FirmaImagenView.as_view(), name='firma-imagen'),
    path('trazabilidad/cargas/<int:pk>/acta/<str:formato>/', DescargarActaView.as_view(), name='descargar-acta'),
    path('trazabilidad/historial/<int:pk>/revertir/', RevertirCargaView.as_view(), name='revertir-carga'),
    path('trazabilidad/empleados/', EmpleadosView.as_view(), name='empleados-list'),
    path('trazabilidad/empleados/<str:documento>/', EmpleadosView.as_view(), name='empleados-detalle'),
    path('trazabilidad/kpis/', KPIsTrazabilidadView.as_view(), name='kpis-trazabilidad'),
    path('trazabilidad/resolver-sedes/', ResolverSedesView.as_view(), name='resolver-sedes'),
    # Edición de registros individuales y auditoría
    path('trazabilidad/admin/registros/',          AdminRegistrosView.as_view(),   name='admin-registros'),
    path('trazabilidad/registros/crear/',          CrearRegistroView.as_view(),    name='crear-registro'),
    path('trazabilidad/registros/<int:pk>/eliminar/', EliminarRegistroView.as_view(), name='eliminar-registro'),
    path('trazabilidad/registros/<int:pk>/editar/', EditarRegistroView.as_view(), name='editar-registro'),
    path('trazabilidad/registros/<int:pk>/historial/', HistorialRegistroView.as_view(), name='historial-registro'),
]
