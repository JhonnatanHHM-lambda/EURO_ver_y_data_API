from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.test import APIClient

from .models import DocumentoDigitalizado, IntentoCargaSAIA, LoteDocumental, MetadataDocumento
from .services.error_message_service import build_phase1_error_message, get_blocking_phase_error
from .services.extraction_service import extract_metadata_from_text
from .services.file_name_service import (
    extraer_metadata_nombre_archivo,
    has_ok_marker,
    is_ambiguous_pel_filename,
)
from .services.normalizacion_service import normalize_money, normalize_nit
from .services.relaciones_service import MIN_RELATION_CONFIDENCE, relacionar_documentos_lote
from .services.saia.historical_service import find_historical_saia_evidence
from .services.saia.routes import detect_document_identifier, resolve_saia_route_context

PERMISOS_MMA = (
    'can_view_migracion_masiva_archivo',
    'can_manage_migracion_masiva_archivo',
    'can_upload_migracion_masiva_archivo_saia',
)


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
        # Los permisos viven en Usuarios.Usuario.Meta (ver Fase 1 de la migración,
        # movidos desde LoteDocumental.Meta) — sin esto, cualquier endpoint
        # decorado con @require_permission responde 403 para un usuario nuevo.
        self.user.user_permissions.add(
            *Permission.objects.filter(codename__in=PERMISOS_MMA)
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_crea_carga_con_archivo(self):
        def fake_crear_lote_desde_carpeta(carpeta_origen, nombre, usuario, carpeta_secundaria=None):
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


class FileNameServiceTests(TestCase):
    """
    Casos portados/adaptados del app de escritorio (Documental/tests.py) que
    cubren reglas de negocio de reconocimiento de nombre de archivo — ver
    Fase 7 de la migración. Funciones puras, sin necesidad de base de datos.
    """

    # El consecutivo PEL exige 4 a 8 digitos (ver la regex de _extract_structured_name_metadata
    # en file_name_service.py) — por eso los casos de prueba usan "1234", no "123".

    def test_pel_simple(self):
        metadata = extraer_metadata_nombre_archivo('PEL 1234.pdf')
        self.assertEqual(metadata['pel_base_nombre'], 1234)
        self.assertEqual(metadata['tipo_nombre'], 'PEL_SIMPLE')
        self.assertEqual(metadata['identidad_documental'], 'PEL-1234')
        self.assertTrue(metadata['nombre_reconocido'])

    def test_pel_subparte(self):
        metadata = extraer_metadata_nombre_archivo('PEL 1234 - 2.pdf')
        self.assertEqual(metadata['pel_base_nombre'], 1234)
        self.assertEqual(metadata['subparte_nombre'], 2)
        self.assertEqual(metadata['identidad_documental'], 'PEL-1234-SUBPARTE-2')

    def test_pel_tomo_parte(self):
        metadata = extraer_metadata_nombre_archivo('PEL 1234 TOMO 1-2.pdf')
        self.assertEqual(metadata['tomo_nombre'], 1)
        self.assertEqual(metadata['parte_nombre'], 2)
        self.assertEqual(metadata['identidad_documental'], 'PEL-1234-TOMO-1-PARTE-2')

    def test_bancolombia_mes_simple(self):
        metadata = extraer_metadata_nombre_archivo('ENERO.pdf')
        self.assertEqual(metadata['tipo_documento_nombre'], 'BANCOLOMBIA')
        self.assertEqual(metadata['identidad_documental'], 'BANCOLOMBIA-ENERO')

    def test_bancolombia_mes_con_parte(self):
        metadata = extraer_metadata_nombre_archivo('ENERO - 2.pdf')
        self.assertEqual(metadata['subparte_nombre'], 2)
        self.assertEqual(metadata['identidad_documental'], 'BANCOLOMBIA-ENERO-2')

    def test_has_ok_marker_detecta_sufijo_ok(self):
        self.assertTrue(has_ok_marker('PEL 1234 OK.pdf'))
        self.assertTrue(has_ok_marker('PEL 1234_OK.pdf'))

    def test_has_ok_marker_no_falso_positivo(self):
        # 'OK' debe estar delimitado — no debe disparar con palabras que lo contienen.
        self.assertFalse(has_ok_marker('PEL 1234.pdf'))
        self.assertFalse(has_ok_marker('OKUPACION 1234.pdf'))

    def test_nombre_pel_ambiguo_por_palabra_sospechosa(self):
        self.assertTrue(is_ambiguous_pel_filename('PEL 1234 copia.pdf'))
        self.assertTrue(is_ambiguous_pel_filename('PEL 1234 version final.pdf'))

    def test_nombre_pel_ambiguo_por_multiples_consecutivos(self):
        # Dos consecutivos PEL distintos en el mismo nombre — no se sabe cual es el real.
        self.assertTrue(is_ambiguous_pel_filename('PEL 1234 PEL 4567.pdf'))

    def test_nombre_pel_no_ambiguo_caso_normal(self):
        self.assertFalse(is_ambiguous_pel_filename('PEL 1234.pdf'))
        self.assertFalse(is_ambiguous_pel_filename('PEL 1234 - 2.pdf'))


class RouteDetectionTests(TestCase):
    """
    Casos de deteccion de ruta SAIA (services/saia/routes.py). detect_document_identifier
    solo lee atributos (getattr), asi que no requiere guardar registros en BD.
    """

    def _documento(self, nombre_archivo='', ruta_archivo='', consecutivo='', tipo_documento='', datos_pel=None):
        metadata = SimpleNamespace(
            consecutivo=consecutivo,
            tipo_documento=tipo_documento,
            observaciones='',
            datos_pel=datos_pel or {},
        )
        documento = SimpleNamespace(
            nombre_archivo=nombre_archivo,
            ruta_archivo=ruta_archivo,
            metadata=metadata,
        )
        return documento, metadata

    def test_pel_simple(self):
        documento, metadata = self._documento(nombre_archivo='PEL 123.pdf', ruta_archivo='C:/PEL/PEL 123.pdf')
        self.assertEqual(detect_document_identifier(documento, metadata), 'PEL')

    def test_bancolombia_por_nombre_de_mes(self):
        documento, metadata = self._documento(nombre_archivo='ENERO.pdf', ruta_archivo='C:/BANCOS/BANCOLOMBIA/ENERO.pdf')
        self.assertEqual(detect_document_identifier(documento, metadata), 'BANCOLOMBIA')

    def test_corficolombiana_gana_sobre_bancolombia(self):
        # 'FIDUCIARIA' esta en BANCOLOMBIA_IDENTIFIERS, pero la ruta de Corficolombiana
        # debe detectarse primero (routes.py la chequea explicitamente antes de Bancolombia).
        documento, metadata = self._documento(
            nombre_archivo='ENERO.pdf',
            ruta_archivo='C:/BANCOS/FIDUCIARIA CORFICOLOMBIANA/2024/ENERO.pdf',
        )
        self.assertEqual(detect_document_identifier(documento, metadata), 'CORFICOLOMBIANA')

    def test_corbanca_gana_sobre_bancolombia_por_nombre_de_mes_compartido(self):
        # Corbanca comparte nombres de mes con Bancolombia — la ruta debe desambiguar.
        documento, metadata = self._documento(nombre_archivo='ENERO.pdf', ruta_archivo='C:/BANCOS/CORBANCA/ENERO.pdf')
        self.assertEqual(detect_document_identifier(documento, metadata), 'CORBANCA')

    def test_retencion_ica(self):
        documento, metadata = self._documento(
            nombre_archivo='RICA 2024.pdf',
            ruta_archivo='C:/IMPUESTOS/RETENCION DE ICA/RICA 2024.pdf',
        )
        self.assertEqual(detect_document_identifier(documento, metadata), 'RICA')

    def test_egresos_efectivo_ege(self):
        documento, metadata = self._documento(
            nombre_archivo='EGE 2024.pdf',
            ruta_archivo='C:/EGRESOS/EGRESOS EFECTIVO/EGE 2024.pdf',
        )
        self.assertEqual(detect_document_identifier(documento, metadata), 'EGE')

    def test_cartera_colectiva_abierta_cca(self):
        documento, metadata = self._documento(
            nombre_archivo='ENERO.pdf',
            ruta_archivo='C:/CARTERA COLECTIVA ABIERTA/ENERO.pdf',
        )
        self.assertEqual(detect_document_identifier(documento, metadata), 'CCA')

    def test_sin_identificador_retorna_vacio(self):
        documento, metadata = self._documento(nombre_archivo='factura_random.pdf', ruta_archivo='C:/otros/factura_random.pdf')
        self.assertEqual(detect_document_identifier(documento, metadata), '')

    def test_corficolombiana_route_context_resolves_year_from_metadata(self):
        # El app de escritorio (Documental/tests.py) nunca tuvo un test de Corficolombiana
        # pese a tener el mismo patron que Colpatria/Corbanca/Correval — cerrando ese hueco aqui.
        documento, metadata = self._documento(
            nombre_archivo='ENERO.pdf',
            ruta_archivo='C:/BANCOS/FIDUCIARIA CORFICOLOMBIANA/ENERO.pdf',
            datos_pel={'corficolombiana_año': 2016},
        )
        self.assertEqual(detect_document_identifier(documento, metadata), 'CORFICOLOMBIANA')
        year, _subexpediente = resolve_saia_route_context(documento, 'CORFICOLOMBIANA')
        self.assertEqual(year, 2016)


class ErrorMessageServiceTests(TestCase):
    """Catalogo de mensajes de error de Fase 1 (services/error_message_service.py)."""

    def test_ok_detectado(self):
        resultado = build_phase1_error_message('', {'contiene_ok': True})
        self.assertEqual(resultado['codigo_error_usuario'], 'OK_DETECTADO')

    def test_archivo_vacio_bloquea_saia(self):
        resultado = build_phase1_error_message('', {'archivo_vacio': True})
        self.assertEqual(resultado['codigo_error_usuario'], 'ARCHIVO_VACIO')
        self.assertTrue(resultado['bloquea_saia'])
        self.assertTrue(resultado['bloquea_fase_2'])

    def test_duplicado_en_lote(self):
        resultado = build_phase1_error_message('', {'es_duplicado': True})
        self.assertEqual(resultado['codigo_error_usuario'], 'DUPLICADO_LOTE')

    def test_sin_error_no_clasifica_codigo(self):
        resultado = build_phase1_error_message('', {})
        self.assertEqual(resultado['codigo_error_usuario'], '')


class RelacionesServiceTests(TestCase):
    """
    Relaciones documento-soporte (services/relaciones_service.py) — casos de
    subpartes/tomos y el umbral MIN_RELATION_CONFIDENCE=80.
    """

    def setUp(self):
        self.lote = LoteDocumental.objects.create(nombre='Lote relaciones', carpeta_origen='C:/tmp')

    def _crear_documento(self, nombre_archivo, consecutivo, estado='VALIDADO'):
        documento = DocumentoDigitalizado.objects.create(
            lote=self.lote,
            ruta_archivo=f'C:/tmp/{nombre_archivo}',
            nombre_archivo=nombre_archivo,
            extension='.pdf',
            estado_proceso=estado,
        )
        MetadataDocumento.objects.create(documento=documento, consecutivo=consecutivo)
        documento.refresh_from_db()
        return documento

    def test_relaciona_pel_principal_con_subparte(self):
        principal = self._crear_documento('PEL 5000.pdf', 'PEL 5000')
        subparte = self._crear_documento('PEL 5000 - 2.pdf', 'PEL 5000 -2')

        resultado = relacionar_documentos_lote(self.lote)

        self.assertEqual(len(resultado['relaciones']), 1)
        detalle = resultado['detalle_relaciones'][0]
        self.assertGreaterEqual(detalle['confianza'], MIN_RELATION_CONFIDENCE)
        principal.refresh_from_db()
        subparte.refresh_from_db()
        self.assertEqual(principal.estado_proceso, 'RELACIONADO')
        self.assertEqual(subparte.estado_proceso, 'RELACIONADO')

    def test_relaciona_tomo_1_1_con_tomo_1_2(self):
        self._crear_documento('PEL 7000 TOMO 1-1.pdf', 'PEL 7000 TOMO 1-1')
        self._crear_documento('PEL 7000 TOMO 1-2.pdf', 'PEL 7000 TOMO 1-2')

        resultado = relacionar_documentos_lote(self.lote)

        self.assertEqual(len(resultado['relaciones']), 1)

    def test_subparte_huerfana_sin_principal_no_genera_relacion(self):
        # Solo existe la subparte -2, falta el documento principal -1: no debe
        # inventarse una relacion, y el grupo debe reportarse como huerfano.
        self._crear_documento('PEL 9000 - 2.pdf', 'PEL 9000 -2')

        resultado = relacionar_documentos_lote(self.lote)

        self.assertEqual(len(resultado['relaciones']), 0)
        self.assertTrue(any(g['codigo_error'] == 'SUBPARTE_HUERFANA' for g in resultado['grupos_ambiguos']))

    def test_documento_unico_no_requiere_relacion(self):
        unico = self._crear_documento('PEL 1111.pdf', 'PEL 1111')

        resultado = relacionar_documentos_lote(self.lote)

        self.assertEqual(len(resultado['relaciones']), 0)
        unico.refresh_from_db()
        # Un PEL simple aislado se acepta en Fase 4 como documento individual —
        # relacionar_documentos_lote no debe forzarlo a RELACIONADO.
        self.assertEqual(unico.estado_proceso, 'VALIDADO')


class HistoricalDedupTests(TestCase):
    """
    Deduplicacion contra el historico (services/saia/historical_service.py) —
    incluye el caso de un documento ya cargado exitosamente a SAIA en un lote
    anterior, que debe bloquear el reintento en el lote nuevo.
    """

    def setUp(self):
        self.lote_historico = LoteDocumental.objects.create(nombre='Lote historico', carpeta_origen='C:/tmp')
        self.lote_nuevo = LoteDocumental.objects.create(nombre='Lote nuevo', carpeta_origen='C:/tmp')

    def test_duplicado_por_hash(self):
        historico = DocumentoDigitalizado.objects.create(
            lote=self.lote_historico, ruta_archivo='C:/tmp/viejo/PEL 200.pdf',
            nombre_archivo='PEL 200.pdf', extension='.pdf', hash_archivo='hash-identico',
        )
        nuevo = DocumentoDigitalizado.objects.create(
            lote=self.lote_nuevo, ruta_archivo='C:/tmp/nuevo/PEL 200.pdf',
            nombre_archivo='PEL 200.pdf', extension='.pdf', hash_archivo='hash-identico',
        )

        evidencia = find_historical_saia_evidence(nuevo)

        self.assertIsNotNone(evidencia)
        self.assertIn('HASH', evidencia['duplicado_historico_por'])
        self.assertEqual(evidencia['documento_historico_id'], historico.id)

    def test_documento_ya_cargado_a_saia_bloquea_reintento(self):
        historico = DocumentoDigitalizado.objects.create(
            lote=self.lote_historico, ruta_archivo='C:/tmp/viejo/PEL 300.pdf',
            nombre_archivo='PEL 300.pdf', extension='.pdf', hash_archivo='hash-300',
        )
        IntentoCargaSAIA.objects.create(
            documento=historico, numero_intento=1, exitoso=True, id_documento_saia='SAIA-300',
        )
        nuevo = DocumentoDigitalizado.objects.create(
            lote=self.lote_nuevo, ruta_archivo='C:/tmp/nuevo/PEL 300.pdf',
            nombre_archivo='PEL 300.pdf', extension='.pdf', hash_archivo='hash-300',
        )

        evidencia = find_historical_saia_evidence(nuevo)

        self.assertTrue(evidencia['ya_cargado_saia'])
        self.assertEqual(evidencia['codigo_error_usuario'], 'YA_CARGADO_SAIA_HISTORICO')

    def test_documento_unico_sin_coincidencias_no_bloquea(self):
        nuevo = DocumentoDigitalizado.objects.create(
            lote=self.lote_nuevo, ruta_archivo='C:/tmp/nuevo/PEL 999.pdf',
            nombre_archivo='PEL 999.pdf', extension='.pdf', hash_archivo='hash-unico-999',
        )

        evidencia = find_historical_saia_evidence(nuevo)

        self.assertIsNone(evidencia)


class MarcadoOkRegressionTests(TestCase):
    """
    Regresion de la migracion 0007_documentodigitalizado_marcado_ok del app de
    escritorio: un documento ya cargado exitosamente a SAIA, cuyo archivo local
    fue renombrado agregando " OK", NO debe mostrarse como error de Fase 1 en el
    dashboard. El desktop app nunca tuvo un test que cubriera este caso (ver
    Fase 7) — _document_phase_context() en error_message_service.py solo marca
    'contiene_ok' si el documento NO esta marcado_ok=True.
    """

    def setUp(self):
        self.lote = LoteDocumental.objects.create(nombre='Lote marcado_ok', carpeta_origen='C:/tmp')

    def _documento_cargado(self, nombre_archivo, marcado_ok):
        # texto_extraido no vacio: un documento CARGADO_SAIA real ya paso OCR/Fase 2,
        # asi que se llena aqui para que get_blocking_phase_error no confunda esta
        # prueba con un error de Fase 2 (OCR_SIN_TEXTO) no relacionado con marcado_ok.
        return DocumentoDigitalizado.objects.create(
            lote=self.lote,
            ruta_archivo=f'C:/tmp/{nombre_archivo}',
            nombre_archivo=nombre_archivo,
            extension='.pdf',
            estado_proceso='CARGADO_SAIA',
            marcado_ok=marcado_ok,
            # >80 caracteres: OCR_TEXTO_INSUFICIENTE se dispara con menos (ver
            # error_message_service.py, umbral de texto_extraido_len < 80).
            texto_extraido='PAGOS ELECTRONICOS MAY-PEL-00001234 CONSECUTIVO VALIDADO CORRECTAMENTE PARA PRUEBA',
        )

    def test_documento_cargado_y_marcado_ok_no_se_reporta_como_error(self):
        documento = self._documento_cargado('PEL 1234 OK.pdf', marcado_ok=True)

        self.assertIsNone(get_blocking_phase_error(documento))

    def test_documento_cargado_sin_marcar_ok_si_se_reporta_como_error(self):
        # Mismo documento, pero sin el flag — reproduce el bug que arreglo la migracion 0007:
        # antes de existir marcado_ok, este caso se mostraba incorrectamente como error F1.
        documento = self._documento_cargado('PEL 5678 OK.pdf', marcado_ok=False)

        error = get_blocking_phase_error(documento)

        self.assertIsNotNone(error)
        self.assertEqual(error['codigo_error_usuario'], 'OK_DETECTADO')


class BancoExtractionTests(TestCase):
    """
    Extraccion de metadata (services/extraction_service.py) para las rutas
    bancarias con estructura carpeta/año/mes (BBVA, Davivienda, Bogota) y para
    Retencion ICA — ver Fase 7 (punto 2 del recuento del 2026-07-14): el agente
    que reviso Documental/tests.py confirmo que el escritorio SI tenia pruebas
    extensas para estos tipos, y que nunca se verificaron aqui tras portar el
    codigo. NOTA: INC, IND e Impuesto al Consumo NO tienen una funcion de
    extraccion dedicada en este extraction_service.py (a diferencia del
    escritorio) — caen al bloque generico tipo-PEL al final de
    extract_metadata_from_text(). Eso no es una falta de pruebas, es una
    funcionalidad que no se porto; no se escribe un test aqui para no dar
    una falsa sensacion de cobertura.
    """

    def test_bbva_extraccion_clasifica_carpeta_nombre_y_mes(self):
        resultado = extract_metadata_from_text(
            text='CONCILIACION BANCARIA BANCO BBVA Periodo 2016/12 Diciembre de 2016',
            filename='12.DICIEMBRE.pdf',
            ruta_archivo='C:/BANCOS/BBVA/CONCILIACIONES BANCARIAS 2016/12.DICIEMBRE.pdf',
        )
        self.assertEqual(resultado['tipo_documento'], 'DOCUMENTO_BBVA')
        datos = resultado['datos_pel']
        self.assertEqual(datos['bbva_año'], 2016)
        self.assertEqual(datos['bbva_mes_num'], 12)
        self.assertTrue(datos['bbva_titulo_ok'])
        self.assertTrue(datos['bbva_banco_ok'])
        self.assertEqual(datos['bbva_inconsistencias'], [])
        self.assertFalse(resultado['requiere_revision'])

    def test_bbva_extraccion_marca_discrepancia_de_mes_entre_nombre_y_pdf(self):
        resultado = extract_metadata_from_text(
            text='CONCILIACION BANCARIA BANCO BBVA Noviembre de 2016',
            filename='10.OCTUBRE.pdf',
            ruta_archivo='C:/BANCOS/BBVA/CONCILIACIONES BANCARIAS 2016/10.OCTUBRE.pdf',
        )
        self.assertTrue(resultado['requiere_revision'])
        inconsistencias = ' | '.join(resultado['datos_pel']['bbva_inconsistencias'])
        self.assertIn('mes nombre', inconsistencias)

    def test_bbva_extraccion_marca_banco_no_confirmado_en_pdf(self):
        resultado = extract_metadata_from_text(
            text='CONCILIACION BANCARIA BANCO DAVIVIENDA Periodo 2016/6',
            filename='06.JUNIO.pdf',
            ruta_archivo='C:/BANCOS/BBVA/CONCILIACIONES BANCARIAS 2016/06.JUNIO.pdf',
        )
        self.assertFalse(resultado['datos_pel']['bbva_banco_ok'])
        self.assertIn('BANCO BBVA', ' | '.join(resultado['datos_pel']['bbva_inconsistencias']))

    def test_davivienda_extraccion_clasifica_carpeta_nombre_y_mes(self):
        resultado = extract_metadata_from_text(
            text='CONCILIACION BANCARIA BANCO DAVIVIENDA Periodo 2017/3',
            filename='03.MARZO.pdf',
            ruta_archivo='C:/BANCOS/DAVIVIENDA/CONCILIACIONES BANCARIAS 2017/03.MARZO.pdf',
        )
        self.assertEqual(resultado['tipo_documento'], 'DOCUMENTO_DAVIVIENDA')
        datos = resultado['datos_pel']
        self.assertEqual(datos['davivienda_año'], 2017)
        self.assertEqual(datos['davivienda_mes_num'], 3)
        self.assertFalse(resultado['requiere_revision'])

    def test_davivienda_extraccion_marca_discrepancia_de_anio_entre_carpeta_y_pdf(self):
        resultado = extract_metadata_from_text(
            text='CONCILIACION BANCARIA BANCO DAVIVIENDA Periodo 2018/5',
            filename='05.MAYO.pdf',
            ruta_archivo='C:/BANCOS/DAVIVIENDA/CONCILIACIONES BANCARIAS 2017/05.MAYO.pdf',
        )
        self.assertTrue(resultado['requiere_revision'])
        self.assertIn('anio carpeta', ' | '.join(resultado['datos_pel']['davivienda_inconsistencias']))

    def test_bogota_extraccion_clasifica_carpeta_nombre_y_mes(self):
        resultado = extract_metadata_from_text(
            text='CONCILIACION BANCARIA BANCO DE BOGOTA Periodo 2016/1',
            filename='01.ENERO.pdf',
            ruta_archivo='C:/BANCOS/BOGOTA/CONCILIACIONES BANCARIAS 2016/01.ENERO.pdf',
        )
        self.assertEqual(resultado['tipo_documento'], 'DOCUMENTO_BOGOTA')
        self.assertFalse(resultado['requiere_revision'])

    def test_bogota_acepta_carpeta_de_rango_de_anios_y_credito_rotativo(self):
        # El Banco de Bogota tiene carpetas tipo "ENERO - SEPTIEMBRE 2015 - 2016"
        # que cubren dos años, y una ruta alterna "CREDITO ROTATIVO" (no solo
        # "CONCILIACION BANCARIA") — ambas particularidades vistas en el escritorio.
        resultado = extract_metadata_from_text(
            text='CREDITO ROTATIVO BANCO DE BOGOTA Periodo 2016/9',
            filename='09.SEPTIEMBRE.pdf',
            ruta_archivo='C:/BANCOS/BOGOTA/ENERO - SEPTIEMBRE 2015 - 2016/09.SEPTIEMBRE.pdf',
        )
        datos = resultado['datos_pel']
        self.assertTrue(datos['bogota_titulo_ok'])
        self.assertEqual(datos['bogota_año'], 2016)
        self.assertIn(2016, datos['bogota_años_carpeta'])
        self.assertFalse(resultado['requiere_revision'])

    def test_retencion_ica_clasifica_bimestre_titulo_y_anio(self):
        # Sin mes explicito en el texto/nombre: el bimestre (5) se convierte a
        # mes (5*2=10, octubre) — misma regla que el escritorio.
        resultado = extract_metadata_from_text(
            text='DECLARACION BIMESTRAL RETENCION ICA BIMESTRE 5 BELLO 2014',
            filename='DECLARACION BIMESTRE 5 BELLO 2014.pdf',
            ruta_archivo='C:/IMPUESTOS/Declaracion de Retencion de ICA/2014/DECLARACION BIMESTRE 5 BELLO 2014.pdf',
        )
        self.assertEqual(resultado['tipo_documento'], 'DOCUMENTO_RETENCION_ICA')
        self.assertEqual(resultado['datos_pel']['retencion_ica_bimestre'], 5)
        self.assertEqual(resultado['fecha_documento'].month, 10)
        self.assertFalse(resultado['requiere_revision'])

    def test_retencion_ica_marca_discrepancia_de_anio_entre_carpeta_y_pdf(self):
        resultado = extract_metadata_from_text(
            text='DECLARACION BIMESTRAL RETENCION ICA BIMESTRE 3 AÑO 2016',
            filename='DECLARACION BIMESTRE 3.pdf',
            ruta_archivo='C:/IMPUESTOS/Declaracion de Retencion de ICA/2015/DECLARACION BIMESTRE 3.pdf',
        )
        self.assertTrue(resultado['requiere_revision'])
        # confianza baja (60) porque hay discrepancia de año, aunque el titulo si se confirma
        self.assertEqual(resultado['confianza'], 60)


class AjusteContableYImpuestoConsumoExtractionTests(TestCase):
    """
    Impuesto al Consumo (recibo DIAN 490, bimestral IC1-IC6 + auxiliar anual) e
    INC/IND (ajustes contables internos) — services/extraction_service.py.

    Estas 3 funciones de extraccion (_extract_impuesto_consumo_metadata,
    _extract_inc_metadata, _extract_ind_metadata) NO estaban portadas del app
    de escritorio hasta ahora — el codigo caia al bloque generico tipo-PEL, sin
    ninguna de estas reglas especificas. Se portaron completas desde
    Euro_gestion_documental_API/Documental/services/extraction_service.py
    (ver Fase 7, punto 2 del recuento del 2026-07-14).
    """

    def test_impuesto_consumo_bimestral_clasifica_bimestre_anio_valor_y_nit(self):
        resultado = extract_metadata_from_text(
            text=(
                'RECIBO OFICIAL DE PAGO DE IMPUESTOS NACIONALES PERIODO 3 AÑO 2018 '
                'CONCEPTO 21 VALOR PAGO IMPUESTO 1.234.567 FECHA PARA EL PAGO 2018-05-15 '
                'NIT 900123456-7'
            ),
            filename='IC3 2018.pdf',
            ruta_archivo='C:/IMPUESTOS/Impuesto al Consumo/2018/IC3 2018.pdf',
        )
        self.assertEqual(resultado['tipo_documento'], 'DOCUMENTO_IMPUESTO_CONSUMO')
        self.assertEqual(resultado['datos_pel']['impuesto_consumo_bimestre'], 3)
        self.assertEqual(resultado['datos_pel']['impuesto_consumo_año'], 2018)
        self.assertEqual(resultado['valor'], normalize_money('1.234.567'))
        self.assertEqual(resultado['nit'], normalize_nit('900123456-7'))
        self.assertFalse(resultado['requiere_revision'])

    def test_impuesto_consumo_anual_usa_auxiliar_contable_sin_bimestre(self):
        # Sin el titulo del recibo DIAN 490, pero con el auxiliar contable
        # (Consultas Cuentas / PUC): es el septimo expediente anual, no uno
        # de los 6 recibos bimestrales.
        resultado = extract_metadata_from_text(
            text='CONSULTAS CUENTAS PUC PLAN UNICO DE CUENTAS AUXILIAR: 24780101 AÑO 2019',
            filename='auxiliar impuesto consumo 2019.pdf',
            ruta_archivo='C:/IMPUESTOS/Impuesto al Consumo/2019/auxiliar impuesto consumo 2019.pdf',
        )
        self.assertEqual(resultado['tipo_documento'], 'DOCUMENTO_IMPUESTO_CONSUMO_ANUAL')
        self.assertEqual(resultado['datos_pel']['impuesto_consumo_anual_año'], 2019)
        self.assertTrue(resultado['datos_pel']['impuesto_consumo_anual_ledger_ok'])

    def test_inc_extraccion_confia_en_nombre_de_archivo_para_el_numero(self):
        resultado = extract_metadata_from_text(
            text='AJUSTES CONTABLES INDIRECTOS CONTABLES CIERRE FECHA: 15/03/20 MAY-INC-00000185',
            filename='INC 185.pdf',
            ruta_archivo='C:/CONTABILIDAD/INC/2020/INC 185.pdf',
        )
        self.assertEqual(resultado['tipo_documento'], 'DOCUMENTO_INC')
        self.assertEqual(resultado['consecutivo'], 'MAY-INC-00000185')
        self.assertEqual(resultado['datos_pel']['inc_año'], 2020)
        self.assertFalse(resultado['requiere_revision'])

    def test_ind_marca_discrepancia_de_sede_entre_encabezado_y_carpeta(self):
        # IND organiza por sede en sub-carpetas (ej. BARBOSA); la sede impresa
        # en el encabezado del documento debe coincidir con esa carpeta.
        resultado = extract_metadata_from_text(
            text=(
                'AJUSTES CONTABLES INDIRECTOS CONTABLES FECHA: 10/02/16 ADMINISTRACION '
                'TERCERO: EURO SUPERMERCADOS ADM-IND-00000041'
            ),
            filename='IND 41.pdf',
            ruta_archivo='C:/CONTABILIDAD/IND/2016/BARBOSA/IND 41.pdf',
        )
        self.assertEqual(resultado['tipo_documento'], 'DOCUMENTO_IND')
        self.assertTrue(resultado['requiere_revision'])
        self.assertEqual(resultado['datos_pel']['ind_sede'], 'BARBOSA')
        self.assertEqual(resultado['datos_pel']['ind_sede_encabezado'], 'ADMINISTRACION')
        self.assertIn(
            'sede del encabezado',
            ' | '.join(resultado['datos_pel']['ind_inconsistencias']),
        )
        # La discrepancia de sede topa la confianza en 65 aunque numero/fecha esten bien
        self.assertLessEqual(resultado['confianza'], 65)
