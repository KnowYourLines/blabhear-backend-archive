from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from recblab.models import Room


class RoomConsumer(AsyncJsonWebsocketConsumer):
    def get_room(self, room_id):
        room, created = Room.objects.get_or_create(id=room_id)
        return room

    async def connect(self):
        self.room_id = self.scope["url_route"]["kwargs"]["room_id"]
        self.room = await database_sync_to_async(self.get_room)(self.room_id)
        await self.channel_layer.group_add(str(self.room.id), self.channel_name)
        await self.accept()

        user = self.scope["user"]
        await self.channel_layer.group_send(
            user.username,
            {
                "type": "hello",
                "hello": "world",
            },
        )

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(str(self.room.id), self.channel_name)


class UserConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        self.username = str(self.scope["url_route"]["kwargs"]["user_id"])
        user = self.scope["user"]
        if self.username == user.username:
            await self.channel_layer.group_add(self.username, self.channel_name)
            await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.username, self.channel_name)

    async def hello(self, event):
        # Send message to WebSocket
        await self.send_json(event)
