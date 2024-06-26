# Generated by Django 3.2.16 on 2022-11-16 23:15

from django.db import migrations


def relink_messages_to_notifications(apps, schema_editor):
    Notification = apps.get_model("blabhear", "Notification")
    for notification in Notification.objects.all():
        latest_message = notification.room.message_set.order_by("-created_at").first()
        notification.message = latest_message
        notification.save()


class Migration(migrations.Migration):

    dependencies = [
        ("blabhear", "0019_notification_message"),
    ]

    operations = [
        migrations.RunPython(
            relink_messages_to_notifications, reverse_code=migrations.RunPython.noop
        ),
    ]
