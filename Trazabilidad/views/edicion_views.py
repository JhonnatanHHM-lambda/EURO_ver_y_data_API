"""
Vistas para editar registros individuales de trazabilidad.

PUT /api/trazabilidad/registros/<pk>/editar/
  - Campos de clasificación (estado_candidato, tipo_proceso): requieren justificación y quedan en el historial.
  - Campos de datos generales (nombre, cédula, celular, etc.): se actualizan directamente sin auditoría.
GET /api/trazabilidad/registros/<pk>/historial/
  - Devuelve el historial de cambios de clasificación del registro.
"""
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from django.db.models import Q

from EURO_ver_y_data.decoradores import require_permission
from Trazabilidad.models import (
    EmpleadoTrazabilidad, HistorialCambioRegistro,
    ESTADOS_CANDIDATO, TIPOS_PROCESO,
)


_ESTADOS_VALIDOS  = {k for k, _ in ESTADOS_CANDIDATO}
_PROCESOS_VALIDOS = {k for k, _ in TIPOS_PROCESO}

# Campos de datos generales que se pueden editar sin justificación
_CAMPOS_DATOS = {
    'nombre_completo', 'documento_id', 'tipo_documento',
    'celular', 'email', 'cargo', 'sede_id',
    'fecha_ingreso', 'fecha_retiro', 'motivo_retiro',
    'eps', 'pensiones', 'arl', 'tipo_sangre',
    'fecha_nacimiento', 'nivel_escolaridad', 'sexo',
    'expedida_en', 'barrio_municipio', 'direccion',
    'centro_costos', 'observaciones',
    'fecha_entrevista', 'psicologa',
    'motivo_inhabilitacion',
}


