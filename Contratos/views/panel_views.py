from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from ..models import Contrato, AsignacionCentro
from ..serializers import AsignacionCentroSerializer
from datetime import date


class EscanearSiesaView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        from ..tasks import revisar_contratos_60_dias
        try:
            antes = Contrato.objects.count()
            revisar_contratos_60_dias()
            despues = Contrato.objects.count()
            nuevos = despues - antes
            return Response({
                'mensaje': f'Escaneo completado. {nuevos} contrato(s) nuevo(s) generado(s).',
                'nuevos': nuevos,
                'total': despues,
            })
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class PanelResumenView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = Contrato.objects.all()
        from ..models import AsignacionCentro
        sedes_asignadas = AsignacionCentro.objects.filter(
            usuario=request.user, activo=True
        ).values_list('sede', flat=True)
        if sedes_asignadas.exists():
            qs = qs.filter(sede__in=sedes_asignadas)

        from django.db.models import Q
        qs_activos = qs.exclude(estado='CANCELADO')
        # Carta pendiente de firma = tiene pdf_carta_key pero no pdf_firmado_key,
        # independientemente del estado (incluye PENDIENTE_DECISION_DIRECTOR urgentes).
        pendiente_firma = qs_activos.filter(
            Q(pdf_carta_key__isnull=False) & ~Q(pdf_carta_key=''),
            Q(pdf_firmado_key__isnull=True) | Q(pdf_firmado_key=''),
        ).exclude(estado='FIRMADO').count()
        return Response({
            'total': qs_activos.count(),
            'pendiente_firma': pendiente_firma,
            'pendiente_decision': qs_activos.filter(estado='PENDIENTE_DECISION_DIRECTOR').count(),
            'firmados': qs_activos.filter(estado='FIRMADO').count(),
            'sin_canal': qs_activos.filter(estado='SIN_CANAL_CONTACTO').count(),
        })


class ContratacionesView(APIView):
    """Historial de contratos firmados agrupados por empleado."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = (
            Contrato.objects
            .filter(estado='FIRMADO')
            .select_related('sede')
            .prefetch_related('documentos_adicionales')
            .order_by('nombre_completo', '-fecha_firma')
        )

        from ..models import AsignacionCentro
        sedes_asignadas = AsignacionCentro.objects.filter(
            usuario=request.user, activo=True
        ).values_list('sede', flat=True)
        if sedes_asignadas.exists():
            qs = qs.filter(sede__in=sedes_asignadas)

        search = request.query_params.get('search', '').strip()
        if search:
            from django.db.models import Q
            qs = qs.filter(Q(nombre_completo__icontains=search) | Q(documento_id__icontains=search))

        empleados = {}
        for c in qs:
            key = c.documento_id
            if key not in empleados:
                empleados[key] = {
                    'documento_id':    c.documento_id,
                    'tipo_documento':  c.tipo_documento,
                    'nombre_completo': c.nombre_completo,
                    'contratos': [],
                }
            docs_adicionales = c.documentos_adicionales.count()
            total_docs = (1 if c.pdf_firmado_key else 0) + docs_adicionales
            empleados[key]['contratos'].append({
                'id':                 c.id,
                'tipo_carta':         c.tipo_carta,
                'cargo':              c.cargo,
                'fecha_finalizacion': str(c.fecha_finalizacion) if c.fecha_finalizacion else None,
                'fecha_firma':        c.fecha_firma.isoformat() if c.fecha_firma else None,
                'sede_nombre':        c.sede.nombre if c.sede else None,
                'sede_codigo':        c.sede.codigo if c.sede else None,
                'tiene_pdf_firmado':  bool(c.pdf_firmado_key),
                'total_documentos':   total_docs,
            })

        lista = list(empleados.values())
        # Agregar total_documentos por empleado para el badge
        for emp in lista:
            emp['total_documentos'] = sum(c['total_documentos'] for c in emp['contratos'])

        return Response({
            'empleados':        lista,
            'total_empleados':  len(lista),
            'total_contratos':  sum(len(e['contratos']) for e in lista),
        })


class AsignacionesSedView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = AsignacionCentro.objects.select_related('usuario', 'sede').filter(activo=True)
        return Response(AsignacionCentroSerializer(qs, many=True).data)

    def post(self, request):
        serializer = AsignacionCentroSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk=None):
        try:
            asignacion = AsignacionCentro.objects.get(pk=pk)
        except AsignacionCentro.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        asignacion.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
