from __future__ import annotations

from pydantic import BaseModel
from datetime import datetime, timedelta
from enum import Enum

class TaskType(Enum):
    QUIZ = "quiz"
    ASSIGNMENT = "assign"


class Token(BaseModel):
    title: str
    value: str
    expiration_dt: datetime
    
    def encode(self) -> tuple[str, str, float]:
        return (self.title, self.value, self.expiration_dt.timestamp())
    
    @staticmethod
    def decode(title: str, value: str, expiration_timestamp) -> Token:
        expiration_dt = datetime.fromtimestamp(expiration_timestamp)
        
        return Token(title=title, value=value, expiration_dt=expiration_dt)
    

class Task(BaseModel):
    task_id: int
    name: str
    task_type: TaskType
    deadline: datetime | None = None
    
    def encode(self) -> tuple[int, str, str, float]:
        deadline_timestamp = self.deadline.timestamp() if self.deadline is not None else 0
        
        return (
            self.task_id,
            self.name,
            self.task_type.value,
            deadline_timestamp
        )
    
    @staticmethod
    def decode(task_id: int, name: str, task_type_str: str, deadline_timestamp: float) -> Task:
        task_type = TaskType(task_type_str)
        deadline = datetime.fromtimestamp(deadline_timestamp)
        
        return Task(task_id=task_id, name=name, task_type=task_type, deadline=deadline)


class User(BaseModel):
    user_id: int
    is_active: bool = True
    remind_interval: timedelta = timedelta(days=1)
    
    def encode(self) -> tuple[int, bool, float]:
        return (self.user_id, self.is_active, self.remind_interval.total_seconds())
    
    @staticmethod
    def decode(user_id: int, is_active: bool, remind_seconds: float) -> User:
        return User(
            user_id=user_id, 
            is_active=is_active, 
            remind_interval=timedelta(seconds=remind_seconds)
        )
    
    
class ReminderInlineQueryData(BaseModel):
    task_id: int
    # user_id: int      # can be gotten from the query, unnecessary here
    set_active: bool
    
    def minimized(self) -> str:
        return ",".join(
            (
                str(self.task_id), 
                # str(self.user_id), 
                str(int(self.set_active))
            )
        )
        
    @staticmethod
    def deminimize(data: str) -> ReminderInlineQueryData | None:
        try:
            task_id, set_active = (int(i) for i in data.split(","))
            set_active = bool(set_active)
            return ReminderInlineQueryData(task_id=task_id, set_active=set_active)
        
        except ValueError:
            return None
