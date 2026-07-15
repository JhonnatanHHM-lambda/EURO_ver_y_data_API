from collections import defaultdict
from pathlib import Path

from migracion_masiva_archivo.services.file_name_service import extraer_metadata_nombre_archivo, should_omit_system_file
from migracion_masiva_archivo.services.scanner_service import scan_file, scan_folder


MAX_GAP_CONSECUTIVOS = 20


def recuperar_faltantes_desde_secundaria(
    scanned_documents,
    carpeta_secundaria=None,
    max_gap=MAX_GAP_CONSECUTIVOS,
    inventariar_secundaria_completa=False,
):
    base_analysis = analizar_continuidad_base(scanned_documents, max_gap=max_gap)
    context = _build_context(scanned_documents, carpeta_secundaria, inventariar_secundaria_completa, base_analysis)

    secondary_documents = []
    if inventariar_secundaria_completa and carpeta_secundaria:
        secondary_documents = _scan_secondary_folder(carpeta_secundaria, context)
        _classify_missing_bases_in_secondary_inventory(
            base_analysis['faltantes'],
            secondary_documents,
            context,
        )
        recovered_documents = consolidar_inventarios(scanned_documents, secondary_documents, context)
    else:
        recovered_documents = _recover_only_missing_bases(
            base_analysis['faltantes'],
            carpeta_secundaria,
            context,
        )

    consolidated_documents = [*scanned_documents, *recovered_documents]
    subpartes_analysis = analizar_continuidad_subpartes(consolidated_documents)
    tomos_analysis = analizar_continuidad_tomos(consolidated_documents)
    if not inventariar_secundaria_completa:
        component_recovered = _recover_missing_components(
            subpartes_analysis.get('faltantes', []),
            tomos_analysis.get('faltantes', []),
            carpeta_secundaria,
            context,
            consolidated_documents,
        )
        recovered_documents.extend(component_recovered)
        consolidated_documents = [*scanned_documents, *recovered_documents]

    context['subpartes'] = _mark_unrecovered_subparts(
        analizar_continuidad_subpartes(consolidated_documents),
        carpeta_secundaria,
    )
    context['tomos'] = _mark_unrecovered_tomos(
        analizar_continuidad_tomos(consolidated_documents),
        carpeta_secundaria,
    )
    context['consolidado'] = analizar_continuidad_base(consolidated_documents, max_gap=max_gap)
    context['resumen'].update(_build_summary(context, scanned_documents, secondary_documents, recovered_documents))

    return recovered_documents, context


def analizar_continuidad(scanned_documents, max_gap=MAX_GAP_CONSECUTIVOS):
    return analizar_continuidad_base(scanned_documents, max_gap=max_gap)


def analizar_continuidad_base(scanned_documents, max_gap=MAX_GAP_CONSECUTIVOS):
    bases = sorted(
        {
            metadata['pel_base_nombre']
            for metadata in (_metadata_from_document(document) for document in scanned_documents)
            if metadata.get('nombre_reconocido') and metadata.get('pel_base_nombre')
        }
    )
    faltantes = []
    cambios_rango = []

    previous = None
    for current in bases:
        if previous is not None and current > previous + 1:
            gap = current - previous - 1
            if gap <= max_gap:
                for missing in range(previous + 1, current):
                    faltantes.append(
                        {
                            'pel_base': missing,
                            'anterior': previous,
                            'siguiente': current,
                            'estado_continuidad': 'FALTANTE_PEL_BASE',
                        }
                    )
            else:
                cambios_rango.append(
                    {
                        'desde': previous,
                        'hasta': current,
                        'faltantes_omitidos': gap,
                        'estado_continuidad': 'CAMBIO_DE_RANGO',
                    }
                )
        previous = current

    return {'faltantes': faltantes, 'cambios_rango': cambios_rango}


