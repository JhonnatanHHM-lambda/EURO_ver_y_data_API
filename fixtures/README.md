# Fixtures — Datos base del proyecto

Estos fixtures contienen los datos iniciales que deben existir en la base de datos
antes de que el proyecto sea utilizable. Se aplican una sola vez al desplegar.

## Archivos

| Archivo | Contenido | Registros |
|---|---|---|
| `01_trazabilidad_catalogos.json` | `Origen` + `Sede` | ~51 |
| `02_usuarios.json` | `Usuario` (usuarios del sistema) | 3 |
| `03_celery_beat.json` | `CrontabSchedule` + `PeriodicTask` | ~11 |
| `04_empleados_trazabilidad.json.gz` | `EmpleadoTrazabilidad` | ~39 322 |

## Cómo cargar

Desde la raíz del proyecto (donde está `manage.py`), ejecutar **en este orden**:

```bash
py -3.12 manage.py loaddata fixtures/01_trazabilidad_catalogos.json
py -3.12 manage.py loaddata fixtures/02_usuarios.json
py -3.12 manage.py loaddata fixtures/03_celery_beat.json
py -3.12 manage.py loaddata fixtures/04_empleados_trazabilidad.json.gz
```

O con el script de carga automática:

```bash
py -3.12 cargar_datos_base.py
```

## Notas

- Los fixtures de Dashboard (`RotacionDato`, `NominaDato`, `AusentismoDato`) **no están incluidos**
  porque se sincronizan automáticamente desde SIESA al ejecutar las tareas Celery.
- Los fixtures de `Contratos` (`AsignacionCentro`, `FirmaGH`) no están incluidos;
  deben configurarse manualmente en el admin después del despliegue.
- Las migraciones de Django deben aplicarse **antes** de cargar los fixtures:
  `py -3.12 manage.py migrate`
