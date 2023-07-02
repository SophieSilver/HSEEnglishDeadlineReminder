import time
import taskservice
import sys
import settings
import bot
import logging
import threading


def main():
    logging.basicConfig(
        filename=settings.LOG_FILENAME,
        format=settings.LOG_FORMAT,
        datefmt=settings.LOG_DATETIME_FORMAT,
        level=settings.LOG_LEVEL,
    )
    # make it print to stdout
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(
        logging.Formatter(settings.LOG_FORMAT, datefmt=settings.LOG_DATETIME_FORMAT)
    )
    logging.getLogger().addHandler(stdout_handler)
    
    logging.info("Application started")
    
    logging.info("Starting task service")
    task_service_thread = threading.Thread(target=taskservice.task_service_worker, daemon=True)
    task_service_thread.start()
    
    logging.info("Starting bot service")
    bot_service_thread = threading.Thread(target=bot.bot_worker, daemon=True)
    bot_service_thread.start()
    
    while task_service_thread.is_alive() and bot_service_thread.is_alive():
        time.sleep(settings.LOOP_SLEEP_TIME)
    
    logging.error("Critical error: one of the threads died")
    logging.info("Trying to shut down")
    
if __name__ == "__main__":
    main()