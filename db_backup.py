"""
BitShares.org StakeMachine
Periodically Backup the stake_bisthares.db sqlite Database
BitShares Management Group Co. Ltd.
"""
# STANDARD PYTHON MODULES
import os
import subprocess
import time

# STAKE BITSHARES MODULES
from utilities import convert_munix_to_date


def db_backup():
    """
    copy the database to a subfolder
    database/backup/year/month/day.hour.min.stake_bitshares.db
    """
    # refresh rate, subfolder path, and source database file name
    wait = 14400
    subfolder = "/database/"
    database = "stake_bitshares.db"
    # get the current file location
    path = os.path.dirname(os.path.abspath(__file__)) + subfolder
    source = path + database
    while True:
        # extract year, month, day, hour, and min from system time in milleseconds
        now = convert_munix_to_date(
            int(time.time() * 1000), fstring="%Y %m %d %H %M"
        ).split()
        # timestamp the file path with year and month
        destination = path + f"backup/{now[0]}/{now[1]}/"
        # make sure the backup/year/month folder exists
        os.makedirs(destination, exist_ok=True)
        # timestamp the database filename with day.hour.min
        destination += f"{now[2]}.{now[3]}.{now[4]}." + database
        # linux terminal copy file command
        command = ["cp", source, destination]
        print("BACKUP DATABASE TO", command[2])
        subprocess.call(command)
        time.sleep(wait)


if __name__ == "__main__":

    db_backup()
