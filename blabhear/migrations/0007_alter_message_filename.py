# Generated by Django 3.2.16 on 2022-11-10 22:04

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('blabhear', '0006_alter_message_filename'),
    ]

    operations = [
        migrations.AlterField(
            model_name='message',
            name='filename',
            field=models.UUIDField(),
        ),
    ]