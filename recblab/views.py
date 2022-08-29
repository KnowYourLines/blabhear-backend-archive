import json
import os
from datetime import datetime
from http import HTTPStatus

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.http import (
    HttpResponseBadRequest,
    HttpResponse,
    HttpResponseForbidden,
    HttpResponseNotAllowed,
)
from django.views.decorators.csrf import csrf_exempt
from google.auth.transport import requests
from google.oauth2 import id_token

from recblab.models import Room, Notification, User


@csrf_exempt
def audio_upload_webhook(request):
    if request.method == "POST":
        if request.GET.get("token", "") != os.environ.get("PUBSUB_VERIFICATION_TOKEN"):
            return HttpResponseBadRequest()
        try:
            bearer_token = request.META.get("HTTP_AUTHORIZATION")
            token = bearer_token.split(" ")[1]
            claim = id_token.verify_oauth2_token(
                token,
                requests.Request(),
                audience=os.environ.get("GCP_STORAGE_CLIENT_ID"),
            )
            if not (
                claim["email_verified"]
                and claim["email"] == os.environ.get("GCP_STORAGE_CLIENT_EMAIL")
            ):
                return HttpResponseForbidden()
        except Exception as exc:
            return HttpResponseForbidden(str(exc))

        notification = json.loads(request.body.decode("utf-8"))
        attributes = notification["message"]["attributes"]
        filename = attributes["objectId"].split("/")
        file_creator = filename[1]
        file_room_id = filename[0]
        event_timestamp = datetime.strptime(
            attributes["eventTime"], "%Y-%m-%dT%H:%M:%S.%f%z"
        )
        room = Room.objects.get(id=file_room_id)
        previous_event_timestamp = room.audio_file_created_at

        if previous_event_timestamp < event_timestamp:
            room.audio_file_creator = file_creator
            room.audio_file_created_at = event_timestamp
            room.save()
            channel_layer = get_channel_layer()
            for user in room.members.all():
                notification = Notification.objects.get(user=user, room=room)
                notification.timestamp = event_timestamp
                notification.audio_uploaded_by = User.objects.get(username=file_creator)
                notification.read = notification.user.username == file_creator
                notification.save()
                async_to_sync(channel_layer.group_send)(
                    user.username, {"type": "refresh_notifications"}
                )
            async_to_sync(channel_layer.group_send)(
                file_room_id,
                {
                    "type": "upload_successful",
                    "uploader": file_creator,
                },
            )

        return HttpResponse(status=HTTPStatus.OK)
    return HttpResponseNotAllowed(permitted_methods=["POST"])
