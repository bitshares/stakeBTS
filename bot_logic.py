"""
BitShares.org StakeMachine
Interest Payment on Investment for
BitShares Management Group Co. Ltd.
"""

from apscheduler.schedulers.background import BackgroundScheduler
import time
from pprint import pprint
from getpass import getpass
from traceback import format_exc
from json import loads as json_load
from sqlite3 import connect as sqlite3_connect
from decimal import Decimal

from bitshares.account import Account
from bitshares.block import Block
from bitshares.asset import Asset
from bitshares.bitshares import BitShares
from bitshares.memo import Memo
from bitshares.instance import set_shared_bitshares_instance

# USER INPUTS
ACCOUNT_WATCHING = "dont-know"
MINIMUM_ACCOUNT_BALANCE = 50
TEN_PAYOUT = 0.015
TWENTY_PAYOUT = 0.025
FIFTY_PAYOUT = 0.055
CANCEL_AMOUNT = 1

THREE_BLOCK_MONTHS = 2592000  # blocks per 3 months
SIX_BLOCK_MONTHS = 5184000  # blocks per 6 months

scheduler = BackgroundScheduler()
scheduler.start()


def add_jobs(password):
    """
    Function to add jobs to apscheduler. These are payout jobs.
    """
    scheduler.add_job(payout_weekly_stake, trigger='cron', args=[password], minute='*')


# USER DEFINED NODE WHITELIST
def public_nodes():
    """
    User defined list of whitelisted public RPC nodes
    """
    return [
        "wss://api.iamredbar.com/ws",
    ]


def payout_database_entry(valid_stakes):
    """
    Function to input all payouts into the payout table
    """
    investment_db = database_connection()
    cursor = investment_db.cursor()
    while True:
        for stake in valid_stakes:
            try:
                with investment_db:
                    cursor.execute(
                        (
                                "INSERT OR IGNORE INTO payouts " +
                                "(blockid, account, stakeamount, " +
                                "stakelength, payoutamount, timestamp) " +
                                "VALUES (?,?,?,?,?,?)"
                        ),
                        (
                            stake["block_id"],
                            stake["recipient"],
                            stake["stake_amount"],
                            stake["stake_length"],
                            stake["payout_amount"],
                            stake["timestamp"]
                        ),
                    )
            except BaseException as err:
                handle_error(err, "ERROR SUBMITTING PAYOUT TO DB")
        pprint("Added payouts to database.")
        break
    investment_db.commit()


def payout_transfer(valid_stakes, password):
    """
    Transfers all valid stakes 
    """
    bitshares, memo = reconnect()
    for stake in valid_stakes:
        try:
            bitshares.wallet.unlock(password)
            bitshares.transfer(
                stake["recipient"],
                stake["payout_amount"],
                'BTS',
                memo=f'Payout of {stake["payout_amount"]} BTS',
                account=ACCOUNT_WATCHING
            )
            bitshares.wallet.lock()
            bitshares.clear_cache()
        except BaseException as err:
            handle_error(err, "ERROR TRANSFERRING PAYOUT.")
        pprint("Transferred stake payout.")


def payout_weekly_stake(password):
    investment_db = database_connection()
    cursor = investment_db.cursor()
    current_time = time.time()
    cursor.execute("SELECT blockid, user, asset, stakelength, amount FROM stakes")
    weekly_stakes = cursor.fetchall()
    valid_stakes = []
    for stake in weekly_stakes:
        payout_amount = 0
        if stake[4] == 10000:
            payout_amount = get_payout_amount(float(stake[4]), TEN_PAYOUT)
        elif stake[4] == 20000:
            payout_amount = get_payout_amount(float(stake[4]), TWENTY_PAYOUT)
        elif stake[4] == 50000:
            payout_amount = get_payout_amount(float(stake[4]), FIFTY_PAYOUT)
        valid_stakes.append({
            "recipient": stake[1],
            "stake_amount": stake[4],
            "payout_amount": payout_amount,
            "block_id": stake[0],
            "timestamp": current_time,
        })
    print(f'Triggering {len(valid_stakes)} weekly stakes.')
    payout_database_entry(valid_stakes)
    payout_transfer(valid_stakes, password)


def stake_organizer(bot, investment_db):
    cursor = investment_db.cursor()
    stake_valid_time = bot["timestamp"]
    while True and bot["length_of_stake"] is not None:
        try:
            with investment_db:
                cursor.execute(
                    (
                            "INSERT OR IGNORE INTO stakes " +
                            "(block, blockid, timestamp, user, " +
                            "asset, stakelength, stakevalidtime, amount) " +
                            "VALUES (?,?,?,?,?,?,?,?)"
                    ),
                    (
                        bot["block_num"],
                        bot["block_id"],
                        bot["timestamp"],
                        bot["payor"],
                        bot["asset_type"],
                        bot["length_of_stake"],
                        stake_valid_time,
                        bot["amount"],
                    ),
                )
            break
        except BaseException as err:
            handle_error(err, "ERROR SUBMITTING STAKE TO DB")


