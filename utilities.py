"""
BitShares.org StakeMachine
Shared Utility Functions
BitShares Management Group Co. Ltd.
"""

# DISABLE SELECT PYLINT TESTS
# pylint: disable=broad-except, bad-continuation, invalid-name

# STANDARD PYTHON MODULES
import datetime
import inspect
import time
from sqlite3 import connect as sql

# STAKE BTS MODULES
from config import DB


def it(style, text, foreground=True):
    """
    Color printing in terminal
    """
    lie = 4
    if foreground:
        lie = 3
    if isinstance(style, tuple):  # RGB
        return f"\033[{lie}8;2;{style[0]};{style[1]};{style[2]}m{str(text)}\033[0;00m"
    if isinstance(style, int):  # xterm-256
        return f"\033[{lie}8;5;{style}m{str(text)}\033[0;00m"
    # 6 color emphasis dict
    emphasis = {
        "red": 91,
        "green": 92,
        "yellow": 93,
        "blue": 94,
        "purple": 95,
        "cyan": 96,
    }
    return f"\033[{emphasis[style]}m{str(text)}\033[0m"


def convert_munix_to_date(munix, fstring="%m/%d/%Y"):
    """
    convert from millesecond epoch to human readable UTC timestamp
    :param int(munix): milleseconds since epoch
    :param str(fstring): format of readable date
    :return str(date): human readable date in UTC zone
    """
    return (
        datetime.datetime.utcfromtimestamp(munix / 1000)
        .strftime(fstring)
        .replace("01/01/1970", "00/00/0000")
    )


def convert_date_to_munix(date, fstring="%m/%d/%Y %H:%M"):
    """
    convert from human readable to millesecond epoch
    not used by this app because our data is already in millesecond epoch
    :param str(date): human readable date
    :param str(fstring): format of readable date
    :return int(): millesecond unix epoch
    """
    date_time_obj = datetime.datetime.strptime(date, fstring)
    return int(date_time_obj.timestamp() * 1000)


def munix_nonce():
    """
    SECURITY, mandatory increment when creating a nonce for a new stake
    :return int(): unique ascending millesecond unix time stamp
    """

    def munix():
        """
        :return int(): millesecond unix time stamp
        """
        return int(1000 * time.time())

    now = munix()
    while munix() == now:
        time.sleep(0.0005)  # should result in 1-2 iterations
    return munix()


def line_info():
    """
    :return str(): red formatted function and line number
    """
    info = inspect.getframeinfo(inspect.stack()[1][0])
    return it("red", "function " + str(info.function) + " line " + str(info.lineno))


def exception_handler(error):
    """
    :return str(): red formatted error name and args
    """
    return it("red", f"{type(error).__name__} {error.args}")


def sql_db(query, values=()):
    """
    execute discrete sql queries, handle race condition gracefully
    if query is a string, assume values is a tuple
    else, query can be a list of dicts with keys ["query","values"]

    :return None: when not a SELECT query
    :return cur.fetchall(): from single SELECT, or last SELECT query made
    """
    queries = []
    if isinstance(query, str):
        queries.append({"query": query, "values": values})
    else:
        queries = query

    for dml in queries:
        # do not print sql when updating block number, selecting, or status=processing
        if (
            "UPDATE block_num" not in dml["query"]
            and "SELECT" not in dml["query"]
            and "SET status='processing'" not in dml["query"]
            and "WHERE type='penalty' AND due<?" not in dml["query"]
        ):
            print(it("yellow", f"'query': {dml['query']}"))
            print(it("green", f"'values': {dml['values']}\n"))

    pause = 0
    curfetchall = None
    while True:
        try:
            con = sql(DB)
            cur = con.cursor()
            for dml in queries:
                cur.execute(dml["query"], dml["values"])
                if "SELECT" in dml["query"] or "PRAGMA table_info" in dml["query"]:
                    curfetchall = cur.fetchall()
            con.commit()
            break
        # OperationalError: database is locked
        except Exception as error:
            print(exception_handler(error), line_info())
            time.sleep(0.1 * 2 ** pause)
            if pause < 13:  # oddly works out to about 13 minutes
                pause += 1
            continue
    con.close()
    return curfetchall
