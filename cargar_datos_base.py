# -*- coding: utf-8 -*-
"""
Carga los fixtures de datos base en el orden correcto.
Ejecutar después de `manage.py migrate` en un despliegue limpio.

Uso:
    py -3.12 cargar_datos_base.py
"""
import os, sys, subprocess

BASE = os.path.dirname(os.path.abspath(__file__))
MANAGE = os.path.join(BASE, 'manage.py')
PYTHON = sys.executable

FIXTURES = [
    'fixtures/01_trazabilidad_catalogos.json',
    'fixtures/02_usuarios.json',
    'fixtures/03_celery_beat.json',
    'fixtures/04_empleados_trazabilidad.json.gz',
]

SEP = '=' * 60

print()
print(SEP)
print('  CARGA DE DATOS BASE')
print(SEP)

for fixture in FIXTURES:
    path = os.path.join(BASE, fixture)
    if not os.path.exists(path):
        print(f'  SKIP  {fixture}  (no encontrado)')
        continue
    print(f'\n  Cargando {fixture} ...')
    result = subprocess.run(
        [PYTHON, MANAGE, 'loaddata', fixture],
        capture_output=True, text=True, cwd=BASE,
    )
    if result.returncode == 0:
        out = result.stdout.strip()
        print(f'  OK    {out}')
    else:
        print(f'  ERROR {result.stderr.strip()}')
        sys.exit(1)

print()
print(SEP)
print('  Datos base cargados correctamente.')
print(SEP)
print()
