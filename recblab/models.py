import uuid

from django.contrib.auth.models import AbstractUser
from django.core.validators import RegexValidator
from django.db import models

phone_regex = RegexValidator(
    regex=r"^\+?1?\d{9,15}$",
    message="Phone number must be entered in the format: '+999999999'. Up to 15 digits allowed.",
)


class User(AbstractUser):
    id = models.AutoField(primary_key=True)
    phone_number = models.CharField(validators=[phone_regex], max_length=17, blank=True)
    display_name = models.CharField(max_length=150, blank=True)

    def save(self, *args, **kwargs):
        if not self.display_name and self.phone_number:
            self.display_name = self.phone_number
        elif not self.display_name and not self.phone_number:
            self.display_name = self.username
        super(User, self).save(*args, **kwargs)


class Room(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    members = models.ManyToManyField(User)
    private = models.BooleanField(blank=False, default=False)
    display_name = models.CharField(max_length=150, blank=True)
    audio_filename = models.UUIDField(default=uuid.uuid4)

    def save(self, *args, **kwargs):
        if not self.display_name:
            self.display_name = self.id
        super(Room, self).save(*args, **kwargs)


class JoinRequest(models.Model):
    id = models.AutoField(primary_key=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    room = models.ForeignKey(Room, on_delete=models.CASCADE)
    timestamp = models.DateTimeField(auto_now_add=True)


class Notification(models.Model):
    id = models.AutoField(primary_key=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    room = models.ForeignKey(Room, on_delete=models.CASCADE)
    timestamp = models.DateTimeField(auto_now_add=True)
