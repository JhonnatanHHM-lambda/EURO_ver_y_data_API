# Propuesta: migración del histórico de deduplicación SAIA (escritorio → Web)

Documento de propuesta, no de ejecución — no se corrió ningún script de migración de datos.
Parte de la Fase 7 (calidad/pruebas/datos históricos) del trabajo de migración de
`migracion_masiva_archivo`.

## El problema

`services/saia/historical_service.find_historical_saia_evidence()` es el mecanismo que evita
volver a cargar a SAIA un documento ya cargado antes — busca coincidencias de `hash_archivo`,
`identidad_documental` (derivada del nombre de archivo) y `ruta_archivo` entre TODOS los
`DocumentoDigitalizado` de la base Postgres del proyecto Web, sin importar el lote.

El aplicativo de escritorio (`Euro_gestion_documental_API`) tiene su propia base **SQLite**
(`db.sqlite3`) con años de historial de documentos ya cargados a SAIA desde ese equipo. Esa
información **nunca se migró** a Postgres. Consecuencia concreta: si un analista sube hoy, desde
la Web, una carpeta que contiene un PEL que ya se cargó a SAIA hace meses desde el escritorio, el
sistema Web no tiene forma de saberlo — `find_historical_saia_evidence()` no encontrará nada
porque no hay ningún `DocumentoDigitalizado`/`IntentoCargaSAIA` en Postgres que lo represente, y
el documento se re-cargará a SAIA como si fuera nuevo (duplicado real dentro de SAIA, un sistema
que además no tiene una API de deduplicación propia confiable — ver
`INFRA_MIGRACION_MASIVA_ARCHIVO.md` punto 3).

## Opciones

### Opción A — No migrar nada (aceptar el riesgo)

- **Qué implica:** el histórico previo al día del corte simplemente no se conoce; solo se
  deduplican documentos subidos por la Web desde que arranca.
- **Riesgo:** cualquier PEL que se vuelva a explorar (ej. un reintento manual, una carpeta que se
  vuelve a copiar) desde la fecha de corte hacia atrás puede duplicarse en SAIA sin que el sistema
  lo detecte.
- **Cuándo tiene sentido:** si el equipo de Eurosupermercados va a dejar de tocar esas carpetas
  antiguas y solo trabajará con documentos nuevos hacia adelante.

### Opción B — Migración completa (replicar el modelo tal cual)

- **Qué implica:** un comando de `manage.py` que lee `db.sqlite3` del escritorio (con el módulo
  `sqlite3` de Python, en modo solo lectura) y crea, por cada lote histórico, un `LoteDocumental`
  + sus `DocumentoDigitalizado` + `MetadataDocumento` + `IntentoCargaSAIA` equivalentes en Postgres.
- **Ventaja:** no requiere tocar `historical_service.py` — reutiliza las mismas tablas que ya
  consulta.
- **Desventajas:**
  - Los lotes/documentos importados no corresponden a cargas reales de la Web: `ruta_archivo`
    apuntaría a rutas del equipo de escritorio que no existen en el servidor, `carpeta_origen`
    tampoco. Cualquier reporte o KPI que cuente "lotes procesados"/"documentos totales" quedaría
    inflado con datos que no son actividad real de este sistema, a menos que se filtren
    explícitamente (ej. por un valor convencional en `iniciado_por`).
  - Volumen: si el histórico de escritorio tiene varios años de PEL, esto puede ser una cantidad
    considerable de filas — vale la pena medir el tamaño real de `db.sqlite3` antes de decidir.

### Opción C — Migración parcial: solo cargas exitosas a SAIA (recomendada)

- **Qué implica:** igual que la Opción B, pero **solo** se migran los `DocumentoDigitalizado` que
  tienen al menos un `IntentoCargaSAIA` con `exitoso=True` en el escritorio — que es exactamente
  el subconjunto de información que `find_historical_saia_evidence()` necesita para bloquear un
  reintento (`ya_cargado_saia`/`carga_saia_historica`). Se descartan los documentos que en su
  momento fallaron, quedaron en revisión manual o nunca se procesaron — ese detalle histórico no
  aporta al propósito de evitar duplicados y reduce mucho el volumen a migrar.
- **Convención propuesta:** marcar estos lotes importados con
  `iniciado_por='IMPORT_HISTORICO_ESCRITORIO'` (o un campo dedicado si se prefiere) para poder
  excluirlos fácilmente de reportes/KPIs de actividad real.
- **Ventaja sobre la Opción B:** mucho menor volumen de datos migrados, menor riesgo de arrastrar
  inconsistencias del modelo antiguo, y el propósito (deduplicación) queda cubierto igual.

### Opción D — Tabla de huella histórica dedicada (más limpia, más trabajo)

- **Qué implica:** en vez de fabricar `LoteDocumental`/`DocumentoDigitalizado` falsos, crear un
  modelo nuevo y pequeño, ej. `HistoricoCargaSAIAExterna` (hash_archivo, identidad_documental,
  asunto_saia, fecha_carga_saia, id_documento_saia), poblado desde el `db.sqlite3` del escritorio,
  y modificar `find_historical_saia_evidence()` para que también consulte esa tabla como una
  fuente adicional de coincidencias.
- **Ventaja:** separación limpia entre "actividad real de la Web" y "huella heredada del
  escritorio" — ningún reporte se contamina, no hay lotes ni documentos falsos.
- **Desventaja:** requiere modificar código de producción (`historical_service.py`), no solo un
  script de una sola vez — más trabajo, y ese código debe mantenerse mientras la tabla histórica
  siga siendo relevante.

## Recomendación

**Opción C** para salir del paso rápido y con bajo riesgo (reutiliza el modelo existente, migra
solo lo estrictamente necesario para deduplicar). Si el histórico de escritorio es muy grande o se
va a seguir alimentando por un tiempo largo en paralelo a la Web, vale la pena invertir en la
**Opción D** más adelante.

## Siguiente paso concreto (no ejecutado)

Antes de escribir el comando de migración, se necesita:
1. Confirmar dónde está el `db.sqlite3` real y su tamaño (`Euro_gestion_documental_API/db.sqlite3`
   en la máquina de escritorio, o su backup más reciente).
2. Contar cuántos `DocumentoDigitalizado` tienen `IntentoCargaSAIA.exitoso=True` en esa base —
   ese número es el volumen real a migrar bajo la Opción C.
3. Con esos dos datos, escribir un `manage.py` command dedicado (ej.
   `importar_historico_saia_escritorio --sqlite-path <ruta> --dry-run`) que:
   - Abra el SQLite en modo solo lectura (`sqlite3.connect(f'file:{ruta}?mode=ro', uri=True)`).
   - Por cada documento con carga exitosa, cree (o actualice si ya existe por hash) el
     `LoteDocumental`/`DocumentoDigitalizado`/`MetadataDocumento`/`IntentoCargaSAIA` equivalente en
     Postgres, dentro de una transacción, con `--dry-run` por defecto (solo imprime lo que haría) y
     una bandera explícita `--confirmar` para escribir de verdad.
   - Registre un resumen (cuántos importados, cuántos ya existían, cuántos se saltaron por datos
     incompletos) en `LogProcesoDocumental` o en la salida del comando.

Esto queda como una tarea aparte, a ejecutar cuando el usuario confirme cuál opción prefiere y
tenga acceso al `db.sqlite3` real para medir el volumen.
