from bs4 import BeautifulSoup, ResultSet, Tag
import httpx
from datetime import datetime
import dateparser
import pytz
from auth import AuthError
from typing import Iterable
from model import Token, Task, TaskType
import asyncio
import json
import html
from pprint import pprint


MSK_TIMEZONE = "Europe/Moscow"


class TaskError(Exception):
    pass

class TaskDeserializationError(TaskError):
    pass

class TaskFetchError(TaskError):
    pass

class LMSTaskFetcher:
    TASKS_REQUEST_URL = "https://edu.hse.ru/webservice/adfsrest/server.php"
    ASSIGN_VIEW_HOST = "https://edu.hse.ru/mod/assign/view.php"
    QUIZ_VIEW_HOST = "https://edu.hse.ru/mod/quiz/view.php"
    
    def __init__(self, client: httpx.AsyncClient, course_id: int, submodule_id: int, bearer: Token):
        self.client = client
        self.course_id = course_id
        self.submodule_id = submodule_id
        self.bearer_token = bearer

    async def __fetch_tasks_raw(self) -> str:
        form_data = {
            "wsfunction": "core_course_get_contents",
            "courseid": self.course_id,
            "moodlewssettinglang": "en",
            "moodlewsrestformat": "json",
            "moodlewssettingfilter": True
        }
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Bearer {self.bearer_token.value}"
        }
        
        try:
            response = await self.client.post(self.TASKS_REQUEST_URL, data=form_data, headers=headers)
            response.raise_for_status()
        except httpx.HTTPError as e:
            raise TaskFetchError(str(e))
        
        return response.text
        
    def __deserealize_tasks(self, raw_response: str) -> list[Task]:
        try:
            sub_module_list: list[dict] = json.loads(raw_response)
            
            # find the dict that corresponds to SMART LMS training submodule
            lms_training_dict: dict | None = None
            for i in sub_module_list:
                if i["id"] == self.submodule_id:
                    lms_training_dict = i
                    break
            
            if lms_training_dict is None:
                raise TaskDeserializationError("Task dictionary not found")
            
            task_dict_list: list[dict] = lms_training_dict["modules"]
            task_list: list[Task] = []
            
            for task_dict in task_dict_list:
                task_id = task_dict["id"]
                name = html.unescape(task_dict["name"])
                task_type = TaskType(task_dict["modname"])
                
                task = Task(task_id=task_id, task_type=task_type, name=name)
                task_list.append(task)
            
        except (TypeError, AttributeError, KeyError) as e:
            raise TaskDeserializationError(f"Error while deserializing tasks: {e}")
        
        return task_list
    
    async def __fetch_task_view(self, task: Task) -> str:
        params = {
            "id": task.task_id,
            "lang": "en",
            "token": self.bearer_token.value
        }
        
        # cookies = {
        #     self.moodle_token.title: self.moodle_token.value
        # }
        
        try:
            match task.task_type:
                case TaskType.ASSIGNMENT:
                    task_page = await self.client.get(self.ASSIGN_VIEW_HOST, params=params)
                case TaskType.QUIZ:
                    task_page = await self.client.get(self.QUIZ_VIEW_HOST, params=params)
                case _: 
                    raise TaskDeserializationError("Unknown task type")
                    
            task_page.raise_for_status()
        except httpx.HTTPError as e:
            raise TaskFetchError(str(e))
        
        return task_page.text
        
    def __get_assignment_deadline(self, soup: BeautifulSoup) -> datetime:
        DUE_DATE_TEXT = "Due date"
        deadline = None
        
        try:
            table = soup.select_one(".generaltable")
            
            rows = table.select("tr")                   # type: ignore
            for row in rows:
                header = row.select_one("th")
                data = row.select_one("td")
                
                if header.text != DUE_DATE_TEXT:        # type: ignore
                    continue
                
                settings = {
                    "TIMEZONE": MSK_TIMEZONE,
                    "RETURN_AS_TIMEZONE_AWARE": True
                }
                
                deadline = dateparser.parse(data.text, settings=settings)          # type: ignore
                break
                
        except (KeyError, TypeError, AttributeError) as e:
            raise TaskDeserializationError(str(e))
        
        if deadline is None:
            raise TaskDeserializationError("Could not parse the due date")
        
        return deadline
        
    def __get_quiz_deadline(self, soup: BeautifulSoup) -> datetime:
        deadline = None
        
        try:
            # this has a similar format to "This quiz closes on Monday, 26 september, 2022"
            # get the second p element
            quizinfo = soup.select(".quizinfo p")
            
            deadline = self.__get_due_date_from_quizinfo(quizinfo)
            
                
        except (KeyError, TypeError, AttributeError) as e:
            raise TaskDeserializationError(str(e))
        
        if deadline is None:
            raise TaskDeserializationError("Could not parse the due date")
        
        return deadline
    
    @staticmethod
    def __get_due_date_from_quizinfo(quizinfo: ResultSet[Tag]) -> datetime | None:
        deadline = None
        
        for tag in reversed(quizinfo):
            try:
                line = tag.text
                due_date_str = line.split(",", 1)[1]    # split after the day of the week
                
                settings = {
                    "TIMEZONE": MSK_TIMEZONE,
                    "RETURN_AS_TIMEZONE_AWARE": True
                }
                deadline = dateparser.parse(due_date_str, settings=settings)    # type: ignore
                
                if deadline is not None:
                    break

            except IndexError:
                continue
        
        return deadline
    
    async def get_deadline(self, task: Task) -> datetime:
        task_view = await self.__fetch_task_view(task)
        soup = BeautifulSoup(task_view, features="html.parser")
        
        match task.task_type:
            case TaskType.QUIZ:
                return self.__get_quiz_deadline(soup)
            case TaskType.ASSIGNMENT:
                return self.__get_assignment_deadline(soup)
            case _:
                raise TaskError("Unknown task type")
    
    async def add_deadlines(self, task_list: Iterable[Task]):
        # for task in task_list:
        #     deadline = await self.get_deadline(task)
        #     task.deadline = deadline
        
        # doing it through tasks asynchronously coz it's faster
        # as waiting for each requests doesn't disrupt the program
        async def add_deadline_to_task(task: Task):
            deadline = await self.get_deadline(task)
            task.deadline = deadline
            
        await asyncio.gather(*(add_deadline_to_task(task) for task in task_list))
            
    async def get_tasks_without_deadlines(self) -> list[Task]:
        """
        Getting all tasks, but with deadlines set to None.
        
        This is useful if you don't want to know the deadlines right away,
        as getting a deadline requires additional requests which might slow down your application
        """
        raw_tasks = await self.__fetch_tasks_raw()
        tasks = self.__deserealize_tasks(raw_tasks)
        
        return tasks
    
    async def get_tasks_full(self) -> list[Task]:
        """
        Getting all tasks with deadlines.
        Might be slower than doing it without deadlines
        """
        
        tasks = await self.get_tasks_without_deadlines()
        await self.add_deadlines(tasks)
        
        return tasks
        

