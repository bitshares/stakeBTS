"""
BitShares.org StakeMachine
Interest Payment on Staking for
BitShares Management Group Co. Ltd.
"""
# Standard imports
from apscheduler.schedulers.background import BackgroundScheduler
import time
from getpass import getpass
from traceback import format_exc
from json import loads as json_load
from sqlite3 import connect as sqlite3_connect
from decimal import Decimal
from sys import exit

# BitShares imports
from bitshares.account import Account
from bitshares.block import Block
from bitshares.asset import Asset
from bitshares.bitshares import BitShares
from bitshares.memo import Memo
from bitshares.instance import set_shared_bitshares_instance

# USER INPUTS
ACCOUNT_WATCHING = "iamredbar2"
NODE = 'wss://testnet.dex.trading/'
STAKING_ASSET = 'TEST'  # 'BTS'
# MAXIMUM_ACCOUNT_BALANCE = 20000
# LOW_INVEST_AMOUNT = 25000
# MID_INVEST_AMOUNT = 50000
# HIGH_INVEST_AMOUNT = 100000
# TOP_INVEST_AMOUNT = 200000
LOW_INVEST_AMOUNT = 25
MID_INVEST_AMOUNT = 50
HIGH_INVEST_AMOUNT = 100
TOP_INVEST_AMOUNT = 200
PAYOUT = 0.08
CANCEL_AMOUNT = 1

THREE_BLOCK_MONTHS = 2592000  # blocks per 3 months
SIX_BLOCK_MONTHS = 5184000  # blocks per 6 months
TWELVE_BLOCK_MONTHS = 5184000 * 2 # blocks per 12 months

scheduler = BackgroundScheduler()
scheduler.start()


def add_jobs(password):
    """
    Function to add jobs to apscheduler. These are payout jobs.
    """
    scheduler.add_job(payout_stake, trigger='cron', args=[password], minute='*/2')


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
        print("Added payouts to database.")
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
                STAKING_ASSET,
                memo=f'Payout of {stake["payout_amount"]} {STAKING_ASSET}',
                account=ACCOUNT_WATCHING
            )
            bitshares.wallet.lock()
            bitshares.clear_cache()
        except BaseException as err:
            handle_error(err, "ERROR TRANSFERRING PAYOUT.")
        print("Transferred stake payout.")


def payout_stake(password):
    investment_db = database_connection()
    cursor = investment_db.cursor()
    current_time = time.time()
    cursor.execute("SELECT blockid, user, asset, stakelength, amount FROM stakes")
    weekly_stakes = cursor.fetchall()
    valid_stakes = []
    for stake in weekly_stakes:
        payout_amount = _get_payout_amount(float(stake[4]), PAYOUT)
        print(f'Payout amount: {payout_amount}')
        valid_stakes.append({
            "recipient": stake[1],
            "stake_amount": stake[4],
            "payout_amount": payout_amount,
            "block_id": stake[0],
            "stake_length": stake[3],
            "timestamp": current_time,
        })
    print(f'Triggering {len(valid_stakes)} payouts.')
    payout_database_entry(valid_stakes)
    payout_transfer(valid_stakes, password)


