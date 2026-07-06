from django.http import HttpResponse
from django.utils.dateparse import parse_date
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from rest_framework.views import APIView

from EURO_ver_y_data.decoradores import require_permission
from ..models import EjecucionConsolidacion, ResultadoConciliacion
from ..serializers import (
    EjecucionConsolidacionListSerializer,
    EjecucionConsolidacionDetalleSerializer,
    ResultadoConciliacionSerializer,
)
from ..tasks import ejecutar_consolidacion
from ..utils.export_xlsx import generar_excel


class EjecutarConsolidacionView(APIView):
    permission_classes = [IsAuthenticated]

    @require_permission(['can_view_optimizacion_correos'], app_label='Usuarios')
    def post(self, request):
        fecha_desde = request.data.get('fecha_desde')
        fecha_hasta = request.data.get('fecha_hasta')

        if not fecha_desde or not fecha_hasta:
            return Response(
                {'error': 'Se requieren fecha_desde y fecha_hasta'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        fecha_desde_dt = parse_date(str(fecha_desde))
        fecha_hasta_dt = parse_date(str(fecha_hasta))
        if not fecha_desde_dt or not fecha_hasta_dt:
            return Response(
                {'error': 'Las fechas deben tener formato YYYY-MM-DD'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if fecha_desde_dt >= fecha_hasta_dt:
            return Response(
                {'error': 'fecha_desde debe ser anterior a fecha_hasta'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        en_curso = EjecucionConsolidacion.objects.filter(
            estado__in=['PENDIENTE', 'EN_PROCESO']
        ).first()
        if en_curso:
            return Response(
                {'error': f'Ya hay una ejecución en curso (id={en_curso.pk}, estado={en_curso.estado})'},
                status=status.HTTP_409_CONFLICT,
            )

        ejecucion = EjecucionConsolidacion.objects.create(
            fecha_desde=fecha_desde_dt,
            fecha_hasta=fecha_hasta_dt,
            estado='PENDIENTE',
            iniciada_por=request.user,
        )

        ejecutar_consolidacion.delay(ejecucion.pk)

        return Response(
            {'ejecucion_id': ejecucion.pk, 'estado': ejecucion.estado},
            status=status.HTTP_202_ACCEPTED,
        )


class ListaEjecucionesView(APIView):
    permission_classes = [IsAuthenticated]

    @require_permission(['can_view_optimizacion_correos'], app_label='Usuarios')
    def get(self, request):
        qs = EjecucionConsolidacion.objects.all().order_by('-creado')

        # Paginación simple
        page = int(request.query_params.get('page', 1))
        page_size = int(request.query_params.get('page_size', 20))
        offset = (page - 1) * page_size
        total = qs.count()
        qs_page = qs[offset:offset + page_size]

        serializer = EjecucionConsolidacionListSerializer(qs_page, many=True)
        return Response({
            'count': total,
            'page': page,
            'page_size': page_size,
            'results': serializer.data,
        })


class DetalleEjecucionView(APIView):
    permission_classes = [IsAuthenticated]

    @require_permission(['can_view_optimizacion_correos'], app_label='Usuarios')
    def get(self, request, ejecucion_id):
        try:
            ejecucion = EjecucionConsolidacion.objects.get(pk=ejecucion_id)
        except EjecucionConsolidacion.DoesNotExist:
            return Response({'error': 'Ejecución no encontrada'}, status=status.HTTP_404_NOT_FOUND)

        serializer = EjecucionConsolidacionDetalleSerializer(ejecucion)
        return Response(serializer.data)


class ResultadosEjecucionView(APIView):
    permission_classes = [IsAuthenticated]

    @require_permission(['can_view_optimizacion_correos'], app_label='Usuarios')
    def get(self, request, ejecucion_id):
        try:
            ejecucion = EjecucionConsolidacion.objects.get(pk=ejecucion_id)
        except EjecucionConsolidacion.DoesNotExist:
            return Response({'error': 'Ejecución no encontrada'}, status=status.HTTP_404_NOT_FOUND)

        qs = ResultadoConciliacion.objects.filter(ejecucion=ejecucion)

        estado_filtro = request.query_params.get('estado', '')
        if estado_filtro:
            qs = qs.filter(estado=estado_filtro)

        page = int(request.query_params.get('page', 1))
        page_size = int(request.query_params.get('page_size', 50))
        offset = (page - 1) * page_size
        total = qs.count()
        qs_page = qs[offset:offset + page_size]

        serializer = ResultadoConciliacionSerializer(qs_page, many=True)
        return Response({
            'count': total,
            'page': page,
            'page_size': page_size,
            'results': serializer.data,
        })


class ExportarExcelView(APIView):
    permission_classes = [IsAuthenticated]

    @require_permission(['can_view_optimizacion_correos'], app_label='Usuarios')
    def get(self, request, ejecucion_id):
        try:
            ejecucion = EjecucionConsolidacion.objects.get(pk=ejecucion_id)
        except EjecucionConsolidacion.DoesNotExist:
            return Response({'error': 'Ejecución no encontrada'}, status=status.HTTP_404_NOT_FOUND)

        if ejecucion.estado != 'COMPLETADA':
            return Response(
                {'error': 'Solo se puede exportar una ejecución completada'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        xlsx_bytes = generar_excel(ejecucion)
        filename = f'conciliacion_{ejecucion.fecha_desde}_{ejecucion.fecha_hasta}.xlsx'

        response = HttpResponse(
            xlsx_bytes,
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