def transfer_cancelled_stake(bot, transfer_amount):
    bitshares, memo = reconnect()
    try:
        bitshares.wallet.unlock(bot["password"])
        bitshares.transfer(
            bot["payor"],
            transfer_amount,
            "BTS",
            memo="Return of {} stake. {} BTS returned.".format(
                bot["stop_length"],
                transfer_amount
            ),
            account=ACCOUNT_WATCHING
        )
        bitshares.wallet.lock()
        bitshares.clear_cache()
    except BaseException as err:
        handle_error(err, "ERROR TRANSFERRING CANCELLED STAKE.")
    pprint("Transferred cancelled stake back.")


def remove_stake_entry(account, length):
    investment_db = database_connection()
    cursor = investment_db.cursor()
    try:
        cursor.execute(
            "DELETE FROM stakes " +
            f"WHERE stakelength='{length}' AND user='{account}'"
        )
    except BaseException as err:
        handle_error(err, "ERROR REMOVING STAKES FROM DB.")
    investment_db.commit()
    pprint("Removed stakes from DB.")


def cancelled_database_entry(stakes_to_cancel):
    current_time = time.time()
    investment_db = database_connection()
    cursor = investment_db.cursor()
    while True:
        for stake in stakes_to_cancel:
            try:
                with investment_db:
                    cursor.execute(
                        (
                                "INSERT OR IGNORE INTO cancelledstakes " +
                                "(block, blockid, timestamp, user, " +
                                "asset, stakelength, stakevalidtime, amount, cancelledtime) " +
                                "VALUES (?,?,?,?,?,?,?,?,?)"
                        ),
                        (
                            stake[0],
                            stake[1],
                            stake[2],
                            stake[3],
                            stake[4],
                            stake[5],
                            stake[6],
                            stake[7],
                            current_time,
                        ),
                    )
            except BaseException as err:
                handle_error(err, "ERROR SUBMITTING CANCELS TO DB")
        break
    investment_db.commit()
    pprint("Entered cancelled stakes into database.")


def cancel_stake(bot):
    print('Should be cancelling an investment here...')
    # print("STAKE {} SHOULD BE CANCELLED FOR {}.".format(bot["stop_length"], bot["payor"]))
    # investment_db = database_connection()
    # cursor = investment_db.cursor()
    # cursor.execute(
    #     "SELECT * FROM stakes " +
    #     "WHERE stakelength='{}' AND user='{}'". \
    #     format(bot["stop_length"], bot["payor"])
    # )
    # stakes_to_cancel = cursor.fetchall()
    # cancelled_database_entry(stakes_to_cancel)
    # remove_stake_entry(bot["payor"], bot["stop_length"])
    # cancelled_transfer_amount = 0
    # for stake in stakes_to_cancel:
    #     cancelled_transfer_amount += stake[7]
    # transfer_cancelled_stake(bot, cancelled_transfer_amount)
    # investment_db.commit()


def check_block(memo, bot, investment_db, block):
    """
    Check the block for incoming transactions to bot
    """
    for trxs in block["transactions"]:
        for operation, trx in enumerate(trxs["operations"]):
            if trx[0] == 0 and Account(trx[1]["to"]).name == ACCOUNT_WATCHING:
                bot["payor"] = Account(trx[1]["from"]).name
                bot["asset_type"] = str(trx[1]["amount"]["asset_id"])
                asset_precision = Asset(bot["asset_type"]).precision
                bot["amount"] = int(trx[1]["amount"]["amount"]) / (10 ** asset_precision)
                Account.clear_cache()
                Asset.clear_cache()
                bot = get_json_memo(memo, bot, trx)
                if bot["asset_type"] != "1.3.0":
                    print('Wrong asset transferred.')
                elif bot["length_of_stake"] is None:
                    print('Wrong memo format.')
                elif bot["length_of_stake"] != "funding" \
                        and bot["length_of_stake"] != "stop" \
                        and bot["length_of_stake"] is not None:
                    bot["block_id"] = f'{bot["block_num"]}.{str(operation)}'
                    bot["timestamp"] = time.time()
                    print("New stake")
                    stake_organizer(bot, investment_db)
                elif bot["length_of_stake"] == "stop" and bot["amount"] == CANCEL_AMOUNT:
                    cancel_stake(bot)
    bot["block_num"] += 1


