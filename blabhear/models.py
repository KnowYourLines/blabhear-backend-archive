import uuid

from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _


class User(AbstractUser):
    id = models.AutoField(primary_key=True)
    phone_number = models.CharField(max_length=150, blank=True)
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
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    creator = models.ForeignKey(User, on_delete=models.CASCADE)
    room = models.ForeignKey(Room, on_delete=models.CASCADE)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    edited_at = models.DateTimeField(null=True, blank=True, default=None)
    filename = models.UUIDField(null=True, blank=True)


class RecordingSettings(models.Model):
    class Language(models.TextChoices):
        CHINESE = "zh"
        CHINESE_CHINA = "zh-CN"
        CHINESE_TAIWAN = "zh-TW"
        DANISH = "da"
        DUTCH = "nl"
        ENGLISH = "en"
        ENGLISH_AUSTRALIA = "en-AU"
        ENGLISH_UNITED_KINGDOM = "en-GB"
        ENGLISH_INDIA = "en-IN"
        ENGLISH_NEW_ZEALAND = "en-NZ"
        ENGLISH_UNITED_STATES = "en-US"
        FRENCH = "fr"
        FRENCH_CANADA = "fr-CA"
        GERMAN = "de"
        HINDI = "hi"
        HINDI_ROMAN_SCRIPT = "hi-Latn"
        INDONESIAN = "id"
        ITALIAN = "it"
        JAPANESE = "ja"
        KOREAN = "ko"
        NORWEGIAN = "no"
        POLISH = "pl"
        PORTUGUESE = "pt"
        PORTUGUESE_BRAZIL = "pt-BR"
        PORTUGUESE_PORTUGAL = "pt-PT"
        RUSSIAN = "ru"
        SPANISH = "es"
        SPANISH_LATIN_AMERICA = "es-419"
        SWEDISH = "sv"
        TAMIL = "ta"
        TURKISH = "tr"
        UKRAINIAN = "uk"
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    room = models.ForeignKey(Room, on_delete=models.CASCADE)
    language = models.CharField(
        max_length=10,
        choices=Language.choices,
        default=Language.ENGLISH
    )

    def base_only_language(self):
        return self.language in {
            self.Language.CHINESE,
            self.Language.CHINESE_CHINA,
            self.Language.CHINESE_TAIWAN,
            self.Language.ENGLISH_AUSTRALIA,
            self.Language.ENGLISH_UNITED_KINGDOM,
            self.Language.ENGLISH_INDIA,
            self.Language.ENGLISH_NEW_ZEALAND,
            self.Language.FRENCH_CANADA,
            self.Language.HINDI_ROMAN_SCRIPT,
            self.Language.INDONESIAN,
            self.Language.RUSSIAN,
            self.Language.TURKISH,
            self.Language.UKRAINIAN,
        }

    def save(self, *args, **kwargs):
        other_recording_settings = RecordingSettings.objects.filter(
            user=self.user, room=self.room
        ).exclude(id=self.id)
        if other_recording_settings.exists():
            raise ValidationError(
                _("Recording settings must be unique per user in room.")
            )
        self.full_clean()
        super(RecordingSettings, self).save(*args, **kwargs)


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
