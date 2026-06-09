"""Endpoints para firmar y descargar el acta de carga."""
from django.http import HttpResponse
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response

from EURO_ver_y_data.decoradores import require_permission
from Trazabilidad.models import CargaExcel
from Trazabilidad.utils.acta_pdf  import generar_pdf_acta
from Trazabilidad.utils.acta_word import generar_word_acta


class FirmaImagenView(APIView):
    """Devuelve solo la imagen de la firma GH de una carga específica."""

    @require_permission(['can_manage_cargas'], app_label='Usuarios')
    def get(self, request, pk):
        try:
            carga = CargaExcel.objects.get(pk=pk)
        except CargaExcel.DoesNotExist:
            return Response({'error': 'Carga no encontrada.'}, status=404)
        return Response({
            'firma_gh_imagen': carga.firma_gh_imagen or '',
            'firmada':         bool(carga.firma_gh_nombre),
        })


class FirmarActaView(APIView):
    """Guarda la firma GH en la carga y confirma."""

    @require_permission(['can_manage_cargas'], app_label='Usuarios')
    def post(self, request, pk):
        try:
            # estado=True/False — se puede firmar incluso una carga revertida
            # (el acta es el registro histórico del proceso, necesita firma aunque esté revertida)
            carga = CargaExcel.objects.get(pk=pk)
        except CargaExcel.DoesNotExist:
            return Response({'error': 'Carga no encontrada.'}, status=404)

        # Bloquear re-firma si ya fue firmada
        if carga.firma_gh_nombre:
            return Response({
                'error': 'Esta acta ya fue firmada y no puede modificarse.',
                'firmada_por': carga.firma_gh_nombre,
                'firmada_en':  carga.firma_gh_fecha.strftime('%d/%m/%Y %H:%M')
                               if carga.firma_gh_fecha else None,
            }, status=400)

        nombre = request.data.get('nombre', '').strip()
        cargo  = request.data.get('cargo',  '').strip()
        imagen = request.data.get('imagen', '').strip()

        if not nombre:
            return Response({'error': 'El nombre del firmante es obligatorio.'}, status=400)

        carga.firma_gh_nombre = nombre
        carga.firma_gh_cargo  = cargo
        carga.firma_gh_fecha  = timezone.now()
        carga.firma_gh_imagen = imagen
        carga.save(update_fields=['firma_gh_nombre', 'firma_gh_cargo',
                                  'firma_gh_fecha',  'firma_gh_imagen'])

        return Response({'ok': True, 'mensaje': f'Firma registrada para {nombre}.'})


class DescargarActaView(APIView):
    """Genera y descarga el acta on-demand (PDF o Word)."""

    @require_permission(['can_manage_cargas'], app_label='Usuarios')
    def get(self, request, pk, formato='pdf'):
        try:
            carga = CargaExcel.objects.select_related('sede', 'cargado_por').get(pk=pk)
        except CargaExcel.DoesNotExist:
            return Response({'error': 'Carga no encontrada.'}, status=404)

        nombre_base = (
            f"Acta_Carga_{carga.origen_datos}_{carga.id}"
            .replace(' ', '_').replace('/', '-')
        )

        if formato == 'pdf':
            pdf_bytes = generar_pdf_acta(carga)
            resp = HttpResponse(pdf_bytes, content_type='application/pdf')
            resp['Content-Disposition'] = f'attachment; filename="{nombre_base}.pdf"'
            return resp

        elif formato == 'docx':
            docx_bytes = generar_word_acta(carga)
            resp = HttpResponse(
                docx_bytes,
                content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            )
            resp['Content-Disposition'] = f'attachment; filename="{nombre_base}.docx"'
            return resp

        return Response({'error': 'Formato no válido. Usa pdf o docx.'}, status=400)
