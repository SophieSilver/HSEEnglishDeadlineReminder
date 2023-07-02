import asyncio
from datetime import timedelta
from model import User
# import sqlite3
import aiosqlite
import logging
import settings

logger = logging.getLogger("user_service")
logger.setLevel(settings.LOG_LEVEL)

class UserService:
    def __init__(self, db_connection: aiosqlite.Connection):
        self.connection = db_connection
    
    async def register_new_user(self, user_id: int) -> User:
        logger.info(f"Registering a new user with id: {user_id}")
        
        user = User(user_id=user_id)
        
        async with self.connection.cursor() as cursor:
            await cursor.execute(
                """--sql
                    INSERT OR IGNORE INTO users(id, is_active, remind_interval)
                    VALUES (?, ?, ?);
                """,
                user.encode()
            )
        
        await self.connection.commit()
        
        return user
        
    async def get_stored_user(self, user_id: int) -> User | None:
        """
        Gets the user from the database by id.
        """
        
        logger.info(f"Getting user info for user with id: {user_id}")
        
        async with self.connection.cursor() as cursor:
            await cursor.execute(
                """--sql
                    SELECT id, is_active, remind_interval FROM users WHERE id = ?;
                """,
                (user_id, )
            )
            
            result = await cursor.fetchone()
        
        if result is None:
            logger.info("User info not found")
            return None
        
        logger.info("Found user info")
        return User.decode(*result)
    
    async def get_or_register_user(self, user_id: int) -> User:
        user = await self.get_stored_user(user_id)
        
        if user is None:
            return await self.register_new_user(user_id)
        
        return user
    
    async def update_user(self, user: User):
        logger.info(f"Updating user info for user with id: {user.user_id}")
    
        async with self.connection.cursor() as cursor: 
            await cursor.execute(
                """--sql
                    REPLACE INTO users(id, is_active, remind_interval)
                    VALUES (?, ?, ?);
                """,
                user.encode()
            )
        
        await self.connection.commit()

    async def get_active_users(self) -> list[User]:
        logger.debug("Getting the list of active users")
        async with self.connection.cursor() as cursor:
            await cursor.execute(
                """--sql
                    SELECT id, is_active, remind_interval
                    FROM users
                    WHERE is_active = 1;
                """
            )
        
            users_raw = await cursor.fetchall()
        
        return [User.decode(*user_data) for user_data in users_raw]

async def main():
    logging.basicConfig(
        format=settings.LOG_FORMAT,
        datefmt=settings.LOG_DATETIME_FORMAT
    )
    
    async with aiosqlite.connect("test.db") as connection:
        service = UserService(connection)
        
        user = await service.get_stored_user(1)
        if user is None:
            user = await service.register_new_user(1)
            
        user.remind_interval = timedelta(seconds=30)
        await service.update_user(user)
        

if __name__ == "__main__":
    asyncio.run(main())