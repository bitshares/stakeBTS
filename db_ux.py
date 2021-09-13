"""
BitShares.org StakeMachine
Pretty Print Database Contents
BitShares Management Group Co. Ltd.
"""

# STANDARD PYTHON MODULES
from rpc import get_block_num_current
from stake_bitshares import get_block_num_database
# STAKE BTS MODULES
from utilities import convert_munix_to_date, sql_db


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
            "nominator": stake[0],
            "digital_asset": stake[1],
            "amount": stake[2],
            "type": stake[3],
            "nonce": stake[4],
            "start": convert_munix_to_date(stake[5]),
            "due": convert_munix_to_date(stake[6]),
            "processed": convert_munix_to_date(stake[7]),
            "status": stake[8],
            "block_start": stake[9],
            "trx_idx": stake[10],
            "ops_idx": stake[11],
            "block_proc": stake[12],
            "number": stake[13],
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
            "date": convert_munix_to_date(receipt[1]),
            "nonce": receipt[0],
            "receipt": receipt[2],
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
