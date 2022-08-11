from channels.generic.websocket import AsyncJsonWebsocketConsumer


class RoomConsumer(AsyncJsonWebsocketConsumer):
    pass


class UserConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        self.username = str(self.scope["url_route"]["kwargs"]["user_id"])
        user = self.scope["user"]
        if self.username == user.username:
            await self.channel_layer.group_add(self.username, self.channel_name)
            await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.username, self.channel_name)
