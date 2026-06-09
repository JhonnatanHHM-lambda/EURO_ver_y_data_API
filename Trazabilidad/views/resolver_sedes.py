from rest_framework.views import APIView
from rest_framework.response import Response
from drf_yasg.utils import swagger_auto_schema

from EURO_ver_y_data.decoradores import require_permission
from Trazabilidad.models import Sede
from Trazabilidad.serializers import SedeSerializer
from Trazabilidad.variantes_sede import resolver_sede


class ResolverSedesView(APIView):
    """
    Recibe una lista de valores de sede encontrados en un Excel y retorna:
    - resueltos: {valor_original: SedeSerializer}
    - no_resueltos: [valor_original, ...]
    - sedes_disponibles: lista completa de sedes para el dropdown
    """

    @require_permission(['can_upload_excel'], app_label='Usuarios')
    @swagger_auto_schema(operation_summary='Resolver valores de sede del Excel', tags=['Carga Excel'])
    def post(self, request):
        valores = request.data.get('valores', [])
        if not isinstance(valores, list):
            return Response({'error': 'valores debe ser una lista.'}, status=400)

        # Cache de sedes por código
        sedes_por_codigo = {s.codigo: s for s in Sede.objects.filter(estado=True)}

        resueltos = {}
        no_resueltos = []

        for valor in valores:
            # Vacío/sin sede → siempre va a no_resueltos para que el usuario asigne
            if valor == '':
                no_resueltos.append(valor)
                continue
            codigo = resolver_sede(valor)
            if codigo and codigo in sedes_por_codigo:
                sede = sedes_por_codigo[codigo]
                resueltos[valor] = SedeSerializer(sede).data
            else:
                no_resueltos.append(valor)

        sedes_disponibles = SedeSerializer(
            Sede.objects.filter(estado=True).order_by('nombre'), many=True
        ).data

        return Response({
            'resueltos':         resueltos,
            'no_resueltos':      no_resueltos,
            'sedes_disponibles': sedes_disponibles,
        })
