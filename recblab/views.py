import json
import os
from http import HTTPStatus

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.http import HttpResponseBadRequest, HttpResponse, HttpResponseForbidden
from google.auth.transport import requests
from google.oauth2 import id_token


def audio_upload_webhook(request):
    if request.GET.get("token", "") != os.environ.get("PUBSUB_VERIFICATION_TOKEN"):
        return HttpResponseBadRequest()
    try:
        bearer_token = request.META.get("HTTP_AUTHORIZATION")
        token = bearer_token.split(" ")[1]
        claim = id_token.verify_oauth2_token(
            token, requests.Request(), audience=os.environ.get("GCP_STORAGE_CLIENT_ID")
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
    file_room = filename[0]
    event_timestamp = attributes["eventTime"]

    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        file_room,
        {
            "type": "upload_successful",
            "uploader": file_creator,
            "uploaded_at": event_timestamp,
        },
    )
    return HttpResponse(status=HTTPStatus.OK)
