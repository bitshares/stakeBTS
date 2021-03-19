"""
portfolio_management_bot
"""

# STANDARD PYTHON MODULES
from apscheduler.schedulers.background import BackgroundScheduler
from time import sleep
import time
from pprint import pprint
from getpass import getpass
from traceback import format_exc
from json import loads as json_load
from sqlite3 import connect as sqlite3_connect
from decimal import Decimal

# PYBITSHARES MODULES
# temporary disable pylint check for pybitshares modules:
# pylint: disable=import-error, no-name-in-module
from bitshares.account import Account
from bitshares.block import Block
from bitshares.asset import Asset
from bitshares import BitShares
from bitshares.memo import Memo

# USER INPUTS
ACCOUNT_WATCHING = "dao-street"
MINIMUM_ACCOUNT_BALANCE = 50
DAY_PAYOUT = 0.000009
WEEK_PAYOUT = 0.000061
MONTH_PAYOUT = 0.00025
DAILY_STAKE_DELAY = 1 #86400
WEEKLY_STAKE_DELAY = 1 #604800
MONTHLY_STAKE_DELAY = 1 #2628000
CANCEL_AMOUNT = 1


scheduler = BackgroundScheduler()
scheduler.start()


def add_jobs(password):
    """
    Function to add jobs to apscheduler. These are payout jobs.
    """
    scheduler.add_job(payout_daily_stake, trigger='cron', args=[password], hour='*')
    scheduler.add_job(payout_weekly_stake, trigger='cron', args=[password], hour='*/2')
    scheduler.add_job(payout_monthly_stake, trigger='cron', args=[password], hour='*/6')
    #scheduler.add_job(
    #    payout_daily_stake,
    #    trigger='cron',
    #    args=[password],
    #    day='*',
    #    hour='0',
    #   minute='1'
    #)
    #scheduler.add_job(
    #    payout_weekly_stake,
    #    trigger='cron',
    #    args=[password],
    #    day_of_week='mon',
    #    hour='0',
    #    minute='1'
    #)
    #scheduler.add_job(
    #    payout_monthly_stake,
    #    trigger='cron',
    #    args=[password],
    #    month='*',
    #    day='1',
    #    hour='0',
    #    minute='1'
    #)


# USER DEFINED NODE WHITELIST
def public_nodes():
    """
    User defined list of whitelisted public RPC nodes
    """
    return [
        "wss://api.bitsharesdex.com",
        "wss://chicago.bitshares.apasia.tech/ws",
        "wss://sg.nodes.bitshares.ws",
        "wss://status200.bitshares.apasia.tech/ws",
        "wss://dallas.bitshares.apasia.tech/ws",
    ]


def payout_database_entry(valid_stakes):
    """
    Function to input all payouts into the payout table
    """
    portfolio_db = database_connection()
    cursor = portfolio_db.cursor()
    while True:
        for stake in valid_stakes:
            try:
                with portfolio_db:
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
    portfolio_db.commit()


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
                "BTS",
                memo="{} payout of {} BTS for stake {} BTS.".format(
                    stake["stake_length"],
                    stake["payout_amount"],
                    stake["stake_amount"]
                ),
                account=ACCOUNT_WATCHING
            )
            bitshares.wallet.lock()
            bitshares.clear_cache()
        except BaseException as err:
            handle_error(err, "ERROR TRANSFERING PAYOUT.")
        pprint("Transferred stake payout.")


def payout_daily_stake(password):    
    portfolio_db = database_connection()
    cursor = portfolio_db.cursor()
    current_time = time.time()
    cursor.execute(
        "SELECT blockid, user, asset, stakevalidtime, amount " +
        "FROM stakes WHERE stakelength='day'"
    )
    daily_stakes = cursor.fetchall()
    valid_stakes = []
    for stake in daily_stakes:
        if stake[3] < current_time:
            payout_amount = get_payout_amount(float(stake[4]), DAY_PAYOUT)
            valid_stakes.append({
                "recipient": stake[1],
                "stake_amount": stake[4],
                "stake_length": "day",
                "payout_amount": payout_amount,
                "block_id": stake[0],
                "timestamp": current_time,
            })
    pprint("Triggering {} daily stakes.".format(len(valid_stakes)))
    payout_database_entry(valid_stakes)
    payout_transfer(valid_stakes, password)

    
