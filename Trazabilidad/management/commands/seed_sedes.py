from django.core.management.base import BaseCommand
from Trazabilidad.models import Sede
from Trazabilidad.variantes_sede import SEDES_CANONICAS


class Command(BaseCommand):
    help = 'Carga las sedes reales de Euro Supermercados (basadas en los Excel reales)'

    def handle(self, *args, **options):
        # Eliminar sedes ficticias que no corresponden a tiendas reales
        ficticias = [
            # Códigos de versiones anteriores del sistema
            'BAQ-CEN', 'BAQ-NOR', 'BAQ-SUR', 'BOG-CHA', 'BOG-SUB',
            'BUC-CAB', 'CAL-NOR', 'CAL-SUR', 'CTG-BOC',
            'MED-BEL', 'MED-POB', 'MED-LAU', 'MED-ROB',
            'PEI-CEN', 'STM-001',
            # Códigos EUR-*/BIG-*/OPS-* reemplazados por códigos cortos SIESA
            'EUR-FRONTERA', 'EUR-MAYORISTA', 'EUR-FLORIDA', 'EUR-LAURELES',
            'EUR-BERNAL', 'EUR-SABANETA', 'EUR-GUADALCANAL', 'EUR-PALMAS',
            'EUR-NIQUIA', 'EUR-ITAGUI', 'EUR-BARBOSA', 'EUR-MARINILLA',
            'EUR-BELLO', 'EUR-CASTILLA', 'EUR-LLANOGRANDE', 'EUR-ARKADIA',
            'EUR-TERRACINA', 'EUR-MURANO', 'EUR-MIXY', 'EUR-CARNAVAL',
            'EUR-INFERIOR', 'EUR-GRANMANZANA', 'EUR-MONTERIA', 'EUR-NTR-MONTERIA',
            'BIG-MAYORISTA', 'BIG-LAURELES', 'BIG-CALDAS', 'BIG-CRISTOBAL', 'BIG-PALACE',
            'OPS-CEDI', 'OPS-DESPOSTE', 'OPS-ADMIN',
        ]
        eliminadas = Sede.objects.filter(codigo__in=ficticias).delete()
        self.stdout.write(f'Sedes ficticias eliminadas: {eliminadas[0]}')

        creadas = 0
        actualizadas = 0
        for data in SEDES_CANONICAS:
            obj, created = Sede.objects.update_or_create(
                codigo=data['codigo'],
                defaults={
                    'nombre': data['nombre'],
                    'ciudad': data['ciudad'],
                    'estado': True,
                },
            )
            if created:
                creadas += 1
                self.stdout.write(f'  NUEVA: {obj}')
            else:
                actualizadas += 1

        self.stdout.write(self.style.SUCCESS(
            f'\nResultado: {creadas} creadas, {actualizadas} actualizadas. '
            f'Total: {Sede.objects.count()} sedes'
        ))