def stake_organizer(bot, investment_db):
    stake_valid_block = bot["stake_valid_block"]
    cursor = investment_db.cursor()
    cursor.execute("SELECT user FROM stakes")
    prior_investments = cursor.fetchall()
    # print(prior_investments)
    prior_flag = False
    for person in prior_investments:
        if bot['payor'] == person[0]:
            prior_flag = True
            print('user has prior investment')
    if not prior_flag:
        print("New stake")
        while True and bot["length_of_stake"] is not None:
            try:
                with investment_db:
                    cursor.execute(
                        (
                                "INSERT OR IGNORE INTO stakes " +
                                "(block, blockid, timestamp, user, " +
                                "asset, stakelength, stakevalidtime, amount, earlyamount) " +
                                "VALUES (?,?,?,?,?,?,?,?,?)"
                        ),
                        (
                            bot["block_num"],
                            bot["block_id"],
                            bot["timestamp"],
                            bot["payor"],
                            bot["asset_type"],
                            bot["length_of_stake"],
                            stake_valid_block,
                            bot["amount"],
                            bot['early_amount']
                        ),
                    )
                break
            except BaseException as err:
                handle_error(err, "ERROR SUBMITTING STAKE TO DB")
        # transfer 1 BTS back with memo 'Stake accepted and confirmed'
        bitshares, memo = reconnect()
        try:
            bitshares.wallet.unlock(bot['password'])
            bitshares.transfer(
                bot['payor'],
                1,
                STAKING_ASSET,
                memo=f'Stake accepted and confirmed',
                account=ACCOUNT_WATCHING
            )
            bitshares.wallet.lock()
            bitshares.clear_cache()
        except BaseException as err:
            handle_error(err, 'ERROR TRANSFERRING CONFIRMATION BACK TO USER')


def transfer_cancelled_stake(bot, transfer_amount):
    bitshares, memo = reconnect()
    try:
        bitshares.wallet.unlock(bot["password"])
        bitshares.transfer(
            bot["payor"],
            transfer_amount,
            STAKING_ASSET,
            memo='Investment returned',
            account=ACCOUNT_WATCHING
        )
        bitshares.wallet.lock()
        bitshares.clear_cache()
    except BaseException as err:
        handle_error(err, "ERROR TRANSFERRING CANCELLED STAKE.")
    print("Transferred cancelled stake back.")


def remove_stake_entry(account):
    investment_db = database_connection()
    cursor = investment_db.cursor()
    try:
        cursor.execute(
            "DELETE FROM stakes " +
            f"WHERE user='{account}'"
        )
    except BaseException as err:
        handle_error(err, "ERROR REMOVING STAKES FROM DB.")
    investment_db.commit()
    print("removed investment from db")


def cancelled_database_entry(stakes_to_cancel, bot):
    investment_db = database_connection()
    cursor = investment_db.cursor()
    while True:
        for stake in stakes_to_cancel:
            if bot['block_num'] >= stake[6]:
                cancelled_transfer_amount = stake[7]
            else:
                cancelled_transfer_amount = stake[8]
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
                            cancelled_transfer_amount,
                            bot['block_num'],
                        ),
                    )
            except BaseException as err:
                handle_error(err, "ERROR SUBMITTING CANCELS TO DB")
        break
    investment_db.commit()
    print("entered cancelled stakes into database")


def cancel_stake(bot):
    print(f'cancel stake for {bot["payor"]}')
    investment_db = database_connection()
    cursor = investment_db.cursor()
    cursor.execute(
        "SELECT * FROM stakes " +
        f"WHERE user='{bot['payor']}'"
    )
    stakes_to_cancel = cursor.fetchall()
    cancelled_database_entry(stakes_to_cancel, bot)
    remove_stake_entry(bot["payor"])
    cancelled_transfer_amount = 0
    for stake in stakes_to_cancel:
        print(f'valid block: {stake[6]}')
        if bot['block_num'] >= stake[6]:
            cancelled_transfer_amount += stake[7]
            print(f'full stake {cancelled_transfer_amount} returned')
        else:
            cancelled_transfer_amount += stake[8]
            print(f'early stake {cancelled_transfer_amount} returned')
    transfer_cancelled_stake(bot, cancelled_transfer_amount)
    investment_db.commit()