def analizar_continuidad_subpartes(scanned_documents):
    groups = defaultdict(set)
    for document in scanned_documents:
        metadata = _metadata_from_document(document)
        if not metadata.get('nombre_reconocido'):
            continue
        if metadata.get('tomo_nombre'):
            continue
        base = metadata.get('pel_base_nombre')
        subparte = metadata.get('subparte_nombre')
        if base and subparte:
            groups[base].add(int(subparte))

    faltantes = []
    for base, subpartes in sorted(groups.items()):
        min_subparte = min(subpartes)
        max_subparte = max(subpartes)
        if min_subparte > 1:
            for missing in range(1, min_subparte):
                faltantes.append(
                    {
                        'pel_base': base,
                        'subparte': missing,
                        'estado_continuidad': 'FALTA_PRINCIPAL_SUBPARTE',
                        'consecutivo_faltante': f'PEL {base} - {missing}',
                    }
                )
        for missing in range(min_subparte, max_subparte + 1):
            if missing not in subpartes:
                faltantes.append(
                    {
                        'pel_base': base,
                        'subparte': missing,
                        'estado_continuidad': 'FALTANTE_SUBPARTE',
                        'consecutivo_faltante': f'PEL {base} - {missing}',
                    }
                )

    return {'faltantes': faltantes}


def analizar_continuidad_tomos(scanned_documents):
    tomos_by_base = defaultdict(lambda: defaultdict(set))
    for document in scanned_documents:
        metadata = _metadata_from_document(document)
        base = metadata.get('pel_base_nombre')
        tomo = metadata.get('tomo_nombre')
        parte = metadata.get('parte_nombre')
        if base and tomo and parte:
            tomos_by_base[base][int(tomo)].add(int(parte))

    faltantes = []
    for base, tomos in sorted(tomos_by_base.items()):
        tomo_numbers = sorted(tomos)
        if not tomo_numbers:
            continue

        min_tomo = min(tomo_numbers)
        max_tomo = max(tomo_numbers)
        if min_tomo > 1:
            for missing_tomo in range(1, min_tomo):
                faltantes.append(
                    {
                        'pel_base': base,
                        'tomo': missing_tomo,
                        'estado_continuidad': 'FALTA_TOMO_INICIAL',
                        'consecutivo_faltante': f'PEL {base} TOMO {missing_tomo}',
                    }
                )

        for missing_tomo in range(min_tomo, max_tomo + 1):
            if missing_tomo not in tomos:
                faltantes.append(
                    {
                        'pel_base': base,
                        'tomo': missing_tomo,
                        'estado_continuidad': 'FALTANTE_TOMO',
                        'consecutivo_faltante': f'PEL {base} TOMO {missing_tomo}',
                    }
                )

        for tomo, partes in sorted(tomos.items()):
            min_parte = min(partes)
            max_parte = max(partes)
            if min_parte > 1:
                for missing_parte in range(1, min_parte):
                    faltantes.append(
                        {
                            'pel_base': base,
                            'tomo': tomo,
                            'parte': missing_parte,
                            'estado_continuidad': 'FALTA_PARTE_INICIAL',
                            'consecutivo_faltante': f'PEL {base} TOMO {tomo}-{missing_parte}',
                        }
                    )
            for missing_parte in range(min_parte, max_parte + 1):
                if missing_parte not in partes:
                    faltantes.append(
                        {
                            'pel_base': base,
                            'tomo': tomo,
                            'parte': missing_parte,
                            'estado_continuidad': 'FALTANTE_PARTE_TOMO',
                            'consecutivo_faltante': f'PEL {base} TOMO {tomo}-{missing_parte}',
                        }
                    )

    return {'faltantes': faltantes}


def buscar_pel_en_carpeta(carpeta_secundaria, pel_base):
    folder = Path(carpeta_secundaria)
    matches = []
    for path in sorted(folder.rglob('*')):
        if not path.is_file() or should_omit_system_file(path):
            continue
        metadata = extraer_metadata_nombre_archivo(path.name)
        if metadata.get('pel_base_nombre') == pel_base:
            matches.append(path)
    return matches


def inventariar_secundaria_completa(carpeta_secundaria):
    return scan_folder(carpeta_secundaria)


