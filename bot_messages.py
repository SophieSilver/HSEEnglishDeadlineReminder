GREETING = """Welcome to the SmartLMS English Reminder Bot!

I am a bot created to remind you of your English deadlines in SmartLMS and notify you when new tasks appear. By default I will remind you about all tasks every 24 hours but you can change it if you want.
Type /help to see the list of commands.

<i>Created by @SophieMore</i>
"""
HELP = """List of commands:
/start -- start receiving reminders.

/help -- see the list of commands.

/set_remind_interval -- set the time between reminders, format: X days Y hours Z minutes.
example: "/set_remind_interval 5 days".

/stop -- stop receiving reminders.
"""
UNKNOWN = "Command unrecognized.\nType /help to see the list of commands."
ERROR = "Sorry, something went wrong."

REMINDERS_ALREADY_FMT = "Reminders are already {0}."
REMINDERS_TURNED_FMT = "Reminders are now turned {0}."

INTERVAL_NO_ARGS = "Error: No interval was given."
INTERVAL_IS_NONE = "Error: Could not parse the given interval.\nPlease follow the format: X days Y hours Z minutes"
INTERVAL_LESS_THAN_SECONDS_FMT = "Error: Remind interval should be longer than {0} seconds."

INTERVAL_CHANGED_FMT = "Your remind interval has been successfully changed to: {0}."

REMINDER_FMT = """You have a <b>{0}</b>
<b>{1}</b>
Due on <b>{2}</b>
Time remaining: <b>{3}</b>

New SmartLMS link: https://smartedu.hse.ru/mod/{4}/{5}

Old SmartLMS link: https://edu.hse.ru/mod/{4}/view.php?id={5}
"""

TURN_REMINDER_OFF = "Do not remind about that"
TURN_REMINDER_ON = "Turn reminders back on"

REMINDER_TURNED_OFF_FMT = "Will no longer remind about <b>{0}</b>."
REMINDER_TURNED_ON_FMT = "Reminders for <b>{0}</b> have been turned on"
