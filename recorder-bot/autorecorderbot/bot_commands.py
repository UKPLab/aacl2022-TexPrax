import logging
from nio import AsyncClient, MatrixRoom, RoomMessageText

from autorecorderbot.chat_functions import react_to_event, send_text_to_room
from autorecorderbot.config import Config
from autorecorderbot.storage import Storage


class Command:
    def __init__(
        self,
        client: AsyncClient,
        store: Storage,
        config: Config,
        command: str,
        room: MatrixRoom,
        event: RoomMessageText,
    ):
        """A command made by a user.

        Args:
            client: The client to communicate to matrix with.

            store: Bot storage.

            config: Bot configuration parameters.

            command: The command and arguments.

            room: The room the command was sent in.

            event: The event describing the command.
        """
        self.client = client
        self.store = store
        self.config = config
        self.command = command
        self.room = room
        self.event = event
        self.args = self.command.split()[1:]

    async def process(self):
        """Process the command"""
        # If the event was sent before the bot joined the room, ignore it
        avail_types = ["lösung", "problem", "ursache", "o"]
        logging.debug(f"Message TS: {self.event.server_timestamp} Join TS: {self.store.get_room_timestamp(self.room.room_id)*1000}")
        if self.event.server_timestamp < self.store.get_room_timestamp(self.room.room_id) * 1000:
            return
        elif self.command.lower() == "yes" or self.command.lower() == "y" or self.command.lower() == "j" or self.command.lower() == "ja":
            await self._yes()
        elif self.command.lower() == "no" or self.command.lower() == "n" or self.command.lower() == "nein":
            await self._no()
        elif self.command.startswith(":"):
            if self.command[1:].lower() in avail_types:
                self.store.change_last_message_type(self.command[1:], self.room.room_id)
                if self.command[1:].lower() == "problem":
                    self.store.last_msg_as_problem_to_teamboard(self.room.room_id)
                    await send_text_to_room(self.client, self.room.room_id, 'Message was stored as a problem to the teamboard!')
                elif self.command[1:].lower() == "lösung":
                    if self.store.last_msg_as_solution_to_teamboard(self.room.room_id):
                        await send_text_to_room(self.client, self.room.room_id, 'Message was stored as a solution to the teamboard!')
                    else:
                        await send_text_to_room(self.client, self.room.room_id, 'Message could not be stored as a solution to the teamboard!')
                elif self.command[1:].lower() == "ursache":
                    if self.store.last_msg_as_cause_to_teamboard(self.room.room_id):
                        await send_text_to_room(self.client, self.room.room_id, 'Message was stored as a cause to the teamboard!')
                    else:
                        await send_text_to_room(self.client, self.room.room_id, 'Message could not be stored as a cause to the teamboard!')
            elif self.command[1:].lower() == "yes" and self.store.get_last_message_type() == "Problem":
                self.store.last_msg_as_problem_to_teamboard(self.room.room_id)
                await send_text_to_room(self.client, self.room.room_id, 'Message was stored as a problem to the teamboard!')
            elif self.command[1:].lower() == "yes" and self.store.get_last_message_type() == "Lösung":
                if self.store.last_msg_as_solution_to_teamboard(self.room.room_id):
                    await send_text_to_room(self.client, self.room.room_id, 'Message was stored as a solution to the teamboard!')
                else:
                    await send_text_to_room(self.client, self.room.room_id, 'Message could not be stored as a solution to the teamboard!')
            elif self.command[1:].lower() == "yes" and self.store.get_last_message_type() == "Ursache":
                if self.store.last_msg_as_cause_to_teamboard(self.room.room_id):
                    await send_text_to_room(self.client, self.room.room_id, 'Message was stored as a cause to the teamboard!')
                else:
                    await send_text_to_room(self.client, self.room.room_id, 'Message could not be stored as a cause to the teamboard!')
        else:
            await self._unknown_command()

    async def _no(self):
        response = "Okay, I will leave now!"
        await send_text_to_room(self.client, self.room.room_id, response)
        await self.client.room_leave(self.room.room_id)
        self.store.delete_room(self.room.room_id)
    
    async def _yes(self):
        response = "Okay, I will stay!"
        await send_text_to_room(self.client, self.room.room_id, response)
        self.store.set_room_recording(self.room.room_id)

    async def _unknown_command(self):
        if not self.store.get_room_recording(self.room.room_id):
            response = "I did not quite understand what you said, so I assume I should not record."
            await send_text_to_room(self.client, self.room.room_id, response)
            await self.client.room_leave(self.room.room_id)
            self.store.delete_room(self.room.room_id)