def consolidar_inventarios(primary_documents, secondary_documents, context=None):
    primary_by_identity = {
        _metadata_from_document(document).get('identidad_documental'): document
        for document in primary_documents
        if _metadata_from_document(document).get('identidad_documental')
    }
    consolidated_secondary = []

    for document in secondary_documents:
        metadata = _metadata_from_document(document)
        identity = metadata.get('identidad_documental')
        if identity and identity in primary_by_identity:
            if context is not None:
                context['duplicados_entre_carpetas'].append(
                    {
                        'identidad_documental': identity,
                        'nombre_archivo': document.get('nombre_archivo', ''),
                        'ruta_secundaria': document.get('ruta_archivo', ''),
                        'ruta_principal': primary_by_identity[identity].get('ruta_archivo', ''),
                        'estado_continuidad': 'DUPLICADO_ENTRE_CARPETAS',
                    }
                )
            continue
        consolidated_secondary.append(document)
        if context is not None:
            status = _secondary_inventory_status(metadata, context)
            context['recuperados'].append(
                {
                    'pel_base': metadata.get('pel_base_nombre'),
                    'ruta_archivo': document.get('ruta_archivo', ''),
                    'nombre_archivo': document.get('nombre_archivo', ''),
                    'estado_continuidad': status,
                    'observacion_continuidad': (
                        'Consecutivo faltante en carpeta principal encontrado en carpeta secundaria'
                        if status == 'FALTANTE_ENCONTRADO_EN_SECUNDARIA'
                        else 'Documento incluido desde inventario completo de carpeta secundaria'
                    ),
                }
            )

    return consolidated_secondary


def _recover_only_missing_bases(faltantes, carpeta_secundaria, context):
    missing_bases = [event['pel_base'] for event in faltantes]
    if not missing_bases:
        return []

    if not carpeta_secundaria:
        for pel_base in missing_bases:
            context['alertas'].append(_build_missing_alert(pel_base, 'CARPETA_SECUNDARIA_NO_CONFIGURADA'))
        return []

    secondary_folder = Path(carpeta_secundaria)
    if not secondary_folder.exists() or not secondary_folder.is_dir():
        for pel_base in missing_bases:
            context['alertas'].append(
                _build_missing_alert(
                    pel_base,
                    'CARPETA_SECUNDARIA_NO_ACCESIBLE',
                    observacion='Carpeta secundaria no existe o no es accesible',
                )
            )
        return []

    recovered_documents = []
    for pel_base in missing_bases:
        matches = buscar_pel_en_carpeta(secondary_folder, pel_base)
        if not matches:
            context['alertas'].append(_build_missing_alert(pel_base, 'FALTANTE_NO_ENCONTRADO'))
            continue

        for path in matches:
            file_info = scan_file(path)
            if not file_info:
                continue
            recovered_documents.append(file_info)
            context['recuperados'].append(
                {
                    'pel_base': pel_base,
                    'ruta_archivo': str(path),
                    'nombre_archivo': path.name,
                    'estado_continuidad': 'FALTANTE_ENCONTRADO_EN_SECUNDARIA',
                    'observacion_continuidad': (
                        'Consecutivo faltante en carpeta principal encontrado en carpeta secundaria'
                    ),
                }
            )
    return recovered_documents


def _recover_missing_components(subpartes, tomos, carpeta_secundaria, context, existing_documents):
    if not carpeta_secundaria:
        return []

    secondary_folder = Path(carpeta_secundaria)
    if not secondary_folder.exists() or not secondary_folder.is_dir():
        return []

    existing_identities = {
        _metadata_from_document(document).get('identidad_documental')
        for document in existing_documents
        if _metadata_from_document(document).get('identidad_documental')
    }
    recovered = []

    for event in subpartes:
        matches = _find_component_in_folder(
            secondary_folder,
            pel_base=event.get('pel_base'),
            subparte=event.get('subparte'),
        )
        recovered.extend(
            _scan_component_matches(
                matches,
                existing_identities,
                context,
                'FALTANTE_SUBPARTE_ENCONTRADO_EN_SECUNDARIA',
                event.get('consecutivo_faltante', ''),
            )
        )

    for event in tomos:
        matches = _find_component_in_folder(
            secondary_folder,
            pel_base=event.get('pel_base'),
            tomo=event.get('tomo'),
            parte=event.get('parte'),
        )
        recovered.extend(
            _scan_component_matches(
                matches,
                existing_identities,
                context,
                'FALTANTE_PARTE_TOMO_ENCONTRADO_EN_SECUNDARIA',
                event.get('consecutivo_faltante', ''),
            )
        )

    return recovered