def payout_weekly_stake(password):
    portfolio_db = database_connection()
    cursor = portfolio_db.cursor()
    current_time = time.time()
    cursor.execute(
        "SELECT blockid, user, asset, stakevalidtime, amount " +
        "FROM stakes WHERE stakelength='week'"
    )
    weekly_stakes = cursor.fetchall()
    valid_stakes = []
    for stake in weekly_stakes:
        if stake[3] < current_time:
            payout_amount = get_payout_amount(float(stake[4]), WEEK_PAYOUT)
            valid_stakes.append({
                "recipient": stake[1],
                "stake_amount": stake[4],
                "stake_length": "week",
                "payout_amount": payout_amount,
                "block_id": stake[0],
                "timestamp": current_time,
            })
    pprint("Triggering {} weekly stakes.".format(len(valid_stakes)))
    payout_database_entry(valid_stakes)
    payout_transfer(valid_stakes, password)
    
    
def payout_monthly_stake(password):
    portfolio_db = database_connection()
    cursor = portfolio_db.cursor()
    current_time = time.time()
    cursor.execute(
        "SELECT blockid, user, asset, stakevalidtime, amount " +
        "FROM stakes WHERE stakelength='month'"
    )
    monthly_stakes = cursor.fetchall()
    valid_stakes = []
    for stake in monthly_stakes:
        if stake[3] < current_time:
            payout_amount = get_payout_amount(float(stake[4]), MONTH_PAYOUT)
            valid_stakes.append({
                "recipient": stake[1],
                "stake_amount": stake[4],
                "stake_length": "month",
                "payout_amount": payout_amount,
                "block_id": stake[0],
                "timestamp": current_time,
            })
    pprint("Triggering {} monthly stakes.".format(len(valid_stakes)))
    payout_database_entry(valid_stakes)
    payout_transfer(valid_stakes, password)
    

def stake_organizer(bot, bitshares, portfolio_db):
    cursor = portfolio_db.cursor()
    add_stake_time = 0
    if bot["length_of_stake"] == "day":
        add_stake_time = DAILY_STAKE_DELAY
    elif bot["length_of_stake"] == "week":
        add_stake_time = WEEKLY_STAKE_DELAY
    elif bot["length_of_stake"] == "month":
        add_stake_time = MONTHLY_STAKE_DELAY
    stake_valid_time = bot["timestamp"] + add_stake_time
    while True and bot["length_of_stake"] != None:
        try:
            with portfolio_db:
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
        handle_error(err, "ERROR TRANSFERING CANCELLED STAKE.")
    pprint("Transferred cancelled stake back.")
    

def remove_stake_entry(account, length):
    current_time = time.time()
    portfolio_db = database_connection()
    cursor = portfolio_db.cursor()
    try:
        cursor.execute(
        "DELETE FROM stakes " +
        "WHERE stakelength='{}' AND user='{}'".\
        format(length, account)
    )
    except BaseException as err:
        handle_error(err, "ERROR REMOVING STAKES FROM DB.")
    portfolio_db.commit()
    pprint("Removed stakes from DB.")
            
            
def cancelled_database_entry(stakes_to_cancel):
    current_time = time.time()
    portfolio_db = database_connection()
    cursor = portfolio_db.cursor()
    while True:
        for stake in stakes_to_cancel:
            try:
                with portfolio_db:
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
    portfolio_db.commit()
    pprint("Entered cancelled stakes into database.")
            
            
def cancel_stake(bot):
    print("STAKE {} SHOULD BE CANCELLED FOR {}.".format(bot["stop_length"], bot["payor"]))
    portfolio_db = database_connection()
    cursor = portfolio_db.cursor()
    cursor.execute(
        "SELECT * FROM stakes " +
        "WHERE stakelength='{}' AND user='{}'".\
        format(bot["stop_length"], bot["payor"])
    )
    stakes_to_cancel = cursor.fetchall()
    cancelled_database_entry(stakes_to_cancel)
    remove_stake_entry(bot["payor"], bot["stop_length"])
    cancelled_transfer_amount = 0
    for stake in stakes_to_cancel:
        cancelled_transfer_amount += stake[7]
    transfer_cancelled_stake(bot, cancelled_transfer_amount)
    portfolio_db.commit()
            

