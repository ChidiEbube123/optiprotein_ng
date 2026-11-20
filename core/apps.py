import sys
from django.apps import AppConfig

class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'

    def ready(self):
        if 'runserver' in sys.argv:
            try:
                from django.db import connection
                if 'core_corridor' in connection.introspection.table_names():
                    from core.models import Corridor
                    if not Corridor.objects.exists():
                        from django.core.management import call_command
                        call_command('seed_data')
            except Exception:
                pass