def _find_component_in_folder(folder, pel_base=None, subparte=None, tomo=None, parte=None):
    matches = []
    for path in sorted(folder.rglob('*')):
        if not path.is_file() or should_omit_system_file(path):
            continue
        metadata = extraer_metadata_nombre_archivo(path.name)
        if metadata.get('pel_base_nombre') != pel_base:
            continue
        if subparte is not None and metadata.get('subparte_nombre') == subparte and not metadata.get('tomo_nombre'):
            matches.append(path)
        elif tomo is not None and parte is not None:
            if metadata.get('tomo_nombre') == tomo and metadata.get('parte_nombre') == parte:
                matches.append(path)
    return matches


def _scan_component_matches(matches, existing_identities, context, status, missing_label):
    recovered = []
    for path in matches:
        file_info = scan_file(path)
        if not file_info:
            continue
        identity = _metadata_from_document(file_info).get('identidad_documental')
        if identity and identity in existing_identities:
            continue
        if identity:
            existing_identities.add(identity)
        recovered.append(file_info)
        metadata = _metadata_from_document(file_info)
        context.setdefault('componentes_encontrados_secundaria', set()).add(identity or str(path))
        context['recuperados'].append(
            {
                'pel_base': metadata.get('pel_base_nombre'),
                'ruta_archivo': str(path),
                'nombre_archivo': path.name,
                'consecutivo_faltante': missing_label,
                'estado_continuidad': status,
                'observacion_continuidad': (
                    f'Componente faltante encontrado en carpeta secundaria: {missing_label}'
                ),
            }
        )
    return recovered


def _mark_unrecovered_subparts(analysis, carpeta_secundaria):
    if not carpeta_secundaria:
        return analysis
    for item in analysis.get('faltantes', []):
        if item.get('estado_continuidad') in {'FALTANTE_SUBPARTE', 'FALTA_PRINCIPAL_SUBPARTE'}:
            item['estado_continuidad'] = 'FALTANTE_SUBPARTE_NO_ENCONTRADO'
            item['observacion_continuidad'] = (
                f"No se encontro la subparte faltante en secundaria: {item.get('consecutivo_faltante')}"
            )
    return analysis


def _mark_unrecovered_tomos(analysis, carpeta_secundaria):
    if not carpeta_secundaria:
        return analysis
    for item in analysis.get('faltantes', []):
        if item.get('estado_continuidad') in {'FALTANTE_PARTE_TOMO', 'FALTA_PARTE_INICIAL'}:
            item['estado_continuidad'] = 'FALTANTE_PARTE_TOMO_NO_ENCONTRADO'
            item['observacion_continuidad'] = (
                f"No se encontro la parte de tomo faltante en secundaria: {item.get('consecutivo_faltante')}"
            )
    return analysis


def _classify_missing_bases_in_secondary_inventory(faltantes, secondary_documents, context):
    if not faltantes:
        return

    secondary_bases = {
        _metadata_from_document(document).get('pel_base_nombre')
        for document in secondary_documents
        if _metadata_from_document(document).get('pel_base_nombre')
    }

    for event in faltantes:
        pel_base = event.get('pel_base')
        if pel_base in secondary_bases:
            context.setdefault('faltantes_encontrados_secundaria', set()).add(pel_base)
        else:
            context['alertas'].append(_build_missing_alert(pel_base, 'FALTANTE_NO_ENCONTRADO'))


def _secondary_inventory_status(metadata, context):
    missing_found = context.get('faltantes_encontrados_secundaria', set())
    if metadata.get('pel_base_nombre') in missing_found:
        return 'FALTANTE_ENCONTRADO_EN_SECUNDARIA'
    return 'INVENTARIO_SECUNDARIA_COMPLETO'


def _scan_secondary_folder(carpeta_secundaria, context):
    if not carpeta_secundaria:
        return []

    secondary_folder = Path(carpeta_secundaria)
    if not secondary_folder.exists() or not secondary_folder.is_dir():
        context['alertas'].append(
            {
                'pel_base': '',
                'nombre_archivo': 'CARPETA_SECUNDARIA',
                'consecutivo_faltante': '',
                'estado_continuidad': 'CARPETA_SECUNDARIA_NO_ACCESIBLE',
                'observacion_continuidad': 'Carpeta secundaria no existe o no es accesible',
            }
        )
        return []
    return inventariar_secundaria_completa(secondary_folder)


