from datetime import datetime, timedelta
from pprint import pformat
import time
from aiogram import Bot, Dispatcher, types
from aiogram.utils import exceptions
import pytz
from model import ReminderInlineQueryData, Task, TaskType, User
from userservice import UserService
from remindservice import RemindService
# import sqlite3
import aiosqlite
import asyncio
import settings
import bot_messages
import logging
import pytimeparse

logger = logging.getLogger("bot")
logger.setLevel(settings.LOG_LEVEL)

class BotService:
    def __init__(self, connection: aiosqlite.Connection, api_token: str):
        self.user_service = UserService(connection)
        self.remind_service = RemindService(connection)
        self.bot = Bot(api_token)
        self.dispatcher = Dispatcher(self.bot)
        
        self.create_handlers()
        
    def create_handlers(self):
        @self.dispatcher.message_handler(commands=("help",))
        async def help(message: types.Message):
            logger.info(f"User {message.from_id} ({message.from_user.full_name} @{message.from_user.username}) used /help")
            await message.answer(bot_messages.HELP, settings.BOT_MESSAGE_PARSE_MODE)
            
        @self.dispatcher.message_handler(commands=("start",))
        async def start(message: types.Message):
            logger.info(f"User {message.from_id} ({message.from_user.full_name} @{message.from_user.username}) used /start")
            
            user_id = message.from_id
            user = await self.user_service.get_stored_user(user_id)
            
            # first time using the bot
            if user is None:
                logger.info("user not found, registering...")
                user = await self.user_service.register_new_user(user_id)
                await message.answer(bot_messages.GREETING, settings.BOT_MESSAGE_PARSE_MODE)
                return
            
            if user.is_active:
                logger.info("User is already active")
                await message.answer(bot_messages.REMINDERS_ALREADY_FMT.format("on"))
                return
            
            logger.info("Marking the user as active")
            user.is_active = True
            try:
                await self.user_service.update_user(user)
            
            except Exception as e:
                logger.exception(e)
                await message.answer(bot_messages.ERROR, settings.BOT_MESSAGE_PARSE_MODE)
                return
            
            await message.answer(bot_messages.REMINDERS_TURNED_FMT.format("on"))
        
        @self.dispatcher.message_handler(commands=("stop",))
        async def stop(message: types.Message):
            logger.info(f"User {message.from_id} ({message.from_user.full_name} @{message.from_user.username}) used /stop")
            
            user_id = message.from_id
            user = await self.user_service.get_or_register_user(user_id)
            
            if not user.is_active:
                logger.info(f"User is already inactive")
                await message.answer(bot_messages.REMINDERS_ALREADY_FMT.format("off"))
                return
            
            logger.info(f"Marking the user as inactive")
            user.is_active = False
            try:
                await self.user_service.update_user(user)
            
            except Exception as e:
                logger.exception(e)
                await message.answer(bot_messages.ERROR, settings.BOT_MESSAGE_PARSE_MODE)
                return
            
            await message.answer(bot_messages.REMINDERS_TURNED_FMT.format("off"))
        
        @self.dispatcher.message_handler(commands=("set_remind_interval",))
        async def set_remind_interval(message: types.Message):
            logger.info(f"User {message.from_id} ({message.from_user.full_name} @{message.from_user.username}) used /set_remind_interval")
            user = await self.user_service.get_or_register_user(message.from_id)
            
            args = message.get_args()
            logger.info(f"{args=}")
            
            if args is None or len(args.strip()) == 0:
                logger.info("Empty args")
                await message.answer(bot_messages.INTERVAL_NO_ARGS)
                return
                
            interval_seconds = pytimeparse.parse(args)
            logger.info(f"{interval_seconds=}")
            
            if interval_seconds is None:
                logger.info("Couldn't parse the interval")
                await message.answer(bot_messages.INTERVAL_IS_NONE)
                return
            
            if interval_seconds < settings.MIN_REMIND_INTERVAL_SECONDS:
                logger.info("the interval is less than the allowed minimum")
                await message.answer(
                    bot_messages\
                        .INTERVAL_LESS_THAN_SECONDS_FMT\
                        .format(settings.MIN_REMIND_INTERVAL_SECONDS)
                    )
                return
            
            interval = timedelta(seconds=interval_seconds)
            logger.info(f"{interval}")
            logger.info("setting the remind interval for the user")
            user.remind_interval = interval
            try:
                await self.user_service.update_user(user)
            except Exception as e:
                logger.exception(e)
                await message.answer(bot_messages.ERROR)
                return
            
            await message.answer(bot_messages.INTERVAL_CHANGED_FMT.format(str(interval)))
            
        @self.dispatcher.message_handler()
        async def non_command(message: types.Message):
            logger.info(f"User {message.from_id} ({message.from_user.full_name} @{message.from_user.username}) used a non-command:\n{message.text}")
            
            await message.answer(bot_messages.UNKNOWN, settings.BOT_MESSAGE_PARSE_MODE)
        
        @self.dispatcher.callback_query_handler()
        async def switch_reminder(callback: types.CallbackQuery):
            query_data = ReminderInlineQueryData.deminimize(callback.data)
            user_id = callback.from_user.id
            
            logger.info(f"Inline query from {user_id} ({callback.from_user.full_name} @{callback.from_user.username}) with data {query_data}")
            
            if query_data is None:
                logger.info("Query data is None")
                return
            
            task = await self.remind_service.get_task_by_id(query_data.task_id)
            if task is None:
                logger.info("task is None.")
                return
            
            # change reminder
            logger.info("Changing reminder settings")
            await self.remind_service.set_reminder_active(
                query_data.task_id, user_id, query_data.set_active
            )
            
            # change the button on the old message
            new_button_text = (
                bot_messages.TURN_REMINDER_OFF 
                if query_data.set_active 
                else bot_messages.TURN_REMINDER_ON
            )
            # copy query data but invert set_active
            new_query_data = query_data.copy()
            new_query_data.set_active = not query_data.set_active
            
            new_button = types.InlineKeyboardButton(
                new_button_text, 
                callback_data=new_query_data.minimized()
            )
            keyboard = types.InlineKeyboardMarkup(1)
            keyboard.add(new_button)
            
            # send the message 
            message_text = (
                bot_messages.REMINDER_TURNED_ON_FMT
                if query_data.set_active
                else bot_messages.REMINDER_TURNED_OFF_FMT
            ).format(task.name)
            
            logger.info("Updating the button and sending the message.")
            # change the button and send message at the same time
            await asyncio.gather(
                callback.message.edit_reply_markup(keyboard),
                self.bot.send_message(
                    user_id, 
                    message_text, 
                    settings.BOT_MESSAGE_PARSE_MODE
                )
            )
        
    async def remind_active_users(self):
        # gets all active tasks for that user and reminds them of each of them
        async def remind_user_all(user: User):
            reminders = await self.remind_service.get_current_reminders(user.user_id)
            
            await asyncio.gather(*(self.remind_user(user, task) for task in reminders))
        
        active_users = await self.user_service.get_active_users()
        logger.debug(f"Gotten {len(active_users)} users: {pformat(active_users)}")
        
        await asyncio.gather(*(remind_user_all(user) for user in active_users))
    
    async def remind_user(self, user: User, task: Task):
        logger.info(f"reminding user {user.user_id} about {task}")
        # shouldn't happen but here so that pylance doesn't complain
        if task.deadline is None:
            raise ValueError("Task deadline is None")
        
        type_map = {
            TaskType.QUIZ: "quiz",
            TaskType.ASSIGNMENT: "assignment"
        }
        type_str = type_map[task.task_type]
        
        # rounding to whole seconds
        seconds_left = int((task.deadline.astimezone(pytz.utc) - datetime.now(tz=pytz.utc)).total_seconds())
        time_left = timedelta(seconds=seconds_left)
        
        reminder_text = bot_messages.REMINDER_FMT.format(
            type_str,
            task.name,
            task.deadline.astimezone(
                pytz.timezone("Europe/Moscow")).strftime(settings.DATETIME_FORMAT
            ),
            str(time_left),
            task.task_type.value,
            str(task.task_id)
        )
        
        # making the inline keyboard
        keyboard = types.InlineKeyboardMarkup(1)
        
        query = ReminderInlineQueryData(
            task_id=task.task_id,
            set_active=False    # change if we ever remind of inactive tasks
        )
        callback_data = query.minimized()
        
        button = types.InlineKeyboardButton(
            bot_messages.TURN_REMINDER_OFF,
            callback_data=callback_data
        )
        
        keyboard.add(button)
        
        try:
            await self.bot.send_message(
                user.user_id, 
                reminder_text, 
                settings.BOT_MESSAGE_PARSE_MODE,
                reply_markup=keyboard,
                disable_web_page_preview=True
            )
            
            await self.remind_service.set_reminded_time(task.task_id, user.user_id, datetime.now())
            
        except exceptions.BotBlocked as e:
            logger.error(f"User {user.user_id} blocked the bot")
            logger.exception(e)
            logger.info(f"Making user {user.user_id} inactive")
            
            user.is_active = False
            
            try:
                await self.user_service.update_user(user)
            except Exception as e:
                logger.exception(e)
                
        except Exception as e:
            logger.exception(e)
    

    async def run_bot_non_blocking(self):
        asyncio.create_task(self.dispatcher.start_polling(int(settings.TIMEOUT)))
        
    async def run_bot(self):
        await self.dispatcher.start_polling(int(settings.TIMEOUT))
        

def bot_worker():
    async def main_coroutine():
        async with aiosqlite.connect(settings.DB_PATH) as connection:
            try:
                service = BotService(connection, token)
                await service.run_bot_non_blocking()
                while True:
                    await service.remind_active_users()
                    await asyncio.sleep(settings.BOT_SERVICE_INTERVAL_SECONDS)
            except Exception as e:
                logger.exception(e)
    
    with open("API_TOKEN", "r", encoding="utf-8") as f:
        token = f.read().strip()
    
    asyncio.run(main_coroutine())