async def main():    
    from auth import LMSAuther
    from time import perf_counter
    
    COURSE_ID = 121520
    SUBMODULE_ID = 819742
    
    login_start = perf_counter()
    print("Logging into SmartLMS")
    
    with open("AUTH_CREDENTIALS", "r") as f:
        username, password = (s.strip() for s in f.readlines())
        
    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
        auther = LMSAuther(client)
        msis = await auther.get_msisauth_token(username, password)
        bearer = await auther.get_bearer_token(msis)
        
        print(f"Logged in in {perf_counter() - login_start:.2f} s")
        
        print("getting the tasks")
        task_get_start = perf_counter()
        
        task_fetcher = LMSTaskFetcher(client, COURSE_ID, SUBMODULE_ID, bearer)
        tasks = await task_fetcher.get_tasks_full()
        print(f"gotten the tasks in {perf_counter() - task_get_start:.2f} s")
        pprint(tasks)
        dd: datetime = tasks[-1].deadline   #type:ignore
        print(dd.timestamp())
        print(dd.astimezone(pytz.timezone("UTC")).timestamp())
        print(datetime.fromtimestamp(dd.timestamp()).timestamp())     

if __name__ == "__main__":
    # try:
        asyncio.run(main())
    # except (AuthError, TaskError) as e:
    #     print("Oopsie daisy, something went wrong")
    #     print(e)
    