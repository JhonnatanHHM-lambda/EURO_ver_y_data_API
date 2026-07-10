from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.test import APIClient

from .models import DocumentoDigitalizado, LoteDocumental


class MigracionMasivaArchivoApiTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            correo='mma@test.com',
            cedula='100000001',
            password='123456',
            nombres='QA',
            apellidos='Migracion',
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_crea_carga_con_archivo(self):
        def fake_crear_lote_desde_carpeta(carpeta_origen, nombre, usuario):
            lote = LoteDocumental.objects.create(
                nombre=nombre,
                carpeta_origen=str(carpeta_origen),
                total_archivos=1,
                total_procesados=1,
                iniciado_por=str(usuario),
            )
            documento = DocumentoDigitalizado.objects.create(
                lote=lote,
                ruta_archivo=f'{carpeta_origen}/PEL 001.pdf',
                nombre_archivo='PEL 001.pdf',
                extension='.pdf',
                peso_bytes=10,
                hash_archivo='abc123',
                es_pdf=True,
            )
            return lote, [documento]

        archivo = SimpleUploadedFile('PEL 001.pdf', b'%PDF-1.4 prueba', content_type='application/pdf')
        with patch('migracion_masiva_archivo.views.crear_lote_desde_carpeta', fake_crear_lote_desde_carpeta):
            response = self.client.post(
                '/api/migracion-masiva-archivo/cargas/',
                {'nombre': 'Carga QA', 'archivos': [archivo]},
                format='multipart',
            )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(LoteDocumental.objects.count(), 1)
        carga = LoteDocumental.objects.first()
        self.assertEqual(carga.total_archivos, 1)
        self.assertEqual(carga.documentos.count(), 1)

    def test_listado_requiere_autenticacion(self):
        self.client.force_authenticate(user=None)
        response = self.client.get('/api/migracion-masiva-archivo/cargas/')
        self.assertEqual(response.status_code, 401)
