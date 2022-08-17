import asyncio
from operator import itemgetter

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from recblab.models import Room, JoinRequest, User, Notification


class RoomConsumer(AsyncJsonWebsocketConsumer):
    def get_room(self, room_id):
        room, created = Room.objects.get_or_create(id=room_id)
        return room

    def get_all_room_members(self):
        members = [user["display_name"] for user in self.room.members.all().values()]
        return members

    def add_user_to_room(self, user, room):
        was_added = False
        if user not in room.members.all():
            room.members.add(user)
            Notification.objects.create(user=user, room=room)
            was_added = True
        members = self.get_all_room_members()
        return members, was_added

    def set_room_privacy(self, private):
        self.room.private = private
        self.room.save()

    def user_not_allowed(self):
        return self.user not in self.room.members.all() and self.room.private

    def get_all_join_requests(self):
        all_join_requests = list(
            self.room.joinrequest_set.order_by("-timestamp").values(
                "user", "user__username", "user__display_name"
            )
        )
        return all_join_requests

    def get_or_create_new_join_request(self):
        JoinRequest.objects.get_or_create(user=self.user, room=self.room)

    def reject_room_member(self, username):
        user = User.objects.get(username=username)
        self.room.joinrequest_set.filter(user=user).delete()

    def approve_room_member(self, username):
        user = User.objects.get(username=username)
        self.room.members.add(user)
        Notification.objects.create(user=user, room=self.room)
        self.room.joinrequest_set.filter(user=user).delete()

    def approve_all_room_members(self):
        added_users = []
        for request in self.room.joinrequest_set.all():
            self.room.members.add(request.user)
            Notification.objects.create(user=request.user, room=self.room)
            added_users.append(request.user.username)
        self.room.joinrequest_set.all().delete()
        return added_users

    async def connect(self):
        await self.accept()

        self.room_id = self.scope["url_route"]["kwargs"]["room_id"]
        self.room = await database_sync_to_async(self.get_room)(self.room_id)
        self.user = self.scope["user"]

        await self.channel_layer.group_add(self.room_id, self.channel_name)
        user_not_allowed = await database_sync_to_async(self.user_not_allowed)()
        if user_not_allowed:
            await self.channel_layer.send(
                self.channel_name,
                {"type": "allowed", "allowed": False},
            )
            await database_sync_to_async(self.get_or_create_new_join_request)()
            await self.channel_layer.group_send(
                self.room_id,
                {"type": "refresh_join_requests"},
            )
        else:
            members, was_added = await database_sync_to_async(self.add_user_to_room)(
                self.user, self.room
            )
            if was_added:
                await self.channel_layer.group_send(
                    self.room_id,
                    {"type": "refresh_members"},
                )
                await self.channel_layer.group_send(
                    self.user.username,
                    {
                        "type": "refresh_notifications",
                    },
                )
            else:
                await self.channel_layer.send(
                    self.channel_name, {"type": "members", "members": members}
                )
            await self.fetch_privacy()
            await self.fetch_join_requests()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(str(self.room.id), self.channel_name)

    async def receive_json(self, content, **kwargs):
        user_not_allowed = await database_sync_to_async(self.user_not_allowed)()
        user_allowed = not user_not_allowed
        if content.get("command") == "fetch_allowed_status":
            asyncio.create_task(self.fetch_allowed_status(user_allowed))
        elif user_allowed:
            if content.get("command") == "update_privacy":
                asyncio.create_task(self.update_privacy(content))
            if content.get("command") == "fetch_privacy":
                asyncio.create_task(self.fetch_privacy())
            if content.get("command") == "fetch_join_requests":
                asyncio.create_task(self.fetch_join_requests())
            if content.get("command") == "fetch_members":
                asyncio.create_task(self.fetch_members())
            if content.get("command") == "reject_user":
                asyncio.create_task(self.reject_user(content))
            if content.get("command") == "approve_user":
                asyncio.create_task(self.approve_user(content))
            if content.get("command") == "approve_all_users":
                asyncio.create_task(self.approve_all_users())

    async def approve_all_users(self):
        added_usernames = await database_sync_to_async(self.approve_all_room_members)()
        for username in added_usernames:
            await self.channel_layer.group_send(
                username,
                {
                    "type": "refresh_notifications",
                },
            )
        await self.channel_layer.group_send(
            self.room_id,
            {"type": "refresh_join_requests"},
        )
        await self.channel_layer.group_send(
            self.room_id,
            {"type": "refresh_members"},
        )
        await self.channel_layer.group_send(
            self.room_id,
            {"type": "refresh_allowed_status"},
        )
        await self.channel_layer.group_send(
            self.room_id,
            {"type": "refresh_privacy"},
        )

    async def fetch_allowed_status(self, allowed_status):
        await self.channel_layer.send(
            self.channel_name,
            {"type": "allowed", "allowed": allowed_status},
        )
        if not allowed_status:
            await database_sync_to_async(self.get_or_create_new_join_request)()
            await self.channel_layer.group_send(
                self.room_id,
                {"type": "refresh_join_requests"},
            )

    async def approve_user(self, input_payload):
        await database_sync_to_async(self.approve_room_member)(
            input_payload["username"]
        )
        await self.channel_layer.group_send(
            input_payload["username"],
            {
                "type": "refresh_notifications",
            },
        )
        await self.channel_layer.group_send(
            self.room_id,
            {"type": "refresh_join_requests"},
        )
        await self.channel_layer.group_send(
            self.room_id,
            {"type": "refresh_members"},
        )
        await self.channel_layer.group_send(
            self.room_id,
            {"type": "refresh_allowed_status"},
        )
        await self.channel_layer.group_send(
            self.room_id,
            {"type": "refresh_privacy"},
        )

    async def reject_user(self, input_payload):
        await database_sync_to_async(self.reject_room_member)(input_payload["username"])
        await self.channel_layer.group_send(
            self.room_id,
            {"type": "refresh_join_requests"},
        )

    async def fetch_members(self):
        members = await database_sync_to_async(self.get_all_room_members)()
        await self.channel_layer.send(
            self.channel_name,
            {"type": "members", "members": members},
        )

    async def fetch_privacy(self):
        room = await database_sync_to_async(self.get_room)(self.room_id)
        await self.channel_layer.send(
            self.channel_name,
            {"type": "privacy", "privacy": room.private},
        )

    async def fetch_join_requests(self):
        all_join_requests = await database_sync_to_async(self.get_all_join_requests)()
        await self.channel_layer.send(
            self.channel_name,
            {"type": "join_requests", "join_requests": all_join_requests},
        )

    async def update_privacy(self, input_payload):
        await database_sync_to_async(self.set_room_privacy)(input_payload["privacy"])
        await self.channel_layer.group_send(
            self.room_id,
            {"type": "refresh_privacy"},
        )

    async def refresh_join_requests(self, event):
        # Send message to WebSocket
        await self.send_json(event)

    async def refresh_allowed_status(self, event):
        # Send message to WebSocket
        await self.send_json(event)

    async def members(self, event):
        # Send message to WebSocket
        await self.send_json(event)

    async def refresh_members(self, event):
        # Send message to WebSocket
        await self.send_json(event)

    async def allowed(self, event):
        # Send message to WebSocket
        await self.send_json(event)

    async def join_requests(self, event):
        # Send message to WebSocket
        await self.send_json(event)

    async def refresh_privacy(self, event):
        # Send message to WebSocket
        await self.send_json(event)

    async def privacy(self, event):
        # Send message to WebSocket
        await self.send_json(event)


