"""
BitShares.org StakeMachine
Pretty Print Database Contents
BitShares Management Group Co. Ltd.
"""
# STANDARD PYTHON MODULES
import time

# STAKE BTS MODULES
from config import CUSTODIAN, LOGO, COLOR
from rpc import get_block_num_current, get_balance_pybitshares
from stake_bitshares import get_block_num_database
from utilities import convert_munix_to_date, it, sql_db


def read_stakes():
    """
    print the contents of the stakes table
    """
    print(
            it("yellow", LOGO)
            + it(COLOR[0], f"     {time.ctime().upper()}")
            + it(COLOR[1], f"     {int(time.time()/60)*60000}")
            + it("yellow", f"     {CUSTODIAN.upper()}     ")
    )
    print(it("yellow", "=======================\nDATABASE EXPLORER\n"))

    query = """
        SELECT * FROM stakes
        ORDER BY block_start, trx_idx, ops_idx, number, type ASC
    """
    curfetchall = sql_db(query)

    stakes = []
    for stake in curfetchall:
        row = {
            "nominator": stake[0],
            "digital_asset": stake[1],
            "amount": stake[2],
            "type": stake[3],
            "nonce": stake[4],
            "start": convert_munix_to_date(stake[5], fstring="%m/%d/%Y"),
            "due": convert_munix_to_date(stake[6], fstring="%m/%d/%Y"),
            "processed": convert_munix_to_date(stake[7], fstring="%m/%d/%Y"),
            "status": stake[8],
            "block_start": stake[9],
            "trx_idx": stake[10],
            "ops_idx": stake[11],
            "block_proc": stake[12],
            "number": stake[13],
        }
        stakes.append(row)
    print(it(COLOR[2], f"Stakes Table\n===========================".upper()))
    if stakes:
        header = ""
        for key in stakes[0].keys():
            header += str(key).ljust(16).upper()
        print(it("green", header), "\n")
        for stake in stakes:
            data = ""
            for val in stake.values():
                datum = str(val).ljust(16)
                # highlight items
                if val == "confirmed":
                    datum = it("green", datum)
                elif val == "paid":
                    datum = it("yellow", datum)
                elif val == "pending":
                    pass
                elif val == "aborted":
                    datum = it(COLOR[3], datum)
                # highlight rows
                elif "reward" in stake.values():
                    datum = it(COLOR[1], datum)
                elif "penalty" in stake.values():
                    datum = it(COLOR[0], datum)
                data += datum
            print(data)


def read_receipts():
    """
    print the contents of the receipts table
    """
    # query db and assign to human readable dict
    query = "SELECT * FROM receipts ORDER BY now, nonce ASC"
    curfetchall = sql_db(query)
    receipts = []
    for receipt in curfetchall:
        row = {
            "date": convert_munix_to_date(receipt[1], fstring="%Y/%m/%d %H:%M"),
            "nonce": receipt[0],
            "receipt": receipt[2],
        }
        receipts.append(row)
    # provide ux for receipts
    print(it(COLOR[2], f"\nReceipts Table\n===========================".upper()))
    if receipts:
        # column names
        header = ""
        for key in receipts[0].keys():
            header += str(key).ljust(18).upper()
        print(it("green", header), "\n")
        # row data
        for receipt in receipts:
            data = ""
            for idx, val in enumerate(receipt.values()):
                formatted = str(val).ljust(18)
                # highlight items
                if "response" in str(val):
                    formatted = it(COLOR[3], formatted)
                # highlight items
                elif "balances" in str(val):
                    formatted = it(COLOR[4], formatted)
                # highlight items
                elif "serve_admin" in str(val):
                    formatted = it("green", formatted)
                # highlight items
                elif "initialize" in str(val):
                    formatted = it("purple", formatted)
                # highlight columns
                elif idx == 1:
                    formatted = it(COLOR[2], formatted)
                elif idx == 0:
                    formatted = it(COLOR[4], formatted)

                data += formatted
            print(data, "\n")


def main():
    """
    display database in human readable manner
    """
    while True:
        print("\033c")
        read_stakes()
        read_receipts()
        print("connecting to wallet for account balance...\n")
        print(
            it("yellow", "=================================\n")
            + it(COLOR[2], f"db block   : {get_block_num_database()}\n")
            + it(COLOR[3], f"irr block  : {get_block_num_current()}\n")
            + it(COLOR[4], f"hot wallet : {get_balance_pybitshares()}\n")
            + it("yellow", "=================================\n")
        )
        input("press Enter to refresh\n\n\n")


if __name__ == "__main__":
    main()
