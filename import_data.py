"""
BitShares.org StakeMachine
Import Old Contracts to Database Upon Initialization
BitShares Management Group Co. Ltd.
"""

# PYBITSHARES MODULES
from bitshares.block import Block

# STAKEBTS MODULES
from dev_auth import KEYS
from preexisting_contracts import LEGACY_AGREEMENTS, MANUAL_PAYOUT_CODES
from stake_bitshares import check_block
from utilities import sql_db

# USER DEFINED CONSTANTS
JUNE30 = 1625011200000
JULY31 = 1627689600000
AUG31 = 1630411200000
BLOCK0 = 1445838432000  # assuming perfect blocktime, calculated Aug 7, 2021


def convert_munix_to_block(munix):
    """
    approximate a blocktime given a millesecond unix timestamp, eg:
    NOTE: bitshares block is 3 seconds
    blocktime           btime unix     irr block
    2021-08-07T11:45:39 = 1628336739 = 60832769
    60832769 * 3 = 182498307 seconds
    T0 = 1628336739 - 182498307 = 1445838432
    unix - T0 / 3 = block number
    :param int(munix): timestamp in milleseconds since epoch
    :return int(): block number
    """
    # FIXME this may be 1800 blocks (2 hours) off?
    # this could be mastered gradient descent heuristic
    return int((int(munix) / 1000 - BLOCK0 / 1000) / 3)


def mark_prepaid_stakes():
    """
    make database changes to mark payments prepaid as "paid" with appropriate munix
    :param matrix(stake_matrix): text database converted to python list of lists
    :param object(con): database connection
    :return None:
    """
    # SECURITY: this process must be manually audited prior to 1st live bot start
    # search through our MANUAL_PAYOUT_CODES dict for a list of payments already made
    # extract the user name and list of payout codes of manual payments executed
    for nominator, payout_codes in MANUAL_PAYOUT_CODES.items():
        # for each payout code associated with this nominator
        # apply a custom payout that must be accounted for through database audit
        # failure to account for a manual payout can result in double spend
        for code in payout_codes:
            # handle two last minute payments on august 31st for sune-3355 and bts-stakeacc
            if code == 0:
                block = convert_munix_to_block(AUG31)
                query = """
                    UPDATE stakes
                    SET status='paid', block_processed=?, processed=?
                    WHERE nominator=? AND type='reward' AND status='pending'
                    AND number='1'
                """
                values = (block, AUG31, nominator)
                sql_db(query, values)
            # handle cases where only JULY31 payment has been sent already
            if code == 1:
                block = convert_munix_to_block(JULY31)
                query = """
                    UPDATE stakes
                    SET status='paid', block_processed=?, processed=?
                    WHERE nominator=? AND type='reward' AND status='pending'
                    AND number='1'
                """
                values = (block, JULY31, nominator)
                sql_db(query, values)
            # handle cases where JUNE30 and JULY31 payments have been sent
            if code == 2:
                block = convert_munix_to_block(JUNE30)
                query = """
                    UPDATE stakes
                    SET status='paid', block_processed=?, processed=?
                    WHERE nominator=? AND type='reward' AND status='pending'
                    AND number='1'
                """
                values = (block, JUNE30, nominator)
                sql_db(query, values)
                block = convert_munix_to_block(JULY31)
                query = """
                    UPDATE stakes
                    SET status='paid', block_processed=?, processed=?
                    WHERE nominator=? AND type='reward' AND status='pending'
                    AND number='2'
                """
                values = (block, JULY31, nominator)
                sql_db(query, values)


def load_agreements():
    """
    There are several blocks known to contain legacy agreements, replay by individual
    Add them to the database
    """
    # SECURITY: this process must be manually audited prior to 1st live bot start
    # failure to include a correct legacy agreement block number
    # can result in failed payout to that nominator
    for block_num in LEGACY_AGREEMENTS:
        print("\nINSERT nominator request in block", block_num, "\n")
        for num in range(block_num - 2, block_num + 3):
            print(num)
            block = Block(num)
            Block.clear_cache()
            check_block(num, block, KEYS)


def initialize_database_with_existing_agreements():
    """
    primary event loop to initialize the database with existing agreements
    :return None:
    """
    print("WARN: this script is single use to setup database with legacy agreements")
    print("it will input legacy contracts to database, and mark manual payouts paid")
    choice = input("\ny + Enter to continue, or just Enter to abort\n")
    if choice == "y":
        # replay blocks known to contain legacy agreements
        load_agreements()
        # mark payouts already made as paid
        mark_prepaid_stakes()
        # display results
        query = "SELECT * from stakes"
        print(sql_db(query))


if __name__ == "__main__":

    initialize_database_with_existing_agreements()