class UserConsumer(AsyncJsonWebsocketConsumer):
    def get_user_notifications(self):
        notifications = list(
            self.user.notification_set.values("room", "timestamp")
            .order_by("room", "-timestamp")
            .distinct("room")
        )
        notifications.sort(key=itemgetter("timestamp"), reverse=True)
        for notification in notifications:
            notification["room"] = str(notification["room"])
            notification["timestamp"] = str(notification["timestamp"])
        return notifications

    def leave_room(self, room_id):
        room_to_leave = Room.objects.get(id=room_id)
        room_to_leave.members.remove(self.user)
        self.user.notification_set.filter(room=room_to_leave).delete()

    async def connect(self):
        self.username = str(self.scope["url_route"]["kwargs"]["user_id"])
        self.user = self.scope["user"]
        if self.username == self.user.username:
            await self.channel_layer.group_add(self.username, self.channel_name)
            await self.accept()

            notifications = await database_sync_to_async(self.get_user_notifications)()
            await self.channel_layer.group_send(
                self.username,
                {
                    "type": "notifications",
                    "notifications": notifications,
                },
            )
        else:
            await self.close()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.username, self.channel_name)

    async def receive_json(self, content, **kwargs):
        if content.get("command") == "exit_room":
            asyncio.create_task(self.exit_room(content))
        if content.get("command") == "fetch_notifications":
            asyncio.create_task(self.fetch_notifications())

    async def fetch_notifications(self):
        notifications = await database_sync_to_async(self.get_user_notifications)()
        await self.channel_layer.group_send(
            self.username,
            {
                "type": "notifications",
                "notifications": notifications,
            },
        )

    async def exit_room(self, input_payload):
        await database_sync_to_async(self.leave_room)(input_payload["room_id"])
        await self.channel_layer.group_send(
            input_payload["room_id"],
            {"type": "refresh_members"},
        )
        await self.channel_layer.group_send(
            input_payload["room_id"],
            {"type": "refresh_allowed_status"},
        )
        notifications = await database_sync_to_async(self.get_user_notifications)()
        await self.channel_layer.group_send(
            self.username,
            {
                "type": "notifications",
                "notifications": notifications,
            },
        )

    async def notifications(self, event):
        # Send message to WebSocket
        await self.send_json(event)

    async def refresh_notifications(self, event):
        # Send message to WebSocket
        await self.send_json(event)