def _build_context(scanned_documents, carpeta_secundaria, inventariar_secundaria_completa, base_analysis):
    return {
        'faltantes': base_analysis['faltantes'],
        'cambios_rango': base_analysis['cambios_rango'],
        'subpartes': {'faltantes': []},
        'tomos': {'faltantes': []},
        'consolidado': {'faltantes': [], 'cambios_rango': []},
        'recuperados': [],
        'alertas': [],
        'duplicados_entre_carpetas': [],
        'faltantes_encontrados_secundaria': set(),
        'componentes_encontrados_secundaria': set(),
        'resumen': {
            'total_documentos_principal': len(scanned_documents),
            'total_documentos_secundaria': 0,
            'total_documentos_consolidado': len(scanned_documents),
            'total_documentos_recuperados_secundaria': 0,
            'total_faltantes_detectados': len(base_analysis['faltantes']),
            'total_faltantes_encontrados_secundaria': 0,
            'total_faltantes_no_encontrados': 0,
            'total_cambios_de_rango': len(base_analysis['cambios_rango']),
            'total_duplicados_entre_carpetas': 0,
            'total_faltantes_subparte': 0,
            'total_faltantes_tomo': 0,
            'carpeta_secundaria_usada': bool(carpeta_secundaria),
            'carpeta_secundaria': str(carpeta_secundaria or ''),
            'inventario_secundaria_completo': bool(inventariar_secundaria_completa),
        },
    }


def _build_summary(context, primary_documents, secondary_documents, recovered_documents):
    missing_found = context.get('faltantes_encontrados_secundaria', set())
    component_found = context.get('componentes_encontrados_secundaria', set())
    missing_not_found = [
        item for item in context.get('alertas', [])
        if item.get('estado_continuidad') in {
            'FALTANTE_NO_ENCONTRADO',
            'CARPETA_SECUNDARIA_NO_CONFIGURADA',
            'CARPETA_SECUNDARIA_NO_ACCESIBLE',
        }
    ]
    component_missing_not_found = [
        item for group in (
            context.get('subpartes', {}).get('faltantes', []),
            context.get('tomos', {}).get('faltantes', []),
        )
        for item in group
        if item.get('estado_continuidad') in {
            'FALTANTE_SUBPARTE_NO_ENCONTRADO',
            'FALTANTE_PARTE_TOMO_NO_ENCONTRADO',
        }
    ]
    return {
        'total_documentos_principal': len(primary_documents),
        'total_documentos_secundaria': len(secondary_documents),
        'total_documentos_consolidado': len(primary_documents) + len(recovered_documents),
        'total_documentos_recuperados_secundaria': len(recovered_documents),
        'total_faltantes_encontrados_secundaria': len(missing_found) + len(component_found),
        'total_faltantes_no_encontrados': len(missing_not_found) + len(component_missing_not_found),
        'total_duplicados_entre_carpetas': len(context.get('duplicados_entre_carpetas', [])),
        'total_faltantes_subparte': len(context.get('subpartes', {}).get('faltantes', [])),
        'total_faltantes_tomo': len(context.get('tomos', {}).get('faltantes', [])),
    }


def _metadata_from_document(document):
    if hasattr(document, 'nombre_archivo'):
        return extraer_metadata_nombre_archivo(document.nombre_archivo)
    return extraer_metadata_nombre_archivo(document.get('nombre_archivo', ''))


