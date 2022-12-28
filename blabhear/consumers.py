import asyncio
import datetime
import logging
import os
import uuid
from operator import itemgetter

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from deepgram import Deepgram
from django.core.exceptions import ObjectDoesNotExist
from django.core.paginator import Paginator, EmptyPage

from blabhear.models import Room, JoinRequest, User, Notification, Message
from blabhear.storage import (
    generate_upload_signed_url_v4,
    generate_download_signed_url_v4,
)

logger = logging.getLogger(__name__)
DEEPGRAM_CLIENT = Deepgram(os.environ.get("DEEPGRAM_API_KEY"))


class RoomConsumer(AsyncJsonWebsocketConsumer):
    def get_room(self, room_id):
        room, created = Room.objects.get_or_create(id=room_id)
        return room

    def get_all_room_members(self):
        room = Room.objects.filter(id=self.room_id)
        if room.exists():
            room = room.first()
            members = room.members.all().values()
        else:
            members = []
        member_display_names = [user["display_name"] for user in members]
        member_usernames = [user["username"] for user in members]
        return member_display_names, member_usernames

    def add_user_to_room(self, user, room):
        was_added = False
        latest_message = room.message_set.order_by("-created_at").first()
        if user not in room.members.all():
            room.members.add(user)
            Notification.objects.get_or_create(
                user=user, room=room, defaults={"message": latest_message}
            )
            was_added = True
        member_display_names, member_usernames = self.get_all_room_members()
        return member_display_names, was_added

    def set_room_privacy(self, private):
        room = self.get_room(self.room_id)
        room.private = private
        room.save()

    def user_not_allowed(self):
        room = Room.objects.filter(id=self.room_id)
        if room.exists():
            room = room.first()
            return self.user not in room.members.all() and room.private
        else:
            return False

    def get_all_join_requests(self):
        room = self.get_room(self.room_id)
        all_join_requests = list(
            room.joinrequest_set.order_by("-timestamp").values(
                "user", "user__username", "user__display_name"
            )
        )
        return all_join_requests

    def get_or_create_new_join_request(self):
        room = self.get_room(self.room_id)
        JoinRequest.objects.get_or_create(user=self.user, room=room)

    def reject_room_member(self, username):
        user = User.objects.get(username=username)
        room = self.get_room(self.room_id)
        room.joinrequest_set.filter(user=user).delete()

    def approve_room_member(self, username):
        user = User.objects.get(username=username)
        room = self.get_room(self.room_id)
        room.members.add(user)
        latest_message = room.message_set.order_by("-created_at").first()
        Notification.objects.get_or_create(
            user=user, room=room, defaults={"message": latest_message}
        )
        room.joinrequest_set.filter(user=user).delete()

    def approve_all_room_members(self):
        added_users = []
        room = self.get_room(self.room_id)
        latest_message = room.message_set.order_by("-created_at").first()
        for request in room.joinrequest_set.all():
            room.members.add(request.user)
            Notification.objects.get_or_create(
                user=request.user, room=room, defaults={"message": latest_message}
            )
            added_users.append(request.user.username)
        room.joinrequest_set.all().delete()
        return added_users

    def change_display_name(self, new_name):
        room = self.get_room(self.room_id)
        room.display_name = new_name
        room.save()
        users_to_refresh = [
            str(user["username"]) for user in room.members.all().values()
        ]
        return new_name, users_to_refresh

    def read_unread_room_notification(self):
        room = self.get_room(self.room_id)
        room_notification = Notification.objects.get(user=self.user, room=room)
        if not room_notification.read:
            room_notification.read = True
            room_notification.save()

    def create_new_message_notification_for_all_room_members(self, new_message):
        room = self.get_room(self.room_id)
        for user in room.members.all():
            notification = Notification.objects.get(user=user, room=room)
            notification.message = new_message
            notification.read = user == self.user
            notification.save()

    def create_new_message(self, content, filename):
        room = self.get_room(self.room_id)
        new_message = Message.objects.create(
            creator=self.user, room=room, content=content, filename=filename
        )
        self.create_new_message_notification_for_all_room_members(new_message)
        return {
            "creator__display_name": new_message.creator.display_name,
            "content": new_message.content,
            "creator__username": new_message.creator.username,
            "created_at": new_message.created_at.strftime("%d-%m-%Y %H:%M"),
            "filename": str(new_message.filename),
            "download": generate_download_signed_url_v4(str(new_message.filename)),
            "id": str(new_message.id),
        }

    def edit_message_content(self, message_id, new_content):
        message = Message.objects.get(id=message_id)
        if message.creator == self.user:
            message.edited_at = datetime.datetime.now(tz=datetime.timezone.utc)
            message.content = new_content
            message.save()
        notifications_with_message = Notification.objects.filter(message=message)
        return [
            notification["user__username"]
            for notification in notifications_with_message.values("user__username")
        ]

    def fetch_messages(self, *, page):
        room = self.get_room(self.room_id)
        try:
            messages = Paginator(
                room.message_set.order_by("-created_at").values(
                    "creator__display_name",
                    "content",
                    "creator__username",
                    "created_at",
                    "edited_at",
                    "filename",
                    "id",
                ),
                10,
            )
            message_page = messages.page(page)
            message_page_display_order = message_page.object_list[::-1]
            for message in message_page_display_order:
                if message["edited_at"]:
                    message["edited_at"] = message["edited_at"].strftime(
                        "%d-%m-%Y %H:%M"
                    )
                message["created_at"] = message["created_at"].strftime("%d-%m-%Y %H:%M")
                message["filename"] = str(message["filename"])
                message["id"] = str(message["id"])
                message["download"] = generate_download_signed_url_v4(
                    str(message["filename"])
                )
            return message_page_display_order, page
        except ObjectDoesNotExist:
            pass
        except EmptyPage:
            return [], page

    def fetch_messages_up_to_page(self, *, page):
        accumulated_messages = []
        room = self.get_room(self.room_id)
        for page_number in range(1, page + 1):
            try:
                messages = Paginator(
                    room.message_set.order_by("-created_at").values(
                        "creator__display_name",
                        "content",
                        "creator__username",
                        "created_at",
                        "edited_at",
                        "filename",
                        "id",
                    ),
                    10,
                )
                message_page = messages.page(page_number)
                message_page_display_order = message_page.object_list[::-1]
                accumulated_messages = message_page_display_order + accumulated_messages
            except ObjectDoesNotExist:
                break
            except EmptyPage:
                break
        for message in accumulated_messages:
            if message["edited_at"]:
                message["edited_at"] = message["edited_at"].strftime("%d-%m-%Y %H:%M")
            message["created_at"] = message["created_at"].strftime("%d-%m-%Y %H:%M")
            message["filename"] = str(message["filename"])
            message["id"] = str(message["id"])
            message["download"] = generate_download_signed_url_v4(
                str(message["filename"])
            )
        return accumulated_messages, page

    async def connect(self):
        await self.accept()

        self.room_id = self.scope["url_route"]["kwargs"]["room_id"]
        self.user = self.scope["user"]
        await self.initialize_room()

    async def initialize_room(self):
        await self.channel_layer.group_add(self.room_id, self.channel_name)
        room = await database_sync_to_async(self.get_room)(self.room_id)
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
                self.user, room
            )
            if was_added:
                await self.channel_layer.group_send(
                    self.room_id,
                    {"type": "refresh_members"},
                )
            else:
                await self.channel_layer.send(
                    self.channel_name, {"type": "members", "members": members}
                )
            await database_sync_to_async(self.read_unread_room_notification)()
            await self.channel_layer.group_send(
                self.user.username,
                {
                    "type": "refresh_notifications",
                },
            )
            await self.get_room_messages_up_to_page(page=1)
            await self.fetch_display_name()
            await self.fetch_privacy()
            await self.fetch_join_requests()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(str(self.room_id), self.channel_name)

    async def receive_json(self, content, **kwargs):
        if content.get("command") == "connect":
            await self.channel_layer.group_discard(str(self.room_id), self.channel_name)
            self.room_id = content.get("room")
            await self.initialize_room()
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
            if content.get("command") == "update_display_name":
                asyncio.create_task(self.update_display_name(content))
            if content.get("command") == "send_message":
                asyncio.create_task(self.send_message(content))
            if content.get("command") == "fetch_messages":
                asyncio.create_task(self.get_room_messages(page=content["page"]))
            if content.get("command") == "fetch_messages_up_to_page":
                asyncio.create_task(
                    self.get_room_messages_up_to_page(page=content["page"])
                )
            if content.get("command") == "fetch_display_name":
                asyncio.create_task(self.fetch_display_name())
            if content.get("command") == "fetch_upload_url":
                asyncio.create_task(self.fetch_upload_url())
            if content.get("command") == "read_room_notification":
                asyncio.create_task(self.read_room_notification())
            if content.get("command") == "edit_message":
                asyncio.create_task(self.edit_message(content))

    async def edit_message(self, payload):
        users_to_refresh = await database_sync_to_async(self.edit_message_content)(
            payload["message_id"], payload["edited_message"]
        )
        await self.channel_layer.group_send(
            self.room_id,
            {
                "type": "refresh_messages",
            },
        )
        for username in users_to_refresh:
            await self.channel_layer.group_send(
                username,
                {
                    "type": "refresh_notifications",
                },
            )

    async def read_room_notification(self):
        await database_sync_to_async(self.read_unread_room_notification)()
        await self.channel_layer.group_send(
            self.user.username,
            {
                "type": "refresh_notifications",
            },
        )

    async def fetch_upload_url(self):
        filename = str(uuid.uuid4())
        url = generate_upload_signed_url_v4(filename)
        dry_filename = "dry-" + filename
        dry_url = generate_upload_signed_url_v4(dry_filename)
        await self.channel_layer.send(
            self.channel_name,
            {
                "type": "upload_url",
                "dry_upload_url": dry_url,
                "dry_filename": dry_filename,
                "wet_upload_url": url,
                "wet_filename": filename,
            },
        )

    async def get_room_messages_up_to_page(self, *, page):
        messages, page_number = await database_sync_to_async(
            self.fetch_messages_up_to_page
        )(page=page)
        await self.channel_layer.send(
            self.channel_name,
            {
                "type": "messages",
                "messages": messages,
                "page": page_number,
                "refresh_messages_in": 604790000,
            },
        )

    async def get_room_messages(self, *, page):
        messages, page_number = await database_sync_to_async(self.fetch_messages)(
            page=page
        )
        await self.channel_layer.send(
            self.channel_name,
            {"type": "messages", "messages": messages, "page": page_number},
        )

    async def send_message(self, input_payload):
        new_message = None
        message = input_payload.get("message", "")
        dry_filename = input_payload.get("dry_filename")
        wet_filename = input_payload.get("wet_filename")
        if isinstance(dry_filename, str) and isinstance(wet_filename, str):
            source = {"url": generate_download_signed_url_v4(dry_filename)}
            options = {
                "punctuate": True,
                "model": "general",
                "language": "en",
                "tier": "enhanced",
            }
            try:
                response = await DEEPGRAM_CLIENT.transcription.prerecorded(
                    source, options
                )
            except Exception as error:
                logger.error(
                    f"When attempting transcription, message with filename {dry_filename} generated {error}"
                )
                return
            transcript = response["results"]["channels"][0]["alternatives"][0][
                "transcript"
            ]
            new_message = await database_sync_to_async(self.create_new_message)(
                transcript, wet_filename
            )
        elif len(message.strip()) > 0:
            new_message = await database_sync_to_async(self.create_new_message)(
                message, None
            )
        if new_message:
            await self.channel_layer.group_send(
                self.room_id,
                {"type": "new_message", "new_message": new_message},
            )
            (
                room_member_display_names,
                room_member_usernames,
            ) = await database_sync_to_async(self.get_all_room_members)()
            for username in room_member_usernames:
                await self.channel_layer.group_send(
                    username,
                    {
                        "type": "refresh_notifications",
                    },
                )
            await self.channel_layer.group_send(
                self.room_id,
                {"type": "room_notified"},
            )

    async def update_display_name(self, input_payload):
        if len(input_payload["name"].strip()) > 0:
            display_name, users_to_refresh = await database_sync_to_async(
                self.change_display_name
            )(input_payload["name"])
            for username in users_to_refresh:
                await self.channel_layer.group_send(
                    username, {"type": "refresh_notifications"}
                )
            await self.channel_layer.group_send(
                self.room_id,
                {
                    "type": "display_name",
                    "display_name": display_name,
                },
            )
        else:
            await self.fetch_display_name()

    async def fetch_display_name(self):
        room = await database_sync_to_async(self.get_room)(self.room_id)
        display_name = room.display_name
        await self.channel_layer.send(
            self.channel_name,
            {"type": "display_name", "display_name": display_name},
        )

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
                {"type": "refresh_messages", "username": username},
            )
            await self.channel_layer.group_send(
                self.room_id,
                {"type": "refresh_display_name", "username": username},
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
            {"type": "refresh_messages", "username": input_payload["username"]},
        )
        await self.channel_layer.group_send(
            self.room_id,
            {"type": "refresh_display_name", "username": input_payload["username"]},
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
        member_display_names, member_usernames = await database_sync_to_async(
            self.get_all_room_members
        )()
        await self.channel_layer.send(
            self.channel_name,
            {"type": "members", "members": member_display_names},
        )
        room = await database_sync_to_async(self.get_room)(self.room_id)
        if self.user.username not in member_usernames and not room.private:
            await self.channel_layer.send(
                self.channel_name,
                {"type": "left_room"},
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

    async def upload_url(self, event):
        # Send message to WebSocket
        await self.send_json(event)

    async def messages(self, event):
        # Send message to WebSocket
        await self.send_json(event)

    async def new_message(self, event):
        # Send message to WebSocket
        await self.send_json(event)

    async def refresh_messages(self, event):
        if event.get("username"):
            if self.user.username == event.get("username"):
                await self.send_json(event)
            else:
                pass
        else:
            await self.send_json(event)

    async def refresh_display_name(self, event):
        if event.get("username"):
            if self.user.username == event.get("username"):
                await self.send_json(event)
            else:
                pass
        else:
            await self.send_json(event)

    async def refresh_join_requests(self, event):
        # Send message to WebSocket
        await self.send_json(event)

    async def room_notified(self, event):
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

    async def left_room(self, event):
        # Send message to WebSocket
        await self.send_json(event)

    async def display_name(self, event):
        # Send message to WebSocket
        await self.send_json(event)


class UserConsumer(AsyncJsonWebsocketConsumer):
    def get_user_notifications(self):
        notifications = list(
            self.user.notification_set.values(
                "room",
                "room__display_name",
                "read",
                "timestamp",
                "message__creator__display_name",
                "message__content",
            )
            .order_by("room", "-timestamp")
            .distinct("room")
        )
        notifications.sort(key=itemgetter("timestamp"), reverse=True)
        notifications.sort(key=itemgetter("read"))
        for notification in notifications:
            notification["room"] = str(notification["room"])
            notification["timestamp"] = notification["timestamp"].strftime(
                "%d-%m-%Y %H:%M"
            )
        return notifications

    def leave_room(self, room_id):
        room_to_leave = Room.objects.get(id=room_id)
        room_to_leave.members.remove(self.user)
        self.user.room_set.remove(room_to_leave)
        self.user.notification_set.filter(room=room_to_leave).delete()
        if not room_to_leave.members.all() and not room_to_leave.joinrequest_set.all():
            room_to_leave.delete()

    def change_display_name(self, new_name):
        self.user.display_name = new_name
        self.user.save()
        rooms_to_refresh = [
            str(room["id"]) for room in self.user.room_set.all().values()
        ] + [
            str(request["room_id"])
            for request in self.user.joinrequest_set.all().values()
        ]
        rooms_to_refresh = set(rooms_to_refresh)
        users_to_refresh = [
            str(notification["user__username"])
            for notification in Notification.objects.filter(
                message__creator=self.user
            ).values("user__username")
        ]
        return new_name, rooms_to_refresh, users_to_refresh

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
            await self.fetch_display_name()
        else:
            await self.close()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.username, self.channel_name)

    async def receive_json(self, content, **kwargs):
        if self.username == self.user.username:
            if content.get("command") == "exit_room":
                asyncio.create_task(self.exit_room(content))
            if content.get("command") == "fetch_notifications":
                asyncio.create_task(self.fetch_notifications())
            if content.get("command") == "update_display_name":
                asyncio.create_task(self.update_display_name(content))

    async def update_display_name(self, input_payload):
        if len(input_payload["name"].strip()) > 0:
            (
                display_name,
                rooms_to_refresh,
                users_to_refresh,
            ) = await database_sync_to_async(self.change_display_name)(
                input_payload["name"]
            )
            for room in rooms_to_refresh:
                await self.channel_layer.group_send(room, {"type": "refresh_members"})
                await self.channel_layer.group_send(
                    room, {"type": "refresh_join_requests"}
                )
                await self.channel_layer.group_send(room, {"type": "refresh_messages"})
            for username in users_to_refresh:
                await self.channel_layer.group_send(
                    username,
                    {
                        "type": "refresh_notifications",
                    },
                )
            await self.channel_layer.group_send(
                self.username,
                {
                    "type": "display_name",
                    "display_name": display_name,
                },
            )
        else:
            await self.fetch_display_name()

    async def fetch_display_name(self):
        display_name = self.user.display_name
        await self.channel_layer.send(
            self.channel_name,
            {"type": "display_name", "display_name": display_name},
        )

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

    async def display_name(self, event):
        # Send message to WebSocket
        await self.send_json(event)
