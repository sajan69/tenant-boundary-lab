from django.db import migrations

class Migration(migrations.Migration):
    dependencies=[('tickets','0002_boundary_policies')]
    operations=[migrations.RunSQL('GRANT SELECT ON django_migrations TO boundary_app',
                                 reverse_sql='REVOKE SELECT ON django_migrations FROM boundary_app')]