class EditarRegistroView(APIView):
    """
    PUT /api/trazabilidad/registros/<pk>/editar/

    Cuerpo esperado:
    {
        // Clasificación (ambas opcionales, requieren justificación si cambian):
        "estado_candidato": "HABILITADO",
        "tipo_proceso":     "RETIRADO",
        "justificacion":    "Corrección de error de carga",

        // Datos generales (opcionales, sin justificación):
        "nombre_completo": "JUAN CARLOS PEREZ",
        "celular":         "3001234567",
        ...
    }
    """

    @require_permission(['can_edit_registros'], app_label='Usuarios')
    def put(self, request, pk):
        try:
            registro = EmpleadoTrazabilidad.objects.get(pk=pk, estado=True)
        except EmpleadoTrazabilidad.DoesNotExist:
            return Response({'error': 'Registro no encontrado.'}, status=404)

        data = request.data
        estado_nuevo  = (data.get('estado_candidato') or '').strip().upper() or None
        proceso_nuevo = (data.get('tipo_proceso')     or '').strip().upper() or None
        justificacion = (data.get('justificacion')    or '').strip()

        # ── Validar clasificación ────────────────────────────────────────────
        if estado_nuevo and estado_nuevo not in _ESTADOS_VALIDOS:
            return Response({'error': f'Estado inválido: {estado_nuevo}'}, status=400)
        if proceso_nuevo and proceso_nuevo not in _PROCESOS_VALIDOS:
            return Response({'error': f'Proceso inválido: {proceso_nuevo}'}, status=400)

        hay_cambio_clasificacion = (
            (estado_nuevo  and estado_nuevo  != registro.estado_candidato) or
            (proceso_nuevo and proceso_nuevo != registro.tipo_proceso)
        )
        if hay_cambio_clasificacion and not justificacion:
            return Response(
                {'error': 'La justificación es obligatoria para cambiar el estado o el proceso.'},
                status=400
            )

        # ── Aplicar cambios de clasificación + auditoría ─────────────────────
        campos_actualizar = []
        entradas_historial = []

        if estado_nuevo and estado_nuevo != registro.estado_candidato:
            entradas_historial.append(HistorialCambioRegistro(
                registro       = registro,
                campo          = 'estado_candidato',
                valor_anterior = registro.estado_candidato,
                valor_nuevo    = estado_nuevo,
                justificacion  = justificacion,
                modificado_por = request.user,
            ))
            registro.estado_candidato = estado_nuevo
            campos_actualizar.append('estado_candidato')

        if proceso_nuevo and proceso_nuevo != registro.tipo_proceso:
            entradas_historial.append(HistorialCambioRegistro(
                registro       = registro,
                campo          = 'tipo_proceso',
                valor_anterior = registro.tipo_proceso,
                valor_nuevo    = proceso_nuevo,
                justificacion  = justificacion,
                modificado_por = request.user,
            ))
            registro.tipo_proceso = proceso_nuevo
            campos_actualizar.append('tipo_proceso')

        # ── Aplicar cambios de datos generales ───────────────────────────────
        _NULLABLE = {'sede_id', 'fecha_ingreso', 'fecha_retiro', 'fecha_nacimiento', 'fecha_entrevista'}
        for campo in _CAMPOS_DATOS:
            if campo in data:
                valor = data[campo]
                if valor == '' or valor is None:
                    valor = None if campo in _NULLABLE else ''
                elif campo == 'sede_id':
                    try:
                        valor = int(valor)
                    except (TypeError, ValueError):
                        valor = None
                setattr(registro, campo, valor)
                if campo not in campos_actualizar:
                    campos_actualizar.append(campo)

        if not campos_actualizar:
            return Response({'mensaje': 'Sin cambios — los valores ya son iguales.'}, status=200)

        campos_actualizar.append('modificado')
        registro.save(update_fields=campos_actualizar)

        if entradas_historial:
            HistorialCambioRegistro.objects.bulk_create(entradas_historial)

        # Propagar nombre y/o cédula a TODOS los registros de la misma persona
        propagados = 0
        doc_id_original = registro.documento_id  # puede haber cambiado si se editó
        campos_globales = {}
        if 'nombre_completo' in campos_actualizar:
            campos_globales['nombre_completo'] = registro.nombre_completo
        if 'documento_id' in campos_actualizar:
            campos_globales['documento_id'] = registro.documento_id

        if campos_globales:
            # Buscar todos los demás registros con la misma cédula original
            doc_id_busqueda = data.get('_doc_id_original') or doc_id_original
            propagados = (
                EmpleadoTrazabilidad.objects
                .filter(documento_id=doc_id_busqueda, estado=True)
                .exclude(pk=registro.pk)
                .update(**campos_globales)
            )

        return Response({
            'mensaje':          f'{len(campos_actualizar) - 1} campo(s) actualizado(s) correctamente.',
            'registro_id':      registro.id,
            'estado_candidato': registro.estado_candidato,
            'tipo_proceso':     registro.tipo_proceso,
            'propagados':       propagados,
        })


