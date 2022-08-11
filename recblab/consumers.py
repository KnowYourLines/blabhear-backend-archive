from channels.generic.websocket import AsyncJsonWebsocketConsumer


class RoomConsumer(AsyncJsonWebsocketConsumer):
    pass


class UserConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        user_id = self.scope["url_route"]["kwargs"]["user_id"]
        user = self.scope["user"]
        if user_id == user.username:
            await self.channel_layer.group_add(str(user_id), self.channel_name)
            await self.accept()
