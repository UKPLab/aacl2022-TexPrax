import re
import logging
from sqlite3.dbapi2 import Error
from typing import Any, Dict, List

from tinydb import TinyDB, Query
from tinydb.operations import set
from texpraxconnector.dashboard_requests import DashboardConnector

# The latest migration version of the database.
#
# Database migrations are applied starting from the number specified in the database's
# `migration_version` table + 1 (or from 0 if this table does not yet exist) up until
# the version specified here.
#
# When a migration is performed, the `migration_version` table should be incremented.
latest_migration_version = 0

logger = logging.getLogger(__name__)


class Storage:
    def __init__(self, database_config: Dict[str, str]):
        """Setup the database.

        Runs an initial setup or migrations depending on whether a database file has already
        been created.

        Args:
            database_config: a dictionary containing the following keys:
                * type: A string, one of "sqlite" or "postgres".
                * connection_string: A string, featuring a connection string that
                    be fed to each respective db library's `connect` method.
        """
        self.conn = self._get_database_connection(
            database_config["type"], database_config["connection_string"]
        )
        self.cursor = self.conn.cursor()
        self.db_type = database_config["type"]

        self.messages = TinyDB(database_config["message_path"])

        # Try to check the current migration version
        migration_level = 0
        try:
            self._execute("SELECT version FROM migration_version")
            row = self.cursor.fetchone()
            migration_level = row[0]
        except Exception:
            self._initial_setup()
        finally:
            if migration_level < latest_migration_version:
                self._run_migrations(migration_level)

        logger.info(f"Database initialization of type '{self.db_type}' complete")
        
        #TODO: add password/username here
        self.login_data = {"username":"username",
           "password":"password"}

    def _get_database_connection(
        self, database_type: str, connection_string: str
    ) -> Any:
        """Creates and returns a connection to the database"""
        if database_type == "sqlite":
            import sqlite3

            # Initialize a connection to the database, with autocommit on
            return sqlite3.connect(connection_string, isolation_level=None)
        elif database_type == "postgres":
            import psycopg2

            conn = psycopg2.connect(connection_string)

            # Autocommit on
            conn.set_isolation_level(0)

            return conn

    def _initial_setup(self) -> None:
        """Initial setup of the database"""
        logger.info("Performing initial database setup...")

        # Set up the migration_version table
        self._execute(
            """
            CREATE TABLE migration_version (
                version INTEGER PRIMARY KEY
            )
        """
        )

        # Initially set the migration version to 0
        self._execute(
            """
            INSERT INTO migration_version (
                version
            ) VALUES (?)
        """,
            (0,),
        )

        # Create the 'rooms' table
        self._execute(
            """
            CREATE TABLE rooms (
                roomid TEXT PRIMARY KEY,
                joined INTEGER,
                recording INTEGER,
                timestamp INTEGER
            )
        """
        )

        # Create the 'events' table
        self._execute(
            """
            CREATE TABLE events (
                eventid TEXT PRIMARY KEY,
                worked INTEGER
            )
        """
        )

        # Set up any other necessary database tables here

        logger.info("Database setup complete")

    def _run_migrations(self, current_migration_version: int) -> None:
        """Execute database migrations. Migrates the database to the
        `latest_migration_version`.

        Args:
            current_migration_version: The migration version that the database is
                currently at.
        """
        logger.debug("Checking for necessary database migrations...")

        # if current_migration_version < 1:
        #    logger.info("Migrating the database from v0 to v1...")
        #
        #    # Add new table, delete old ones, etc.
        #
        #    # Update the stored migration version
        #    self._execute("UPDATE migration_version SET version = 1")
        #
        #    logger.info("Database migrated to v1")

    def _execute(self, *args) -> None:
        """A wrapper around cursor.execute that transforms placeholder ?'s to %s for postgres.

        This allows for the support of queries that are compatible with both postgres and sqlite.

        Args:
            args: Arguments passed to cursor.execute.
        """
        if self.db_type == "postgres":
            self.cursor.execute(args[0].replace("?", "%s"), *args[1:])
        else:
            self.cursor.execute(*args)

    def _get_room_info(self, roomid: str) -> List:
        if self.db_type == "sqlite":
            import sqlite3
        else:
            raise NotImplementedError
        try:
            return self.cursor.execute(
                """
                SELECT roomid, joined, recording, timestamp
                    FROM rooms
                    WHERE roomid='{}'
            """.format(roomid)
            ).fetchall()

            return recording == 1
        except sqlite3.DatabaseError as dbe:
            logger.warning(f"Could not get info about room {roomid}")

    def store_message(self, roomid: str, message: str, sender: str, timestamp: int, sent_type: str, tokens: List[str]):
        self.messages.insert({
            "roomid": roomid,
            "message": message,
            "sender": sender,
            "timestamp": timestamp,
            "type": sent_type,
            "tokens": tokens,
        })

    def change_last_message_type(self, sent_type: str, room_id: str):
        Room = Query()
        room_msgs = self.messages.search(Room.roomid == room_id)
        latest_msg = sorted(room_msgs, key=lambda e: e.doc_id)[len(room_msgs) - 1]
        latest_msg['type'] = sent_type
        Room = Query()
        self.messages.update({"type": sent_type}, (Room.timestamp == latest_msg["timestamp"]) & (Room.sender == latest_msg["sender"]))
    
    def get_last_message_type(self):
        return self.messages.get(doc_id=len(self.messages))["type"]

    def last_msg_as_problem_to_dashboard(self, room_id: str) -> bool:
        try:
            Room = Query()
            room_msgs = self.messages.search(Room.roomid == room_id)
            last_row = sorted(room_msgs, key=lambda e: e.doc_id)[len(room_msgs) - 1]
            connector = DashboardConnector(self.login_data)
            connector.set_group("Key User")
            connector.create_problem(last_row["message"])

            return True
        except Error:
            return False

    def last_msg_as_solution_to_dashboard(self, room_id: str) -> bool:
        try: 
            Room = Query()
            room_msgs = self.messages.search(Room.roomid == room_id)
            last_row = sorted(room_msgs, key=lambda e: e.doc_id)[len(room_msgs) - 1]["message"]
            # Check if the last message was a reply to another message or just a regular message
            # If it was no reply, ignore it.
            if not last_row.startswith("> <"):
                return False
            # If it was a reply, make sure to find the corresponding problem.
            # We don't really know when the citation ends, so we have to rely on
            # a newline character:
            regex = re.compile(r"> <.*>") 
            last_row = re.sub(regex, "", last_row).strip() # Removes the part with the username of the old msg
            old_problem = last_row.split("\n")[0] # This is tricky. If the cited msg contains a newline, this won't work
            old_problem = old_problem[:75] if len(old_problem) >= 75 else old_problem # Only the first 75 chars are stored in the teamboard
            # Remove the part with the old problem and strip newlines from the solution:
            new_solution = "\n".join(last_row.split("\n")[1:]).strip()
            
            connector = DashboardConnector(self.login_data)
            connector.set_group("Key User")

            connector.add_solution(old_problem, new_solution)

            return True
        except IndexError:
            return False
        except Error:
            return False

    def last_msg_as_cause_to_dashboard(self, room_id: str) -> bool:
        try:
            Room = Query()
            room_msgs = self.messages.search(Room.roomid == room_id)
            last_row = sorted(room_msgs, key=lambda e: e.doc_id)[len(room_msgs) - 1]["message"]
            # Check if the last message was a reply to another message or just a regular message
            # If it was no reply, ignore it.
            if not last_row.startswith("> <"):
                return False
            # If it was a reply, make sure to find the corresponding problem.
            # We don't really know when the citation ends, so we have to rely on
            # a newline character:
            regex = re.compile(r"> <.*>") 
            last_row = re.sub(regex, "", last_row).strip() # Removes the part with the username of the old msg
            old_problem = last_row.split("\n")[0] # This is tricky. If the cited msg contains a newline, this won't work
            old_problem = old_problem[:75] if len(old_problem) >= 75 else old_problem # Only the first 75 chars are stored in the teamboard
            # Remove the part with the old problem and strip newlines from the solution:
            new_cause = "\n".join(last_row.split("\n")[1:]).strip()
            
            connector = DashboardConnector(self.login_data)
            connector.set_group("Key User")

            connector.add_cause(old_problem, new_cause)
            return True
        except IndexError:
            return False
        except Error:
            return False



    def store_new_room(self, roomid: str, timestamp: int) -> bool:
        """Stores a new room in the database.

        Args:
            roomid (str): The room id
            timestamp (int): The timestamp the bot joined this room

        Raises:
            NotImplementedError: Raised if anything else than sqlite3 is chosen as a database

        Returns:
            bool: True, if the room did not exist before and was succesfully added, else false
        """
        if self.db_type == "sqlite":
            import sqlite3
        else:
            raise NotImplementedError
        try:
            self._execute(
                """
                INSERT INTO rooms (roomid, joined, recording, timestamp)
                VALUES ('{}', 1, 0, {})
            """.format(roomid, timestamp)
            )
            logger.info("Stored new room in DB")
            return True
        except sqlite3.IntegrityError:
            logger.debug("Room already stored, ignoring")
            return False
        except sqlite3.DatabaseError as e:
            import pdb; pdb.set_trace()
            logger.warning(f"Could not store room {roomid}")
            return False

    def store_new_event(self, eventid: str, worked: bool) -> None:
        if self.db_type == "sqlite":
            import sqlite3
        else:
            raise NotImplementedError
        try:
            self._execute(
                """
                INSERT INTO events (eventid, worked)
                VALUES ('{}', {})
            """.format(eventid, int(worked))
            )
        except sqlite3.DatabaseError:
            logger.warning(f"Could not  store new event {eventid}")

    def set_room_recording(self, roomid: str) -> None:
        if self.db_type == "sqlite":
            import sqlite3
        else:
            raise NotImplementedError
        try:
            self._execute(
                """
                UPDATE rooms
                    SET recording=1
                    WHERE roomid='{}'
            """.format(roomid)
            )
        except sqlite3.DatabaseError:
            logger.warning(f"Could not set the room {roomid} to recording")

    def get_room_recording(self, roomid: str) -> bool:
        try:
            return int(self._get_room_info(roomid)[0][2]) == 1
        except (IndexError, TypeError):
            logger.warning(f"Room {roomid} does not exist in DB")
            return 0

    def get_room_timestamp(self, roomid: str) -> int:
        try:
            return int(self._get_room_info(roomid)[0][3])
        except (IndexError, TypeError):
            logger.warning(f"Room {roomid} does not exist in DB")
            return 0

    def get_event_worked(self, eventid: str) -> bool:
        if self.db_type == "sqlite":
            import sqlite3
        else:
            raise NotImplementedError
        try:
            results = self.cursor.execute(
                """
                SELECT eventid, worked
                    FROM events
                    WHERE eventid='{}'
            """.format(eventid)
            ).fetchall()

            if len(results) == 0:
                return False
            if results[0][1] == 0:
                return False
            return True
        except sqlite3.DatabaseError as dbe:
            logger.warning(f"Could not get info about event {eventid}")

    def delete_room(self, roomid: str) -> None:
        if self.db_type == "sqlite":
            import sqlite3
        else:
            raise NotImplementedError

        try:
            self._execute(
                """
                DELETE FROM rooms
                    WHERE roomid='{}'
            """.format(roomid)
            )
        except sqlite3.DatabaseError:
            logger.warning(f"Could not delete the room {roomid}")
