import uuid

from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _


class User(AbstractUser):
    id = models.AutoField(primary_key=True)
    display_name = models.CharField(max_length=150, blank=True)

    def save(self, *args, **kwargs):
        if not self.display_name:
            self.display_name = self.username
        super(User, self).save(*args, **kwargs)


class Room(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    members = models.ManyToManyField(User)
    private = models.BooleanField(blank=False, default=False)
    display_name = models.CharField(max_length=150, blank=True)

    def save(self, *args, **kwargs):
        if not self.display_name:
            self.display_name = self.id
        super(Room, self).save(*args, **kwargs)


class Message(models.Model):
    id = models.AutoField(primary_key=True)
    creator = models.ForeignKey(User, on_delete=models.CASCADE)
    room = models.ForeignKey(Room, on_delete=models.CASCADE)
    content = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    filename = models.UUIDField(null=False)


class JoinRequest(models.Model):
    id = models.AutoField(primary_key=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    room = models.ForeignKey(Room, on_delete=models.CASCADE)
    timestamp = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        other_requests = JoinRequest.objects.filter(
            user=self.user, room=self.room
        ).exclude(id=self.id)
        if other_requests.exists():
            raise ValidationError(_("Join request must be unique per user in room."))
        super(JoinRequest, self).save(*args, **kwargs)


class Notification(models.Model):
    id = models.AutoField(primary_key=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    room = models.ForeignKey(Room, on_delete=models.CASCADE)
    timestamp = models.DateTimeField(auto_now=True)
    message = models.ForeignKey(
        Message, blank=True, null=True, on_delete=models.SET_NULL
    )
    read = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        other_notifications = Notification.objects.filter(
            user=self.user, room=self.room
        ).exclude(id=self.id)
        if other_notifications.exists():
            raise ValidationError(_("Notification must be unique per user in room."))
        super(Notification, self).save(*args, **kwargs)
