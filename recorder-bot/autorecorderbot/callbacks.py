import logging
from time import sleep, time

from nio import (
    AsyncClient,
    InviteMemberEvent,
    JoinError,
    MatrixRoom,
    MegolmEvent,
    RoomGetEventError,
    RoomSendResponse,
    RoomMessageText,
    UnknownEvent,
    ErrorResponse,
)
from numpy import isin

from autorecorderbot.bot_commands import Command
from autorecorderbot.chat_functions import make_pill, react_to_event, send_text_to_room
from autorecorderbot.config import Config
from autorecorderbot.message_responses import Message
from autorecorderbot.storage import Storage
from autorecorderbot.intelligence import SentenceClassPredictor, TokenClassPredictor

logger = logging.getLogger(__name__)


class Callbacks:
    def __init__(self, client: AsyncClient, store: Storage, config: Config):
        """
        Args:
            client: nio client used to interact with matrix.

            store: Bot storage.

            config: Bot configuration parameters.
        """
        self.client = client
        self.store = store
        self.config = config
        self.command_prefix = config.command_prefix
        self.sequence_predictor = SentenceClassPredictor(config.sequence_model_path)
        self.token_predictor = TokenClassPredictor(config.token_model_path)

    async def message(self, room: MatrixRoom, event: RoomMessageText) -> None:
        """Callback for when a message event is received

        Args:
            room: The room the event came from.

            event: The event defining the message.
        """
        # Extract the message text
        msg = event.body

        # Ignore messages from ourselves and commands
        if event.sender == self.client.user:
            return

        logger.debug(
            f"Bot message received for room {room.display_name} | "
            f"{room.user_name(event.sender)}: {msg}"
        )

        avail_sentence_types = set(['O', 'Problem', 'Ursache', 'Lösung'])

        if self.store.get_room_recording(room.room_id) and not msg.startswith(":"):
            sent_prediction = self.sequence_predictor.predict(msg)
            tokens, labels = self.token_predictor.predict(msg)
            joined = [ f"{t}: {l}" for t, l in zip(tokens, labels) if l != "O"]
            self.store.store_message(room.room_id, msg, event.sender, event.server_timestamp, sent_prediction, joined)
            response = await send_text_to_room(self.client, room.room_id, f'I detected the following sentence type: {sent_prediction}. Is that correct? \n' +
                f'If it is correct, please type :yes, otherwise one of the following commands to correct it: {[f":{t}" for t in avail_sentence_types.difference([sent_prediction])]}')
            if isinstance(response, RoomSendResponse):
                await react_to_event(self.client, response.room_id, response.event_id, 'Yes')
                for t in avail_sentence_types.difference([sent_prediction]):
                    await react_to_event(self.client, response.room_id, response.event_id, f'{t}')
                    sleep(0.1)

        # Process as message if in a public room without command prefix
        has_command_prefix = msg.startswith(self.command_prefix)

        # Otherwise if this is in a 1-1 with the bot or features a command prefix,
        # treat it as a command
        if has_command_prefix:
            # Remove the command prefix
            msg = msg[len(self.command_prefix) :]

        command = Command(self.client, self.store, self.config, msg, room, event)
        await command.process()

    async def invite(self, room: MatrixRoom, event: InviteMemberEvent) -> None:
        """Callback for when an invite is received. Join the room specified in the invite.

        Args:
            room: The room that we are invited to.

            event: The invite event.
        """
        logger.debug(f"Got invite to {room.room_id} from {event.sender}.")

        # Attempt to join 3 times before giving up
        for attempt in range(3):
            result = await self.client.join(room.room_id)
            if type(result) == JoinError:
                logger.error(
                    f"Error joining room {room.room_id} (attempt %d): %s",
                    attempt,
                    result.message,
                )
            else:
                break
        else:
            logger.error("Unable to join room: %s", room.room_id)
            return

        # Successfully joined room
        logger.info(f"Joined {room.room_id}")
        first_join = self.store.store_new_room(room.room_id, int(time()))
        if first_join:
            logger.info("Awating sync...")
            await self.client.sync()
            response = await send_text_to_room(
                self.client,
                room.room_id,
                "Hello! I am here to record your messages. If you want me to record, please click either ✔️/❌ for yes/no."
            )
            if isinstance(response, RoomSendResponse):
                await react_to_event(self.client, room.room_id, response.event_id, "✔️")
                await react_to_event(self.client, room.room_id, response.event_id, "❌")

    async def _reaction(
        self, room: MatrixRoom, event: UnknownEvent, reacted_to_id: str
    ) -> None:
        """A reaction was sent to one of our messages. Let's send a reply acknowledging it.

        Args:
            room: The room the reaction was sent in.

            event: The reaction event.

            reacted_to_id: The event ID that the reaction points to.
        """
        logger.debug(f"Got reaction to {room.room_id} from {event.sender}.")

        # Get the original event that was reacted to
        event_response = await self.client.room_get_event(room.room_id, reacted_to_id)
        if isinstance(event_response, RoomGetEventError):
            logger.warning(
                "Error getting event that was reacted to (%s)", reacted_to_id
            )
            return
        reacted_to_event = event_response.event

        # Only acknowledge reactions to events that we sent and that come from other users
        if reacted_to_event.sender != self.config.user_id or event.sender == self.config.user_id:
            return

        reaction_content = (
            event.source.get("content", {}).get("m.relates_to", {}).get("key")
        )

        # Stay in room
        if reaction_content == '✔️':
            if not self.store.get_event_worked(reacted_to_id):
                response = "Okay, I will stay!"
                await send_text_to_room(self.client, room.room_id, response)
                self.store.set_room_recording(room.room_id)
                self.store.store_new_event(reacted_to_id, True)
            return

        # Leave room
        if reaction_content == '❌':
            if not self.store.get_event_worked(reacted_to_id):
                response = "Okay, I will leave now!"
                await send_text_to_room(self.client, room.room_id, response)
                await self.client.room_leave(room.room_id)
                self.store.delete_room(room.room_id)
                self.store.store_new_event(reacted_to_id, True)
            return

        # Accept prediction
        if reaction_content == 'Yes':
            if not self.store.get_event_worked(reacted_to_id):
                prediction = self.store.get_last_message_type()

                if prediction == 'O':
                    self.store.store_new_event(reacted_to_id, True)
                    return

                if prediction == 'Ursache':
                    if self.store.last_msg_as_cause_to_teamboard(room.room_id):
                        response = 'Message was stored as a cause to the teamboard!'
                    else:
                        response = 'Message could not be stored as a cause to the teamboard!'
                elif prediction == 'Problem':
                    if self.store.last_msg_as_problem_to_teamboard(room.room_id):
                        response = 'Message was stored as a problem to the teamboard!'
                    else:
                        response = 'Message could not be stored as a problem to the teamboard!'
                elif prediction == 'Lösung':
                    if self.store.last_msg_as_solution_to_teamboard(room.room_id):
                        response = 'Message was stored as a solution to the teamboard!'
                    else:
                        response = 'Message could not be stored as a solution to the teamboard!'

                await send_text_to_room(self.client, room.room_id, response)
                self.store.store_new_event(reacted_to_id, True)
            return

        if reaction_content == 'Ursache':
            if not self.store.get_event_worked(reacted_to_id):
                if self.store.last_msg_as_cause_to_teamboard(room.room_id):
                    response = 'Message was stored as a cause to the teamboard!'
                else:
                    response = 'Message could not be stored as a cause to the teamboard!'

                await send_text_to_room(self.client, room.room_id, response)
                self.store.store_new_event(reacted_to_id, True)
            return

        if reaction_content == 'Problem':
            if not self.store.get_event_worked(reacted_to_id):
                if self.store.last_msg_as_problem_to_teamboard(room.room_id):
                    response = 'Message was stored as a problem to the teamboard!'
                else:
                    response = 'Message could not be stored as a problem to the teamboard!'

                await send_text_to_room(self.client, room.room_id, response)
                self.store.store_new_event(reacted_to_id, True)
            return

        if reaction_content == 'Lösung':
            if not self.store.get_event_worked(reacted_to_id):
                if self.store.last_msg_as_solution_to_teamboard(room.room_id):
                    response = 'Message was stored as a solution to the teamboard!'
                else:
                    response = 'Message could not be stored as a solution to the teamboard!'

                await send_text_to_room(self.client, room.room_id, response)
                self.store.store_new_event(reacted_to_id, True)
            return
            


    async def decryption_failure(self, room: MatrixRoom, event: MegolmEvent) -> None:
        """Callback for when an event fails to decrypt. Inform the user.

        Args:
            room: The room that the event that we were unable to decrypt is in.

            event: The encrypted event that we were unable to decrypt.
        """
        logger.error(
            f"Failed to decrypt event '{event.event_id}' in room '{room.room_id}'!"
            f"\n\n"
            f"Tip: try using a different device ID in your config file and restart."
            f"\n\n"
            f"If all else fails, delete your store directory and let the bot recreate "
            f"it (your reminders will NOT be deleted, but the bot may respond to existing "
            f"commands a second time)."
        )

        red_x_and_lock_emoji = "❌ 🔐"

        # React to the undecryptable event with some emoji
        await react_to_event(
            self.client,
            room.room_id,
            event.event_id,
            red_x_and_lock_emoji,
        )

    async def unknown(self, room: MatrixRoom, event: UnknownEvent) -> None:
        """Callback for when an event with a type that is unknown to matrix-nio is received.
        Currently this is used for reaction events, which are not yet part of a released
        matrix spec (and are thus unknown to nio).

        Args:
            room: The room the reaction was sent in.

            event: The event itself.
        """
        if event.type == "m.reaction":
            # Get the ID of the event this was a reaction to
            relation_dict = event.source.get("content", {}).get("m.relates_to", {})

            reacted_to = relation_dict.get("event_id")
            if reacted_to and relation_dict.get("rel_type") == "m.annotation":
                await self._reaction(room, event, reacted_to)
                return

        logger.debug(
            f"Got unknown event with type to {event.type} from {event.sender} in {room.room_id}."
        )