class CrearRegistroView(APIView):
    """
    POST /api/trazabilidad/registros/crear/
    Crea un registro individual de trazabilidad de forma manual.
    Campos obligatorios: documento_id, tipo_documento, nombre_completo.
    """

    @require_permission(['can_edit_registros'], app_label='Usuarios')
    def post(self, request):
        from Trazabilidad.models import Sede
        data = request.data

        documento_id   = (data.get('documento_id')   or '').strip()
        nombre_completo = (data.get('nombre_completo') or '').strip()
        tipo_documento = (data.get('tipo_documento')  or 'CC').strip().upper()

        if not documento_id:
            return Response({'error': 'El número de documento es obligatorio.'}, status=400)
        if not nombre_completo:
            return Response({'error': 'El nombre completo es obligatorio.'}, status=400)

        # Sede — acepta ID numérico
        sede = None
        sede_id = data.get('sede_id') or data.get('sede')
        if sede_id:
            try:
                sede = Sede.objects.get(pk=int(sede_id), estado=True)
            except (Sede.DoesNotExist, (TypeError, ValueError)):
                pass

        _NULLABLE = {'fecha_ingreso', 'fecha_retiro', 'fecha_nacimiento', 'fecha_entrevista'}
        _CAMPOS_OPCIONALES = {
            'cargo', 'tipo_proceso', 'estado_candidato',
            'motivo_retiro', 'motivo_inhabilitacion',
            'celular', 'email', 'direccion', 'barrio_municipio',
            'centro_costos', 'eps', 'pensiones', 'arl',
            'tipo_sangre', 'nivel_escolaridad', 'expedida_en', 'sexo',
            'observaciones', 'psicologa',
            'fecha_ingreso', 'fecha_retiro', 'fecha_nacimiento', 'fecha_entrevista',
        }

        kwargs = {
            'documento_id':   documento_id,
            'nombre_completo': nombre_completo,
            'tipo_documento': tipo_documento,
            'sede':           sede,
            'origen_datos':   'Registro manual',
            'fuente_carga':   'Registro manual',
            'cargado_por':    request.user,
        }

        for campo in _CAMPOS_OPCIONALES:
            if campo in data:
                valor = data[campo]
                if valor == '' or valor is None:
                    kwargs[campo] = None if campo in _NULLABLE else ''
                else:
                    kwargs[campo] = valor

        # Validar y parsear fechas
        from Trazabilidad.views.carga_views import _parsear_fecha
        for campo_fecha in _NULLABLE:
            if campo_fecha in kwargs and isinstance(kwargs[campo_fecha], str):
                parsed = _parsear_fecha(kwargs[campo_fecha])
                kwargs[campo_fecha] = parsed  # None si no parsea

        # Aplicar inferencia de proceso/estado igual que en carga masiva
        from Trazabilidad.views.carga_views import _inferir_proceso_y_estado
        _inferir_proceso_y_estado(kwargs, nombre_hoja='')

        registro = EmpleadoTrazabilidad.objects.create(**kwargs)

        return Response({
            'id':              registro.id,
            'documento_id':    registro.documento_id,
            'nombre_completo': registro.nombre_completo,
            'tipo_proceso':    registro.tipo_proceso,
            'estado_candidato':registro.estado_candidato,
            'mensaje':         'Registro creado correctamente.',
        }, status=201)


class HistorialRegistroView(APIView):
    """
    GET /api/trazabilidad/registros/<pk>/historial/
    Devuelve el historial de cambios de clasificación de un registro.
    """

    @require_permission(['can_view_trazabilidad'], app_label='Usuarios')
    def get(self, request, pk):
        try:
            registro = EmpleadoTrazabilidad.objects.get(pk=pk, estado=True)
        except EmpleadoTrazabilidad.DoesNotExist:
            return Response({'error': 'Registro no encontrado.'}, status=404)

        historial = (
            HistorialCambioRegistro.objects
            .filter(registro=registro)
            .select_related('modificado_por')
            .order_by('-creado')
        )

        data = []
        for h in historial:
            u = h.modificado_por
            data.append({
                'id':             h.id,
                'campo':          h.campo,
                'valor_anterior': h.valor_anterior,
                'valor_nuevo':    h.valor_nuevo,
                'justificacion':  h.justificacion,
                'fecha':          h.creado,
                'modificado_por': {
                    'nombre':   u.obtener_nombre_completo(),
                    'correo':   u.correo,
                    'telefono': u.telefono or '—',
                } if u else None,
            })

        return Response(data)


