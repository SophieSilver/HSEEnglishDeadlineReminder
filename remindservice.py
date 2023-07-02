from model import Task, User
from datetime import datetime
# import sqlite3
import aiosqlite
import asyncio
import logging
import settings



logger = logging.getLogger("remind_service")
logger.setLevel(settings.LOG_LEVEL)


class RemindService:
    def __init__(self, connection: aiosqlite.Connection):
        self.connection = connection

    async def get_current_reminders(self, user_id: int) -> list[Task]:
        """
        Get all the tasks for this user that they should be reminded about,
        i.e. the tasks that the user wasn't reminded of in more than the remind interval
        """
        logger.debug(f"Getting current reminders for user {user_id}")

        # THE MONSTROSITY
        async with self.connection.cursor() as cursor:
            await cursor.execute(
                """--sql
                SELECT lmstasks.id, name, type, deadline FROM 
                lmstasks LEFT JOIN reminders 
                ON lmstasks.id = task_id AND user_id = :user_id
                JOIN users
                ON users.id = :user_id
                
                WHERE 
                deadline > :timestamp_now -- not overdue
                AND
                (
                    last_reminded IS NULL OR last_reminded = '' -- never reminded
                    OR
                    (
                        reminders.is_active = 1   -- not turned off
                        AND
                        last_reminded < :timestamp_now - remind_interval
                        --reminded more than remind_interval seconds ago
                    )
                )
                """,
                {"user_id": user_id, "timestamp_now": datetime.now().timestamp()},
            )
            result = await cursor.fetchall()

        tasks = [Task.decode(*task_data) for task_data in result]

        return tasks

    async def get_reminded_time(self, task_id: int, user_id: int) -> datetime | None:
        logger.info(f"Getting remind time for task {task_id} for user {user_id}")

        async with self.connection.cursor() as cursor:
            await cursor.execute(
                """--sql
                SELECT last_reminded FROM reminders
                WHERE task_id = ? AND user_id = ?;
                """,
                (task_id, user_id),
            )
            result = await cursor.fetchone()

        if result is None:
            return None

        return datetime.fromtimestamp(result[0])

    async def set_reminded_time(self, task_id: int, user_id: int, time: datetime):
        """
        Sets the last reminded time of this task for this user
        """
        logger.info(f"Updating remind time for task {task_id} for user {user_id}")
        
        async with self.connection.cursor() as cursor:
            await cursor.execute(
                """--sql
                    REPLACE INTO reminders (task_id, user_id, last_reminded)
                    VALUES (?, ?, ?);
                """,
                (task_id, user_id, time.timestamp()),
            )

        await self.connection.commit()

    async def set_reminder_active(self, task_id: int, user_id: int, is_active: bool):
        logger.info(
            f"Setting reminders for task {task_id} for user {user_id} to {is_active}"
        )

        async with self.connection.cursor() as cursor:
            await cursor.execute(
                """--sql
                    UPDATE OR IGNORE reminders
                    SET is_active = ?
                    WHERE task_id = ? AND user_id = ?;
                """,
                (is_active, task_id, user_id),
            )

        await self.connection.commit()

    # needed for reminder messages
    async def get_task_by_id(self, task_id: int) -> Task | None:
        logger.info(f"Getting task {task_id}")

        async with self.connection.cursor() as cursor:
            await cursor.execute(
                """--sql
                    SELECT id, name, type, deadline FROM lmstasks
                    WHERE id = ?;
                """,
                (task_id,),
            )

            result = await cursor.fetchone()

        if result is None:
            return None

        return Task.decode(*result)
