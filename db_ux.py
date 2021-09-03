"""
BitShares.org StakeMachine
Pretty Print Database Contents
BitShares Management Group Co. Ltd.
"""

# STANDARD PYTHON MODULES
import datetime

# STAKE BTS MODULES
from utilities import sql_db
from rpc import get_block_num_current
from stake_bitshares import get_block_num_database


def convert_munix_to_date(munix, fstring="%m/%d/%Y"):
    """
    convert from millesecond epoch to human readable UTC timestamp
    :param int(munix): milleseconds since epoch
    :param str(fstring): format of readable date
    :return str(date): human readable date in UTC zone
    """
    return datetime.datetime.utcfromtimestamp(munix/1000).strftime(fstring).replace("01/01/1970","00/00/0000")


def read_stakes():
    """
    print the contents of the stakes table
    """
    query = """
        SELECT * FROM stakes
        ORDER BY block_start, trx_idx, ops_idx, number, type ASC
    """
    curfetchall = sql_db(query)

    stakes = []
    for stake in curfetchall:
        row = {
            "nonce" : stake[4],
            "client" : stake[0],
            "token" : stake[1],
            "amount" : stake[2],
            "type" : stake[3],
            "start" : convert_munix_to_date(stake[4]),
            "due" : convert_munix_to_date(stake[5]),
            "processed" : convert_munix_to_date(stake[6]),
            "status" : stake[7],
            "block_start" : stake[8],
            "trx_idx" : stake[9],
            "ops_idx" : stake[10],
            "block_proc" : stake[11],
            "number" : stake[12],
        }
        stakes.append(row)

    header = ""
    for key in stakes[0].keys():
        header += str(key).ljust(16)
    print(header)

    for stake in stakes:
        data = ""
        for val in stake.values():
            data += str(val).ljust(16)
        print(data)

def read_receipts():
    """
    print the contents of the receipts table
    """
    query = "SELECT * FROM receipts ORDER BY now, nonce ASC"
    curfetchall = sql_db(query)

    receipts = []
    for receipt in curfetchall:
        row = {
            "date" : convert_munix_to_date(receipt[1]),
            "nonce" : receipt[0],
            "receipt" : receipt[2],
        }
        receipts.append(row)

    print("\n\n")

    header = ""
    for key in receipts[0].keys():
        header += str(key).ljust(16)
    print(header)

    for receipt in receipts:
        data = ""
        for val in receipt.values():
            data += str(val).ljust(16)
        print(data)

def main():
    """
    display database in human readable manner
    """
    print("\033c")
    read_stakes()
    read_receipts()
    print("")
    print("block num database: ", get_block_num_database())
    print("block num current:  ", get_block_num_current())

if __name__ == "__main__":
    main()