def resolver_carpeta_secundaria_automatica(scanned_documents):
    """
    Detecta automáticamente la carpeta secundaria de búsqueda en el servidor 245.
    Ruta resuelta: Escritorio → GestionDocumental(192.168.1.245) →
                   ARCHIVO CENTRAL → DIGITALIZACIÓN → COMPROBANTES CONTABLES → {identificador}
    Devuelve la ruta como string o None si no se puede resolver.

    Depende de un acceso directo .lnk de Windows resuelto vía win32com, por lo que en
    el despliegue Web (worker Linux) no es portable. Se deshabilita explícitamente por
    configuración (MIGRACION_ARCHIVOS_CARPETA_SECUNDARIA_HABILITADA=False por defecto)
    en vez de dejar que win32com falle en silencio — ver INFRA_MIGRACION_MASIVA_ARCHIVO.md.
    """
    from django.conf import settings

    if not getattr(settings, 'MIGRACION_ARCHIVOS_CARPETA_SECUNDARIA_HABILITADA', False):
        import logging

        logging.getLogger('migracion_masiva_archivo').info(
            'Carpeta secundaria deshabilitada por configuracion '
            '(MIGRACION_ARCHIVOS_CARPETA_SECUNDARIA_HABILITADA=False). '
            'No se buscara PEL faltantes en el servidor 245.'
        )
        return None

    identifier = _detect_batch_identifier(scanned_documents)
    if not identifier:
        return None
    base = _find_245_base_path()
    if not base:
        return None
    return _build_comprobantes_contables_path(base, identifier)


def _detect_batch_identifier(scanned_documents):
    """Detecta el identificador dominante en el lote (PEL, PRO, RCG, etc.)."""
    counts = {}
    for doc in scanned_documents:
        metadata = _metadata_from_document(doc)
        ident = metadata.get('tipo_documento_nombre')
        if ident:
            counts[ident] = counts.get(ident, 0) + 1
    return max(counts, key=counts.get) if counts else None


def _find_245_base_path():
    """
    Busca la carpeta GestionDocumental(192.168.1.245) en el Escritorio/Desktop.
    Soporta carpetas reales y accesos directos .lnk.
    """
    import os

    desktops = []
    for var in ('USERPROFILE', 'HOMEPATH'):
        val = os.environ.get(var, '')
        if val:
            for subfolder in ('Desktop', 'Escritorio'):
                desktops.append(Path(val) / subfolder)

    for desktop in desktops:
        if not desktop.is_dir():
            continue
        try:
            for item in sorted(desktop.iterdir()):
                name_lower = item.name.lower()
                if '192.168.1.245' in name_lower or ('245' in name_lower and 'gestion' in name_lower):
                    if item.is_dir():
                        return item
                    if item.suffix.lower() == '.lnk':
                        resolved = _resolve_lnk_target(item)
                        if resolved and resolved.is_dir():
                            return resolved
        except (PermissionError, OSError):
            continue
    return None


def _resolve_lnk_target(lnk_path):
    """Resuelve el destino de un acceso directo .lnk de Windows."""
    try:
        import win32com.client
        shell = win32com.client.Dispatch('WScript.Shell')
        sc = shell.CreateShortCut(str(lnk_path))
        target = sc.TargetPath
        if target:
            return Path(target)
    except Exception:
        pass
    return None


def _build_comprobantes_contables_path(base, identifier):
    """
    Navega desde la raíz del servidor 245 hasta la subcarpeta del identificador.
    Prueba variantes de acento y capitalización para robustez.
    """
    for digita in ('DIGITALIZACIÓN', 'DIGITALIZACION', 'Digitalización', 'Digitalizacion'):
        for comprobantes in ('COMPROBANTES CONTABLES', 'Comprobantes Contables', 'comprobantes contables'):
            candidate = base / 'ARCHIVO CENTRAL' / digita / comprobantes / identifier
            if candidate.is_dir():
                return str(candidate)
    return None


def _build_missing_alert(pel_base, estado, observacion=''):
    default_observation = {
        'CARPETA_SECUNDARIA_NO_CONFIGURADA': 'Consecutivo faltante; no se configuro carpeta secundaria',
        'CARPETA_SECUNDARIA_NO_ACCESIBLE': 'Carpeta secundaria no existe o no es accesible',
        'FALTANTE_NO_ENCONTRADO': 'Consecutivo no encontrado en carpeta principal ni secundaria',
    }
    return {
        'pel_base': pel_base,
        'nombre_archivo': f'PEL {pel_base}',
        'consecutivo_faltante': f'PEL {pel_base}',
        'estado_continuidad': estado,
        'observacion_continuidad': observacion or default_observation.get(estado, ''),
    }