class AdminRegistrosView(APIView):
    """
    GET /api/trazabilidad/admin/registros/
    Lista paginada de TODOS los registros individuales con filtros avanzados.
    Permite búsqueda, filtrado y ordenamiento para gestión directa.
    """

    @require_permission(['can_edit_registros'], app_label='Usuarios')
    def get(self, request):
        qs = EmpleadoTrazabilidad.objects.filter(estado=True).select_related('sede', 'carga')

        # Filtros
        search = request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(
                Q(documento_id__icontains=search) |
                Q(nombre_completo__icontains=search)
            )

        for param, campo in [
            ('tipo_proceso',   'tipo_proceso'),
            ('estado',         'estado_candidato'),
            ('sede',           'sede_id'),
            ('origen',         'origen_datos__icontains'),
        ]:
            val = request.query_params.get(param, '').strip()
            if val:
                qs = qs.filter(**{campo: val})

        qs = qs.order_by('-creado')

        paginator = PageNumberPagination()
        paginator.page_size = int(request.query_params.get('page_size', 25))
        page = paginator.paginate_queryset(qs, request)

        data = []
        for r in page:
            tiene_historial = HistorialCambioRegistro.objects.filter(registro=r).exists()
            data.append({
                'id':               r.id,
                'documento_id':     r.documento_id,
                'tipo_documento':   r.tipo_documento,
                'nombre_completo':  r.nombre_completo,
                'tipo_proceso':     r.tipo_proceso,
                'estado_candidato': r.estado_candidato,
                'sede_id':          r.sede_id,
                'sede_nombre':      r.sede.nombre if r.sede else None,
                'sede_ciudad':      r.sede.ciudad if r.sede else None,
                'cargo':            r.cargo,
                'fecha_ingreso':    r.fecha_ingreso,
                'fecha_retiro':     r.fecha_retiro,
                'motivo_retiro':    r.motivo_retiro,
                'celular':          r.celular,
                'email':            r.email,
                'fecha_nacimiento': r.fecha_nacimiento,
                'sexo':             r.sexo,
                'tipo_sangre':      r.tipo_sangre,
                'nivel_escolaridad':r.nivel_escolaridad,
                'eps':              r.eps,
                'pensiones':        r.pensiones,
                'arl':              r.arl,
                'observaciones':    r.observaciones,
                'origen_datos':     r.origen_datos,
                'fuente_carga':     r.fuente_carga,
                'carga_id':         r.carga_id,
                'creado':           r.creado,
                # Metadatos para la UI
                'es_manual':        r.carga_id is None and r.fuente_carga == 'Registro manual',
                'puede_eliminar':   r.carga_id is None and not tiene_historial,
                'razon_bloqueo': (
                    'Este registro proviene de una carga masiva. Usa "Revertir carga" para eliminarlo.'
                    if r.carga_id else
                    'Este registro tiene cambios manuales registrados en el historial de auditoría.'
                    if tiene_historial else None
                ),
            })

        return paginator.get_paginated_response(data)


class EliminarRegistroView(APIView):
    """
    DELETE /api/trazabilidad/registros/<pk>/eliminar/
    Solo elimina registros manuales sin historial de cambios.
    """

    @require_permission(['can_edit_registros'], app_label='Usuarios')
    def delete(self, request, pk):
        try:
            registro = EmpleadoTrazabilidad.objects.get(pk=pk, estado=True)
        except EmpleadoTrazabilidad.DoesNotExist:
            return Response({'error': 'Registro no encontrado.'}, status=404)

        # Bloquear si proviene de una carga de Excel
        if registro.carga_id:
            return Response({
                'error': 'No se puede eliminar este registro porque proviene de una carga masiva de Excel. '
                         'Para eliminarlo, usa la opción "Revertir carga" en BD Centralizada.',
                'codigo': 'tiene_carga',
            }, status=400)

        # Bloquear si tiene historial de cambios manuales
        if HistorialCambioRegistro.objects.filter(registro=registro).exists():
            return Response({
                'error': 'No se puede eliminar este registro porque tiene cambios manuales registrados '
                         'en el historial de auditoría.',
                'codigo': 'tiene_historial',
            }, status=400)

        documento_id = registro.documento_id
        nombre       = registro.nombre_completo
        registro.delete()

        return Response({
            'mensaje':      f'Registro de {nombre} ({documento_id}) eliminado correctamente.',
            'documento_id': documento_id,
        })
