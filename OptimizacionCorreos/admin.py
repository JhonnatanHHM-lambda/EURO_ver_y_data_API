from django.contrib import admin
from .models import EjecucionConsolidacion, FacturaRadian, FacturaCorreo, ResultadoConciliacion

admin.site.register(EjecucionConsolidacion)
admin.site.register(FacturaRadian)
admin.site.register(FacturaCorreo)
admin.site.register(ResultadoConciliacion)
