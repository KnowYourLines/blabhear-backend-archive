# Generated by Django 3.2.16 on 2022-11-16 21:46

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('blabhear', '0009_user_phone_number'),
    ]

    operations = [
        migrations.AlterField(
            model_name='message',
            name='filename',
            field=models.UUIDField(blank=True, null=True),
        ),
    ]
