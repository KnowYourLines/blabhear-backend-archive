from django.urls import re_path

from . import consumers

websocket_urlpatterns = [
    re_path(r"ws/user/(?P<user_uuid>.+)$", consumers.UserConsumer.as_asgi()),
    re_path(r"ws/room/(?P<room_name>.+)/$", consumers.RoomConsumer.as_asgi()),
]
