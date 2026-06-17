from django.db.models import Q, Count, Subquery, OuterRef, F
from django.db.models.functions import Coalesce
from rest_framework.views import APIView
from rest_framework.response import Response
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi

from EURO_ver_y_data.decoradores import require_permission
from Trazabilidad.models import EmpleadoTrazabilidad
from Trazabilidad.serializers import EmpleadoListSerializer, EmpleadoDetalleSerializer


def _orden_actividad_reciente():
    """
    Ordena por la fecha de actividad más reciente:
    COALESCE(fecha_retiro, fecha_ingreso) DESC NULLS LAST, creado DESC.
    Un RETIRADO con fecha_retiro=2016 es más reciente que
    un EMPLEADO con fecha_ingreso=2015 aunque tengan el mismo fecha_ingreso.
    """
    return [
        Coalesce('fecha_retiro', 'fecha_ingreso').desc(nulls_last=True),
        '-creado',
    ]


class EmpleadosView(APIView):

    @require_permission(['can_view_trazabilidad'], app_label='Usuarios')
    @swagger_auto_schema(
        operation_summary='Listar una fila por persona (proceso más reciente)',
        manual_parameters=[
            openapi.Parameter('search', openapi.IN_QUERY, type=openapi.TYPE_STRING),
            openapi.Parameter('sede',   openapi.IN_QUERY, type=openapi.TYPE_INTEGER),
            openapi.Parameter('origen', openapi.IN_QUERY, type=openapi.TYPE_STRING),
            openapi.Parameter('estado', openapi.IN_QUERY, type=openapi.TYPE_STRING),
            openapi.Parameter('tipo_proceso', openapi.IN_QUERY, type=openapi.TYPE_STRING),
        ],
        tags=['Trazabilidad'],
    )
    def get(self, request, documento=None):
        # ── Detalle de una persona → historial completo (más reciente primero) ─
        if documento:
            registros = (
                EmpleadoTrazabilidad.objects
                .filter(documento_id=documento, estado=True)
                .select_related('sede')
                .order_by(*_orden_actividad_reciente())
            )
            return Response(EmpleadoDetalleSerializer(registros, many=True).data)

        # ── Listado: UNA fila por persona (proceso más reciente) ─────────────
        base = EmpleadoTrazabilidad.objects.filter(estado=True)

        # Aplicar filtros ANTES de calcular el registro más reciente
        search      = request.query_params.get('search', '').strip()
        sede        = request.query_params.get('sede')
        origen      = request.query_params.get('origen', '').strip()
        estado_f    = request.query_params.get('estado', '').strip()
        tipo_proc   = request.query_params.get('tipo_proceso', '').strip()

        if search:
            base = base.filter(
                Q(documento_id__icontains=search) |
                Q(nombre_completo__icontains=search)
            )
        if sede:
            base = base.filter(sede_id=sede)
        if origen:
            base = base.filter(origen_datos__icontains=origen)

        # Obtener el ID del registro más reciente por documento_id
        # Usa COALESCE(fecha_retiro, fecha_ingreso) para que RETIRADO con
        # fecha_retiro posterior prevalezca sobre EMPLEADO con mismo ingreso
        ultimo_id_subquery = (
            base.filter(documento_id=OuterRef('documento_id'))
            .order_by(*_orden_actividad_reciente())
            .values('id')[:1]
        )

        # Filtrar: solo los registros que son el MÁS RECIENTE de su persona
        qs = base.filter(id=Subquery(ultimo_id_subquery)).select_related('sede')

        # Filtros post-deduplicación (sobre el estado actual de cada persona)
        if estado_f:
            qs = qs.filter(estado_candidato=estado_f)
        if tipo_proc:
            qs = qs.filter(tipo_proceso=tipo_proc)

        qs = qs.order_by('nombre_completo')

        # Paginación
        page      = max(1, int(request.query_params.get('page', 1)))
        page_size = min(100, max(1, int(request.query_params.get('page_size', 20))))
        total     = qs.count()
        start     = (page - 1) * page_size
        pagina    = qs[start: start + page_size]

        return Response({
            'total':       total,
            'page':        page,
            'page_size':   page_size,
            'total_pages': (total + page_size - 1) // page_size,
            'results':     EmpleadoListSerializer(pagina, many=True).data,
        })


class KPIsTrazabilidadView(APIView):

    @require_permission(['can_view_trazabilidad'], app_label='Usuarios')
    @swagger_auto_schema(
        operation_summary='KPIs basados en el proceso más reciente por persona',
        tags=['Trazabilidad']
    )
    def get(self, request):
        sede_id = request.query_params.get('sede')
        base    = EmpleadoTrazabilidad.objects.filter(estado=True)
        if sede_id:
            base = base.filter(sede_id=sede_id)

        # Personas únicas totales
        total = base.values('documento_id').distinct().count()

        # Subquery: id del registro más reciente por documento_id
        ultimo_id_sq = Subquery(
            base.filter(documento_id=OuterRef('documento_id'))
            .order_by(*_orden_actividad_reciente())
            .values('id')[:1]
        )

        # Solo el registro más reciente de cada persona
        ultimos = base.filter(id=ultimo_id_sq)

        # KPIs basados en el proceso MÁS RECIENTE de cada persona — un solo aggregate
        conteos   = ultimos.aggregate(
            activos=Count('id', filter=Q(tipo_proceso='EMPLEADO')),
            retirados=Count('id', filter=Q(tipo_proceso='RETIRADO')),
        )
        activos   = conteos['activos']
        retirados = conteos['retirados']

        # Inhabilitados: cualquier registro con ese estado (no solo el último)
        inhabilitados = (
            base.filter(estado_candidato='INHABILITADO')
            .values('documento_id').distinct().count()
        )

        origenes = list(
            base.values('origen_datos')
            .annotate(total=Count('documento_id', distinct=True))
            .order_by('-total')[:8]
        )

        return Response({
            'total':         total,
            'activos':       activos,
            'retirados':     retirados,
            'inhabilitados': inhabilitados,
            'origenes':      origenes,
        })
