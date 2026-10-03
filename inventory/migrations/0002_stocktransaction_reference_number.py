from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='stocktransaction',
            name='reference_number',
            field=models.CharField(
                blank=True,
                db_index=True,
                default='',
                help_text='Optional structured reference (e.g. dispensing transaction number DS-2026-000001).',
                max_length=50,
            ),
        ),
    ]
