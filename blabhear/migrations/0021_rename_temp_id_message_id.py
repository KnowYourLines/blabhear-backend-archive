# Generated by Django 3.2.16 on 2022-11-16 23:24

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('blabhear', '0020_auto_20221116_2315'),
    ]

    operations = [
        migrations.RenameField(
            model_name='message',
            old_name='temp_id',
            new_name='id',
        ),
    ]
