"""
BitShares.org StakeMachine
Import Old Contracts to Database Upon Initialization
BitShares Management Group Co. Ltd.
"""

# STANDARD MODULES
from sqlite3 import connect as sql

# PYBITSHARES MODULES
from bitshares.block import Block

# STAKEBTS MODULES
from config import DB
from dev_auth import KEYS
from preexisting_contracts import CONTRACT_BLOCKS, STAKES
from rpc import pybitshares_reconnect
from stake_bitshares import check_block
from utilities import sql_db

# USER DEFINED CONSTANTS
JUNE30 = 1625011200000
JULY31 = 1627689600000
AUG31 = 1630411200000
BLOCK0 = 1445838432000  # assuming perfect blocktime, calculated Aug 7, 2021


def get_dynamic_globals():
    """
    not actually used by this script,
    but allows us to associate a recent block num to unix time for dev
    :return dict():
    """
    bitshares, _ = pybitshares_reconnect()
    print(bitshares.rpc.get_dynamic_global_properties())


def convert_stakes_to_matrix(stakes):
    """
    STAKES is a block of text, we'll need to import that to python list of lists
    data must be in space seperated column format:
    username, munix, amount, term_in_months, months_prepaid
    :param str(stakes): multi-line space delimited text field
    :return matrix [[],[],[],...]:
    """
    return [i.strip().split() for i in stakes.splitlines() if i]


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
    return int((int(munix) / 1000 - BLOCK0 / 1000) / 3)


def add_block_num(stake_matrix):
    """
    our stake matrix has unix timestamps, we'll add approximate block number
    :param matrix(stake_matrix): text database converted to python list of lists
    :return matrix [[],[],[],...]:
    """
    for item, stake in enumerate(stake_matrix):
        stake_matrix[item].append(convert_munix_to_block(stake[1]))
    return stake_matrix


def mark_prepaid_stakes(stake_matrix):
    """
    make database changes to mark payments prepaid as "paid" with appropriate munix
    :param matrix(stake_matrix): text database converted to python list of lists
    :param object(con): database connection
    :return None:
    """
    # search through our prepaid stake matrix for payments already made
    for stake in stake_matrix:
        # extract the user name and number of payments already executed
        nominator = str(stake[0])
        prepaid = int(stake[4])
        # handle two last minute payments on august 31st for sune-3355 and bts-stakeacc
        if prepaid == 0:
            block = convert_munix_to_block(AUG31)
            query = (
                "UPDATE stakes "
                + "SET status='paid', block_processed=?, processed=? "
                + "WHERE nominator=? AND type='reward' AND status='pending' "
                + "AND number='1'"
            )
            values = (block, AUG31, nominator)
            sql_db(query, values)
        # handle cases where one payment has been sent already
        if prepaid == 1:
            block = convert_munix_to_block(JULY31)
            query = (
                "UPDATE stakes "
                + "SET status='paid', block_processed=?, processed=? "
                + "WHERE nominator=? AND type='reward' AND status='pending' "
                + "AND number='1'"
            )
            values = (block, JULY31, nominator)
            sql_db(query, values)
        # handle cases where two payments have been sent already
        if prepaid == 2:
            block = convert_munix_to_block(JUNE30)
            query = (
                "UPDATE stakes "
                + "SET status='paid', block_processed=?, processed=? "
                + "WHERE nominator=? AND type='reward' AND status='pending' "
                + "AND number='1'"
            )
            values = (block, JUNE30, nominator)
            sql_db(query, values)
            block = convert_munix_to_block(JULY31)
            query = (
                "UPDATE stakes "
                + "SET status='paid', block_processed=?, processed=? "
                + "WHERE nominator=? AND type='reward' AND status='pending' "
                + "AND number='2'"
            )
            values = (block, JULY31, nominator)
            sql_db(query, values)


def load_agreements():
    """
    There are several blocks known to contain legacy agreements, replay by individual
    Add them to the database
    """
    for block_num in CONTRACT_BLOCKS:
        print("\nINSERT nominator request in block", block_num, "\n")
        for num in range(block_num-2, block_num+3):
            print(num)
            block = Block(num)
            Block.clear_cache()
            check_block(num, block, KEYS)


def initialize_database_with_existing_agreements():
    """
    primary event loop to initialize the database with existing agreements
    :return None:
    """
    # replay blocks known to contain legacy agreements
    load_agreements()
    # convert text block to a matrix
    stake_matrix = convert_stakes_to_matrix(STAKES)
    # add block number to each row in matrix
    stake_matrix = add_block_num(stake_matrix)
    # mark payouts already made as paid
    mark_prepaid_stakes(stake_matrix)
    # display results
    query = "SELECT * from stakes;"
    print(sql_db(query))


if __name__ == "__main__":

    print("WARN: this script is single use to setup database with legacy agreements")
    print("it will input legacy contracts to database, and mark manual payouts paid")
    choice = input("\ny + Enter to continue, or just Enter to abort\n")
    if choice == "y":
        initialize_database_with_existing_agreements()