def scan_chain(memo, bot, investment_db):
    """
    Get block number and check for validity
    """
    cursor = investment_db.cursor()
    cursor.execute("SELECT blockheight FROM last_check")
    blockheight = cursor.fetchall()
    start_block = blockheight[0][0]
    bot["block_num"] = start_block
    while True:
        print("Trying block: {}".format(bot["block_num"]))
        try:
            block = Block(bot["block_num"])
            Block.clear_cache()
        except BaseException as e:
            print(e)
            block = None
        if block is not None:
            check_block(memo, bot, investment_db, block)
        else:
            print("No such block yet: {}".format(bot["block_num"]))
            break
    try:
        with investment_db:
            cursor.execute(
                "UPDATE last_check SET blockheight=?", (bot["block_num"],)
            )
    except BaseException as err:
        handle_error(err, "ERROR UPDATING BLOCKHEIGHT.")
    investment_db.commit()
    return bot["block_num"]


def get_json_memo(memo, bot, trx):
    """
    Collect the info from memo and check for validity
    """
    try:
        memo.blockchain.wallet.unlock(bot["password"])
        decrypted_memo = memo.decrypt(trx[1]["memo"])
        memo.blockchain.wallet.lock()
        try:
            json_memo = json_load(decrypted_memo)
            bot["length_of_stake"] = None
            if "type" in json_memo and json_memo != "FAIL":
                if json_memo["type"].lower() == "three_months":
                    bot["length_of_stake"] = "three_months"
                elif json_memo["type"].lower() == "six_months":
                    bot["length_of_stake"] = "six_months"
                elif json_memo["type"].lower() == "stop":
                    bot["length_of_stake"] = "stop"
                    try:
                        if json_memo["length"].lower() == "day":
                            bot["stop_length"] = "day"
                        elif json_memo["length"].lower() == "week":
                            bot["stop_length"] = "week"
                        elif json_memo["length"].lower() == "month":
                            bot["stop_length"] = "month"
                        else:
                            bot["length_of_stake"] = None
                    except BaseException as err:
                        bot["length_of_stake"] = None
                        handle_error(err, "INCORRECT JSON FORMAT")
        except Exception as err:
            bot["length_of_stake"] = None
            handle_error(err, "JSON ERROR.")
    except Exception as err:
        bot["length_of_stake"] = None
        handle_error(err, "MEMO ERROR")
    return bot


# HELPER FUNCTIONS
def reconnect():
    """
    Create a fresh connection to BitShares, and memo objects
    """
    bitshares = BitShares(node=public_nodes(), nobroadcast=False)
    set_shared_bitshares_instance(bitshares)
    memo = Memo()
    return bitshares, memo


def handle_error(err, err_string):
    """
    Custom error handling, perform stack trace
    """
    print("{}".format(err_string), file=open("logfile.txt", "a"))
    print("Type error: {}".format(str(err)), file=open("logfile.txt", "a"))
    print(format_exc(), file=open("logfile.txt", "a"))


def database_connection():
    """
    Fresh connection to the database.
    """
    return sqlite3_connect('investment.db')


def account_balance_check():
    """
    Self contained function that closes program
    if the account balance is lower than specified
    """
    account_balance = Account(ACCOUNT_WATCHING).balance("BTS")
    Account.clear_cache()
    if account_balance < MINIMUM_ACCOUNT_BALANCE:
        pprint(
            'Bot does not have necessary funds to continue. ' +
            'Adjust minimum balance or add funds to bot.'
        )
        exit()


def get_payout_amount(stake_amount, payout_multiplier):
    """
    Function to always get the correct payout
    """
    unrounded_payout = Decimal(stake_amount * payout_multiplier)
    return float(round(unrounded_payout, 5))


# PRIMARY EVENT BACKBONE

def main():
    """
    Sign in, connect to database, connect to node, and add jobs to queue
    """
    bot = {'password': getpass('Input WALLET PASSWORD and press ENTER: ')}
    investment_db = database_connection()
    block_stall = 0
    last_block = 0
    add_jobs(bot['password'])
    try:
        while True:
            bitshares, memo = reconnect()
            account_balance_check()
            block = scan_chain(memo, bot, investment_db)
            if block == last_block:
                block_stall += 1
                print('Blockstall: {}'.format(block_stall))
            else:
                block_stall = 0
                last_block = block
            if block_stall > 50:
                exit()
            time.sleep(6)
    except KeyboardInterrupt:
        try:
            pprint('Keyboard interrupt. Exiting')
        except BaseException as e:
            print(e)
            exit(0)
    investment_db.close()
    print('DB connection closed.')


if __name__ == '__main__':
    main()
