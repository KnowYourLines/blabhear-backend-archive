# Generated by Django 3.2.16 on 2022-10-29 01:20

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('blabhear', '0002_auto_20221016_2040'),
    ]

    operations = [
        migrations.AddField(
            model_name='message',
            name='filename',
            field=models.UUIDField(default=None, null=True),
        ),
    ]