def check_block(bitshares, memo, bot, portfolio_db, block):
    """
    Check the block for incoming transactions to bot
    """
    for trxs in block["transactions"]:
        for operation, trx in enumerate(trxs["operations"]):
            if trx[0] == 0 and Account(trx[1]["to"]).name == ACCOUNT_WATCHING:
                bot["payor"] = Account(trx[1]["from"]).name
                bot["asset_type"] = str(trx[1]["amount"]["asset_id"])
                asset_precision = Asset(bot["asset_type"]).precision
                bot["amount"] = int(trx[1]["amount"]["amount"]) / (10 ** (asset_precision))
                Account.clear_cache()
                Asset.clear_cache()
                bot = get_json_memo(memo, bot, trx)
                if bot["asset_type"] != "1.3.0":
                    try:
                        bitshares.wallet.unlock(bot["password"])
                        bitshares.transfer(
                            bot["payor"],
                            bot["amount"],
                            bot["asset_type"],
                            memo="Incorrect asset type.",
                            account=ACCOUNT_WATCHING
                        )
                        bitshares.wallet.lock()
                        bitshares.clear_cache()
                    except BaseException as err:
                        handle_error(err, "ERROR TRANSFERING INCORRECT ASSET BACK.")
                elif bot["length_of_stake"] == None:
                    try:
                        bitshares.wallet.unlock(bot["password"])
                        bitshares.transfer(
                            bot["payor"],
                            bot["amount"],
                            bot["asset_type"],
                            memo="Incorrect memo format.",
                            account=ACCOUNT_WATCHING
                        )
                        bitshares.wallet.lock()
                        bitshares.clear_cache()
                    except BaseException as err:
                        handle_error(err, "ERROR TRANSFERING INCORRECT MEMO BACK.")
                elif bot["length_of_stake"] != "funding" \
                    and bot["length_of_stake"] != "stop" \
                    and bot["length_of_stake"] != None:
                    
                    bot["block_id"] = "{}.{}".format(
                        bot["block_num"], str(operation))
                    bot["timestamp"] = time.time()
                    pprint("New stake.")
                    stake_organizer(bot, bitshares, portfolio_db)
                elif bot["length_of_stake"] == "stop" and bot["amount"] == CANCEL_AMOUNT:
                    cancel_stake(bot)
    bot["block_num"] += 1


def scan_chain(bitshares, memo, bot, portfolio_db):
    """
    Get block number and check for validity
    """
    cursor = portfolio_db.cursor()
    cursor.execute("SELECT blockheight FROM last_check")
    blockheight = cursor.fetchall()
    start_block = blockheight[0][0]
    bot["block_num"] = start_block
    while True:
        pprint("Trying block: {}".format(bot["block_num"]))
        try:
            block = Block(bot["block_num"])
            Block.clear_cache()
        except BaseException:
            block = None
        if block is not None:
            check_block(bitshares, memo, bot, portfolio_db, block)
        else:
            pprint("No such block yet: {}".format(bot["block_num"]))
            break
    try:
        with portfolio_db:
            cursor.execute(
                "UPDATE last_check SET blockheight=?", (bot["block_num"],)
            )
    except BaseException as err:
        handle_error(err, "ERROR UPDATING BLOCKHEIGHT.")
    portfolio_db.commit()
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
                if json_memo["type"].lower() == "day":
                 bot["length_of_stake"] = "day"
                elif json_memo["type"].lower() == "week":
                    bot["length_of_stake"] = "week"
                elif json_memo["type"].lower() == "month":
                    bot["length_of_stake"] = "month"
                elif json_memo["type"].lower() == "funding":
                    bot["length_of_stake"] = "funding"
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
    Create a fresh connection to bishares, and memo objects
    """
    bitshares = BitShares(node=public_nodes(), nobroadcast=False)
    memo = Memo(node=public_nodes())

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
    return sqlite3_connect("portfolioDB.db")


def account_balance_check():
    """
    Self contained function that closes program
    if the account balance is lower than specified
    """
    account_balance = Account(ACCOUNT_WATCHING).balance("BTS")
    Account.clear_cache()
    if account_balance < MINIMUM_ACCOUNT_BALANCE:
        pprint(
            "Bot does not have necessary funds to continue. " +
            "Adjust minimum balance or add funds to bot."
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
    bot = {}
    bot["password"] = getpass("Input WALLET PASSWORD and press ENTER: ")
    portfolio_db = database_connection()
    block_stall = 0
    last_block = 0
    add_jobs(bot["password"])
    try:
        while True:
            bitshares, memo = reconnect()
            account_balance_check()
            block = scan_chain(bitshares, memo, bot, portfolio_db)
            if block == last_block:
                block_stall += 1
                print("Blockstall: {}".format(block_stall))
            else:
                block_stall = 0
                last_block = block
            if block_stall > 50:
                exit()
            sleep(6)
    except KeyboardInterrupt:
        try:
            pprint("Keyboard interrupt. Exiting")
        except BaseException:
            exit(0)
    portfolio_db.close()
    pprint("DB connection closed.")    
    

if __name__ == "__main__":

    main()
