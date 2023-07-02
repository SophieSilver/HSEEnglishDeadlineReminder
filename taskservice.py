from datetime import datetime
from typing import Iterable
from lmstasks import LMSTaskFetcher, TaskError
from model import Token, Task
from auth import LMSAuther, AuthError
from functools import partial
from pprint import pformat
# import sqlite3
import aiosqlite
import settings
import asyncio
import httpx
import logging


logger = logging.getLogger("task_service")
logger.setLevel(settings.LOG_LEVEL)


class LMSTaskService:
    def __init__(self, db_connection: aiosqlite.Connection, username: str, password: str):
        self.connection = db_connection
        self.username = username
        self.password = password
    
    async def __get_token_from_db(self, title: str) -> Token | None:
        async with self.connection.cursor() as cursor:
            await cursor.execute(
                """--sql
                    SELECT title, value, expiration_dt FROM tokens 
                    WHERE title=? AND expiration_dt > ?;
                """,
                (title, datetime.now().timestamp())
            )
        
            result = await cursor.fetchone()
            
        if result is None:
            return None
        
        return Token.decode(*result)
    
    async def __get_msis_from_auth(self) -> Token | None:
        func = partial(LMSAuther.get_msisauth_token, username=self.username, password=self.password)
        
        return await self.__call_from_auth(func)
            
    async def __get_bearer_from_auth(self, msis: Token) -> Token | None:
        func = partial(LMSAuther.get_bearer_token, msisauth_token=msis)
        
        return await self.__call_from_auth(func)
    
    async def __call_from_auth(self, func: partial):
        async with httpx.AsyncClient(timeout=httpx.Timeout(settings.TIMEOUT)) as client:
            auther = LMSAuther(client)
            
            try:
                return await func(self=auther)
            except AuthError:
                return None
    
    async def __store_token(self, token: Token):
        async with self.connection.cursor() as cursor:
            await cursor.execute(
                """--sql
                    REPLACE INTO tokens(title, value, expiration_dt)
                    VALUES (?, ?, ?);
                """,
                token.encode()
            )
        
        await self.connection.commit()
    
    async def __store_tasks(self, tasks: Iterable[Task]):
        async with self.connection.cursor() as cursor:
            await cursor.executemany(
                """--sql
                    REPLACE INTO lmstasks(id, name, type, deadline)
                    VALUES (?, ?, ?, ?);
                """,
                (task.encode() for task in tasks)
            )
        
        await self.connection.commit()
    
    async def get_msis(self) -> Token | None:
        # try getting from db
        logger.info("Getting MSISAuth token.")
        logger.info("Getting MSISAuth token from the database.")
        db_msis = await self.__get_token_from_db("MSISAuth")
        
        if db_msis is not None:
            logger.info("MSISAuth token gotten successfully.")
            return db_msis
        
        # if no tokens in db get send a request
        logger.info("Valid MSISAuth not found in the database. Requesting a new one.")
        msis = await self.__get_msis_from_auth()
        
        if msis is None:
            logger.warning("Could not get MSISAuth token.")
            return None
        
        logger.info("MSISAuth token gotten successfully.")
        logger.info("Saving the MSISAuth token.")
        
        await self.__store_token(msis)
        return msis
    
    async def get_bearer(self) -> Token | None:
        logger.info("Getting Bearer token.")
        logger.info("Getting Bearer token from the database.")
        
        db_bearer = await self.__get_token_from_db("Bearer")
        if db_bearer is not None:
            logger.info("Bearer token gotten successfully")
            return db_bearer
        
        logger.info("Valid Bearer token not found in the database. Requesting a new one.")
        
        msis = await self.get_msis()
        
        if msis is None:
            logger.warning("Could not get Bearer token")
            return None
        
        bearer = await self.__get_bearer_from_auth(msis)
        
        if bearer is None:
            logger.warning("Could not get Bearer token")
            return None
        
        logger.info("Bearer token gotten successfully")
        logger.info("Saving the Bearer token into the database")
        
        await self.__store_token(bearer)
        
        return bearer
    
    async def get_stored_tasks(self) -> list[Task]:
        logger.info("Getting tasks from the database")
        async with self.connection.cursor() as cursor:
            await cursor.execute(
                """--sql
                    SELECT id, name, type, deadline FROM lmstasks;
                """
            )
            result =await cursor.fetchall()
                
        tasks = [Task.decode(*task_data) for task_data in result]
        
        return tasks
    
    async def get_new_tasks(self) -> list[Task]:
        """
        Reuquest new tasks from the LMS server, store them in the database and return them
        """
        logger.info("Getting new tasks.")
        bearer = await self.get_bearer()
        if bearer is None:
            return []
        
        old_tasks = await self.get_stored_tasks()
        old_task_ids = {task.task_id for task in old_tasks}
        
        logger.info("Requesting new tasks.")
        async with httpx.AsyncClient(timeout=httpx.Timeout(settings.TIMEOUT)) as client:
            fetcher = LMSTaskFetcher(client, settings.COURSE_ID, settings.SUBMODULE_ID, bearer)
            try:
                tasks_without_deadlines = await fetcher.get_tasks_without_deadlines()
                new_tasks = [
                    task for task in tasks_without_deadlines 
                    if task.task_id not in old_task_ids
                ]
                await fetcher.add_deadlines(new_tasks)
                
            except TaskError as e:
                logger.warning("Could not get new tasks")
                logger.exception(e)
                return []
        
        if len(new_tasks) > 0:
            logger.info(f"Gotten {len(new_tasks)} new tasks successfully.")
            logger.info(pformat(new_tasks))
        else:
            logger.info(f"No new tasks available.")
        
        await self.__store_tasks(new_tasks)
        
        return new_tasks
        
    async def get_active_stored_tasks(self) -> list[Task]:
        logger.info("Getting active stored tasks.")
        
        async with self.connection.cursor() as cursor:
            await cursor.execute(
                """--sql
                    SELECT id, name, type, deadline FROM lmstasks
                    WHERE deadline > ?;
                """,
                (datetime.now().timestamp(), )
            )
            result = await cursor.fetchall()
        tasks = [Task.decode(*task_data) for task_data in result]
        
        return tasks


def task_service_worker():
    """
    Task service worker for running in a separate thread
    """
    async def main_coroutine():
        async def run_loop():
            try:
                while True:
                    await service.get_new_tasks()
                    await asyncio.sleep(settings.TASK_SERVICE_INTERVAL_SECONDS)
                
            except Exception as e:
                logger.exception(e)
        
        with open("AUTH_CREDENTIALS", "r", encoding="utf-8") as f:
            username, password = (s.strip() for s in f.readlines())
        
        async with aiosqlite.connect(settings.DB_PATH) as connection:
            service = LMSTaskService(connection, username, password)
            await run_loop()
    
    asyncio.run(main_coroutine())


async def main():
    from pprint import pprint
        
    logging.basicConfig(
        format=settings.LOG_FORMAT,
        datefmt=settings.LOG_DATETIME_FORMAT
    )
    
    with open("AUTH_CREDENTIALS", "r") as f:
        username, password = (s.strip() for s in f.readlines())
        
    async with aiosqlite.connect("test.db") as connection:
        
        service = LMSTaskService(connection, username, password)
        print("stored")
        pprint(await service.get_stored_tasks())
        
        print("new")
        pprint(await service.get_new_tasks())
        
        pprint(await service.get_active_stored_tasks())
    
if __name__ == "__main__":
    asyncio.run(main())
    