def check_block(memo, bot, investment_db, block):
    for trxs in block["transactions"]:
        for operation, trx in enumerate(trxs["operations"]):
            if trx[0] == 0 and Account(trx[1]["to"]).name == ACCOUNT_WATCHING:
                bot["payor"] = Account(trx[1]["from"]).name
                bot["asset_type"] = str(trx[1]["amount"]["asset_id"])
                asset_precision = Asset(bot["asset_type"]).precision
                bot["amount"] = int(trx[1]["amount"]["amount"]) / (10 ** asset_precision)
                bot['early_amount'] = bot['amount'] * 0.85
                # print(f'Early amount: {bot["early_amount"]}')
                Account.clear_cache()
                Asset.clear_cache()
                bot = get_json_memo(memo, bot, trx)
                if bot["asset_type"] != "1.3.0":
                    print('Wrong asset transferred.')
                elif bot["length_of_stake"] is None:
                    print('Wrong memo format.')
                elif bot["length_of_stake"] != "stop" \
                        and bot["length_of_stake"] is not None:
                    bot["block_id"] = f'{bot["block_num"]}.{str(operation)}'
                    if bot['length_of_stake'] == 'three_months':
                        bot["stake_valid_block"] = bot['block_num'] + THREE_BLOCK_MONTHS
                    elif bot['length_of_stake'] == 'six_months':
                        bot['stake_valid_block'] = bot['block_num'] + SIX_BLOCK_MONTHS
                    elif bot['length_of_stake'] == 'twelve_months':
                        bot['stake_valid_block'] = bot['block_num'] + TWELVE_BLOCK_MONTHS
                    else:
                        print('Wrong vesting period sent')
                    bot['timestamp'] = time.time()
                    if bot['amount'] == LOW_INVEST_AMOUNT or bot['amount'] == MID_INVEST_AMOUNT \
                            or bot['amount'] == HIGH_INVEST_AMOUNT or bot['amount'] == TOP_INVEST_AMOUNT:
                        stake_organizer(bot, investment_db)
                    else:
                        print('Wrong amount sent. Everything else was good.')
                elif bot["length_of_stake"] == "stop":
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
                elif json_memo["type"].lower() == "twelve_months":
                    bot["length_of_stake"] = "twelve_months"
                elif json_memo["type"].lower() == "stop":
                    bot["length_of_stake"] = "stop"
        except Exception as err:
            bot["length_of_stake"] = None
            handle_error(err, "JSON ERROR.")
    except Exception as err:
        bot["length_of_stake"] = None
        handle_error(err, "MEMO ERROR")
    return bot


# HELPER FUNCTIONS
def reconnect():
    bitshares = BitShares(node=NODE, nobroadcast=False)
    set_shared_bitshares_instance(bitshares)
    memo = Memo(blockchain_instance=bitshares)
    return bitshares, memo


def handle_error(err, err_string):
    print(f'{err_string}', file=open("logfile.txt", "a"))
    print("Type error: {}".format(str(err)), file=open("logfile.txt", "a"))
    print(format_exc(), file=open("logfile.txt", "a"))
    print('----------------')


def database_connection():
    return sqlite3_connect('investment.db')


# def account_balance_check():
#     account_balance = Account(ACCOUNT_WATCHING).balance(STAKING_ASSET)
#     Account.clear_cache()
#     if account_balance >= MAXIMUM_ACCOUNT_BALANCE:
#         print('Account exceeds maximum allowed value.')
#         print('Either reduce funds or celebrate raising all the money ;)')
#         exit(0)


def _get_payout_amount(stake_amount, payout_multiplier):
    return float(round(Decimal(stake_amount * payout_multiplier), 5))


# PRIMARY EVENT BACKBONE
def main():
    """
    The bot dictionary contains the information.
    It is passed around through each part containing only
    what it is currently working on.
    """
    bot = {'password': getpass('Input WALLET PASSWORD and press ENTER: ')}
    investment_db = database_connection()
    block_stall = 0
    last_block = 0
    add_jobs(bot['password'])
    try:
        while True:
            bitshares, memo = reconnect()
            # account_balance_check()
            block = scan_chain(memo, bot, investment_db)
            if block == last_block:
                block_stall += 1
                print('block stall: {}'.format(block_stall))
            else:
                block_stall = 0
                last_block = block
            if block_stall > 50:
                exit()
            time.sleep(6)
    except KeyboardInterrupt:
        try:
            print('Keyboard interrupt. Exiting')
        except BaseException as e:
            print(e)
            exit(0)
    investment_db.close()
    print('DB connection closed.')


if __name__ == '__main__':
    main()
