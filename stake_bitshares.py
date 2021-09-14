"""
BitShares.org StakeMachine
Interest Payments on Staking
BitShares Management Group Co. Ltd.
"""
# DISABLE SELECT PYLINT TESTS
# pylint: disable=broad-except, invalid-name, bad-continuation
# STANDARD MODULES
import time
from copy import deepcopy
from getpass import getpass
from json import dumps as json_dumps
from json import loads as json_loads
from threading import Thread

# PYBITSHARES MODULES
from bitshares.account import Account
from bitshares.asset import Asset
from bitshares.block import Block

# STAKE BTS MODULES
from config import (ADMIN_REPLAY, BITTREX_1, BITTREX_2, BITTREX_3,
                    BITTREX_ACCT, CUSTODIAN, DEV, DEV_AUTH, EMAIL,
                    INVEST_AMOUNTS, MAKE_PAYMENTS, MANAGERS, PENALTY, REPLAY,
                    REWARD)
from dev_auth import KEYS
from rpc import (authenticate, get_balance_bittrex, get_balance_pybitshares,
                 get_block_num_current, post_withdrawal_bittrex,
                 post_withdrawal_pybitshares, pybitshares_reconnect)
from utilities import (convert_date_to_munix, exception_handler, it,
                       munix_nonce, sql_db)

# GLOBAL CONSTANTS
MUNIX_MONTH = 86400 * 30 * 1000
NOMINATOR_MEMOS = [
    "stop",  # nominator stops all outstanding agreements
    "three_months",  # nominator creates 3 month agreement
    "six_months",  # nominator creates 6 month agreement
    "twelve_months",  # nominator creates 12 month agreement
]
ADMIN_MEMOS = [
    "bittrex_to_bmg",  # manager moves funds from bittrex to bitsharemanagment.group
    "bmg_to_bittrex",  # manager moves funds from bitsharemanagment.group to bittrex
    "loan_to_bmg",  # manager makes personal loan to bitsharesmanagement.group
]
MONTHS = {  # word phrase to number conversion
    "three_months": 3,
    "six_months": 6,
    "twelve_months": 12,
}
NINES = 999999999  # a default big number


# SQL DATABASE GET AND SET BLOCK NUMBER
def set_block_num_database(block_num):
    """
    update the block number last checked in the database
    :param int(block_num): the bitshares block number last checked by the bot
    """
    query = "UPDATE block_num SET block_num=?"
    values = (block_num,)
    sql_db(query, values)


def get_block_num_database():
    """
    what is the last block number checked in the database?
    """
    query = "SELECT block_num FROM block_num"
    fetchall = sql_db(query)
    return int(fetchall[0][0])


# SQL DATABASE RECEIPTS
def update_receipt_database(nonce, msg):
    """
    upon every audit worthy event update the receipt database with a pertinent message
    :param int(nonce): *start* munix timestamp associated with this stake
    :param str(msg): auditable event documentation
    :return None:
    """
    query = "INSERT INTO receipts (nonce, now, msg) VALUES (?,?,?)"
    values = (nonce, munix_nonce(), msg)
    sql_db(query, values)


# SQL DATABASE START, STOP, MARK PAID
def stake_start(params, keys=None):
    """
    upon receiving a new stake, send receipt to new nominator and
    insert into database new payouts due, sql columns in stake db:
    nominator      - the Bitshares username
    digital_asset       - the Bitshares digital_asset
    amount      - the amount staked
    payment     - base_amount, reward, penalty, agreement_3, agreement_6, or agreement_12
    start       - unix when this agreement began
    due         - unix when the payment is due
    processed   - unix when the payment was processed
    status      - pending, paid, premature, aborted
    number      - the reward payment number, eg 1,2,3; 0 for all other payment types
    :called by serve_nominator():
    :params int(nonce): munix timestamp *originally* associated with this stake
    :params int(block_num): block_num number when this stake began
    :params str(nominator): bitshares username of staking nominator
    :params int(amount): the amount the nominator is staking
    :params int(months): the number of months the nominator is staking
    :param dict(keys): pybitshares wallet password
    :return None:
    """
    # localize parameters
    nonce, block_num, trx_idx, ops_idx, nominator, amount, months = map(
        params.get,
        ("nonce", "block_num", "trx_idx", "ops_idx", "nominator", "amount", "months"),
    )
    # keys are None when using import_data.py to add existing agreements
    if keys is not None:
        # send confirmation receipt to nominator with memo using pybitshares
        memo = (
            f"{months} month nomination agreement of {amount} BTS entered into database"
            f" at epoch {nonce} in block {block_num} trx {trx_idx} op {ops_idx}"
        )
        memo += post_withdrawal_pybitshares(1, nominator, memo, keys)
        memo += json_dumps(params)
        update_receipt_database(nonce, memo)
    # batch new stake queries and process them atomically
    queries = []

    # get the blocktime converted to munix
    block = Block(block_num)
    Block.clear_cache()
    block_munix = convert_date_to_munix(block["timestamp"], fstring="%Y-%m-%dT%H:%M:%S")

    # same schema per line item of a new stake
    query = (
        "INSERT INTO stakes ( "
        + "nominator, "
        + "digital_asset, "
        + "amount, "
        + "type, "
        + "nonce, "
        + "start, "
        + "due, "
        + "processed, "
        + "status, "
        + "block_start, "
        + "trx_idx, "
        + "ops_idx, "
        + "block_processed, "
        + "number"
        + ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
    )
    # insert the `agreement` into the stakes database
    values = (
        nominator,
        "BTS",
        1,
        f"agreement_{months}",
        nonce,  # contract database insertion timestamp
        block_munix,  # start blocktime milleseconds
        block_munix,  # due at blocktime
        block_munix,  # processed at blocktime
        "paid",
        block_num,
        trx_idx,
        ops_idx,
        block_num,  # agreements are considered processed when entered
        0,  # agreements, base_amounts, and penalties are 0
    )
    dml = {"query": query, "values": values}
    queries.append(dml)
    # insert the `base_amount` into the stakes database
    values = (
        nominator,
        "BTS",
        amount,
        "base_amount",
        nonce,  # contract database insertion timestamp
        block_munix,  # start blocktime milleseconds
        block_munix + months * MUNIX_MONTH,  # due monthly from start blocktime
        0,
        "pending",
        block_num,
        trx_idx,
        ops_idx,
        NINES,  # a huge number; not processed yet
        0,  # agreements, base_amounts, and penalties are 0
    )
    dml = {"query": query, "values": values}
    queries.append(dml)
    # insert the early exit `penalty` into the stakes database
    values = (
        nominator,
        "BTS",
        int(-1 * amount * PENALTY),  # entered as negative value
        "penalty",
        nonce,  # contract database insertion timestamp
        block_munix,  # start blocktime milleseconds
        block_munix + months * MUNIX_MONTH,  # due monthly from start blocktime
        0,
        "pending",
        block_num,
        trx_idx,
        ops_idx,
        NINES,  # a huge number; not processed yet
        0,  # agreements, base_amounts, and penalties are 0
    )
    dml = {"query": query, "values": values}
    queries.append(dml)
    # nominator `rewards` are due monthly from start blocktime, enter each into db
    for month in range(1, months + 1):
        values = (
            nominator,
            "BTS",
            int(amount * REWARD),
            "reward",
            nonce,  # contract database insertion timestamp
            block_munix,  # start blocktime milleseconds
            block_munix + month * MUNIX_MONTH,  # due monthly from start blocktime
            0,
            "pending",
            block_num,
            trx_idx,
            ops_idx,
            NINES,  # a huge number; not processed yet
            month,  # ascending number designation of the reward payment
        )
        dml = {"query": query, "values": values}
        queries.append(dml)
    sql_db(queries)


def stake_stop(params, keys):
    """
    send base_amount less penalty from pybitshares wallet
    update database with base_amount and penalty paid; outstanding reward aborted
    :param int(nonce): munix timestamp when stop signal was read from blockchain
    :param int(block_num): block number when this stake began
    :param str(nominator): bitshares username of staking nominator
    :param dict(keys): pybitshares wallet password
    :return None:
    """
    # localize parameters
    nonce, block_num, nominator = map(params.get, ("nonce", "block_num", "nominator"))
    # query base_amount and and penalties due to nominator
    values = (nominator,)
    query = (
        "SELECT amount FROM stakes "
        + "WHERE nominator=? AND status='pending'"
        + " AND (type='base_amount' OR type='penalty')"
    )
    curfetchall_1 = sql_db(query, values)
    # query pending contract nonces by this nominator
    query = "SELECT nonce FROM stakes WHERE nominator=? AND status='pending'"
    curfetchall_2 = sql_db(query, values)  # note: same values as previous query
    # extract pertinent data from SELECT queries
    amounts_due = [int(i[0]) for i in curfetchall_1]
    amount = sum(amounts_due)
    items_due = len(amounts_due)
    contract_nonces = list(set([int(i[0]) for i in curfetchall_2]))
    # batch stop stake queries and process them atomically
    queries = []
    # SECURITY: there may be multiple contracts to stop
    for nonce in contract_nonces:
        # set base_amount to premature
        # with time and block processed
        query = (
            "UPDATE stakes "
            + "SET status='premature', processed=?, block_processed=? "
            + "WHERE nominator=? AND status='pending' AND type='base_amount'"
        )
        values = (nonce, block_num, nominator)
        dml = {"query": query, "values": values}
        queries.append(dml)
        # set penalty to paid
        query = (
            "UPDATE stakes "
            + "SET status='paid', processed=?, block_processed=? "
            + "WHERE nominator=? AND status='pending' AND type='penalty'"
        )
        values = (nonce, block_num, nominator)
        dml = {"query": query, "values": values}
        queries.append(dml)
        # set reward to aborted
        query = (
            "UPDATE stakes "
            + "SET status='aborted', processed=?, block_processed=? "
            + "WHERE nominator=? AND status='pending' AND type='reward'"
        )
        values = (nonce, block_num, nominator)
        dml = {"query": query, "values": values}
        queries.append(dml)
    sql_db(queries)
    # SECURITY - make payouts after sql updates
    # send premature payment to nominator
    # total base_amounts less total penalties
    if amount > 0:
        start_nonce = min(contract_nonces)
        params["nonce"] = start_nonce  # earliest pending nonce for receipts table
        params["amount"] = amount
        params["number"] = 0
        params["type"] = "stop"
        thread = Thread(target=payment_child, args=(deepcopy(params), keys,),)
        thread.start()
    else:
        # no payouts if less than or equal to zero, add receipt to db, and print WARN
        msg = f"WARN {nominator} sent STOP in block {block_num}, "
        if items_due == 0:
            msg += "but had no open agreements"
        elif amount == 0:
            msg += "but base_amount less penalty equals zero"
        elif amount < 0:
            msg += f"but has negative amount {amount} due"
        print(it("red", msg))
        update_receipt_database(nonce, msg)
        

def stake_paid(params):
    """
    update the stakes database for this payment from "processing" to "paid"
    :param str(nominator): bitshares username of staking nominator
    :param int(nonce): munix timestamp *originally* associated with this stake
    :param int(number): the counting number of this reward payment
    :return None:
    """
    # localize params
    nominator, nonce, number = map(params.get, ("nominator", "nonce", "number"))
    query = (
        "UPDATE stakes "
        + "SET status='paid', block_processed=?, processed=? "
        + "WHERE nominator=? AND nonce=? AND number=? AND status='processing' AND "
        + "(type='reward' OR type='base_amount')"
    )
    # note this is current block number not tx containing block
    values = (get_block_num_current(), munix_nonce(), nominator, nonce, number)
    sql_db(query, values)


# SERVE MEMO REQUESTS
def serve_nominator(params, keys):
    """
    create new stake or stop all stakes
    :params dict(memo):
    :params int(amount):
    :params str(nominator):
    :params int(block_num):
    :param dict(keys):
    :return str(msg):
    """
    # localize parameters
    memo, amount, nominator, block_num = map(
        params.get, ("memo", "amount", "nominator", "block_num"),
    )
    # new nominator wants to stake and used a valid memo
    if memo["type"] in MONTHS:
        months = MONTHS[memo["type"]]
        params.update({"months": months})
        msg = (
            f"received new nomination agreement from {nominator} in {block_num} "
            + f"for {months} months and {amount} amount"
        )
        stake_start(params, keys)
    # existing nominator wishes to stop all his stake agreements prematurely
    elif memo["type"] == "stop":
        msg = f"received stop demand from {nominator} in {block_num}"
        stake_stop(params, keys)
    return msg


def serve_admin(params, keys):
    """
    transfer funds to and from bittrex or loan funds to custodian account
    :params dict(memo):
    :params int(amount):
    :params str(nominator):
    :param dict(keys):
    :return str(msg):
    """
    msg = "skipping admin actions during REPLAY" + json_dumps(params)
    if ((get_block_num_current() - get_block_num_database()) < 100) or ADMIN_REPLAY:
        # localize parameters
        memo, amount, nominator = map(params.get, ("memo", "amount", "nominator"))
        msg = f"admin request failed {(nominator, amount, memo)}"
        # the manager wishes to move funds from bittrex to custodian
        if memo["type"] == "bittrex_to_bmg":
            try:
                transfer_amount = int(memo["amount"])
                api = int(memo["api"])
                assert api in [1, 2, 3]
                assert transfer_amount > 400
                msg = post_withdrawal_bittrex(transfer_amount, nominator, api, keys)
            except Exception as error:
                msg = exception_handler(error)
                print(msg)
                update_receipt_database(munix_nonce(), msg)
        # the manager wishes to move funds from custodian to bittrex
        elif memo["type"] == "bmg_to_bittrex":
            try:
                transfer_amount = int(memo["amount"])
                api = int(memo["api"])
                assert api in [1, 2, 3]
                assert transfer_amount > 400
                decode_api = {1: BITTREX_1, 2: BITTREX_2, 3: BITTREX_3}
                bittrex_memo = decode_api[api]
                msg = (
                    memo["type"]
                    + bittrex_memo
                    + post_withdrawal_pybitshares(
                        transfer_amount, BITTREX_ACCT, bittrex_memo, keys
                    )
                )
            except Exception as error:
                msg = exception_handler(error)
                print(msg)
                update_receipt_database(munix_nonce(), msg)
        # the manager has loaned the custodian personal funds
        elif memo["type"] == "loan_to_bmg":
            msg = f"{nominator} has loaned the custodian {amount}"
        # the manager sent an invalid memo
        else:
            msg = f"{nominator} sent invalid admin memo with {amount}"
    return msg


def serve_invalid(params, keys):
    """
    nominator or admin has made an invalid request, return funds less fee
    :params dict(memo):
    :params int(amount):
    :params str(nominator):
    :params int(block_num):
    :params int(nonce):
    :param dict(keys):
    """
    # localize parameters
    memo, amount, nominator, nonce, block_num = map(
        params.get, ("memo", "amount", "nominator", "nonce", "block_num")
    )
    request_type = {
        "nominator_memo": memo["type"] in NOMINATOR_MEMOS,  # bool()
        "admin_memo": memo["type"] in ADMIN_MEMOS,  # bool()
        "admin": nominator in MANAGERS,  # bool()
        "invest_amount": amount in INVEST_AMOUNTS,  # bool()
        "ltm": Account(nominator).is_ltm,  # bool()
        "memo": memo,  # nominator's memo
        "amount": amount,  # amount sent by nominator
        "nominator": nominator,  # bitshares user name
        "nonce": nonce,  # start time of this ticket
        "block_num": block_num,  # block number nominator sent funds
    }

    msg = "invalid request "
    if amount > 50:
        msg += "50 BTS fee charged "
    msg += json_dumps(request_type)
    print(msg)
    amount -= 50
    if amount > 10:
        msg += post_withdrawal_pybitshares(int(amount), nominator, msg, keys)
    return msg


# CHECK BLOCKS FOR INCOMING TRANSFERS
def decrypt_memo(ciphertext, keys):
    """
    using the memo key, decrypt the memo in the nominator's deposit
    """
    try:
        _, memo = pybitshares_reconnect()
        memo.blockchain.wallet.unlock(keys["password"])
        decrypted_memo = memo.decrypt(ciphertext).replace(" ", "")
        memo.blockchain.wallet.lock()
        print("decrypted memo", decrypted_memo)
        try:
            msg = json_loads(decrypted_memo)
        except Exception:
            # last legacy agreement was in block 60692860
            # legacy agreements were invalid and returned to nominator if not in json format
            if get_block_num_database() > 60693000:
                msg = {
                    "type": decrypted_memo.replace('"', "")  # allow d-quotes
                    .replace("'", "")  # allow s-quotes
                    .replace(" ", "")  # allow errant space in memo
                }
            else:
                msg = {"type": "invalid"}
        print(msg)
        if "type" in msg.keys():
            if msg["type"] in NOMINATOR_MEMOS + ADMIN_MEMOS:
                return msg
    except Exception:
        pass
    return {"type": "invalid"}


def check_block(block_num, block, keys):
    """
    check for nominator transfers to the custodian in this block
    :param int(block_num): block number associated with this block
    :param dict(block): block data
    :param dict(keys): bittrex api keys and pybitshares wallet password
    :return None:
    """
    for trx_idx, trx in enumerate(block["transactions"]):
        for ops_idx, ops in enumerate(trx["operations"]):
            # if it is a BTS transfer to the custodian managed account
            if (
                ops[0] == 0  # withdrawal
                and Account(ops[1]["to"]).name == keys["custodian"]  # transfer to me
                and str(ops[1]["amount"]["asset_id"])
                == "1.3.0"  # of BTS core digital_asset
            ):
                nonce = munix_nonce()
                nominator = Account(ops[1]["from"]).name
                amount = int(ops[1]["amount"]["amount"]) // 10 ** int(
                    Asset("1.3.0").precision
                )
                msg = (
                    f"transfer of {amount} BTS to custodian from {nominator} "
                    + f"in block {block_num}"
                )
                update_receipt_database(nonce, msg)
                print(msg)
                # provide timestamp, extract amount and nominator, dedode the memo
                msg = ""
                memo = {"type": "invalid"}
                if "memo" in ops[1]:
                    memo = decrypt_memo(ops[1]["memo"], keys)
                params = {
                    "nominator": nominator,
                    "amount": amount,
                    "memo": memo,
                    "block_num": block_num,
                    "trx_idx": trx_idx,
                    "ops_idx": ops_idx,
                    "ops": ops,
                    "nonce": nonce,
                }
                print(it("green", "incoming transaction to custodian"))
                print(it("green", json_dumps(params)))
                # handle requests to start and stop stakes
                if memo["type"] == "stop" or (
                    memo["type"] in NOMINATOR_MEMOS and amount in INVEST_AMOUNTS
                ):
                    msg = serve_nominator(params, keys)
                # handle admin requests to move funds
                elif (
                    nominator in MANAGERS
                    and memo["type"] in ADMIN_MEMOS
                    # and Account(nominator).is_ltm
                ):
                    msg = serve_admin(params, keys)
                # handle invalid requests
                else:
                    msg = serve_invalid(params, keys)
                update_receipt_database(nonce, msg)


# HANDLE PAYMENTS
def payment_parent(payments_due, keys):
    """
    spawn payment threads
    :param matrix(payments_due): list of payments due;
        each with amount, nominator, nonce, number
    :return None:
    """
    threads = {}
    for payment in payments_due:
        if MAKE_PAYMENTS:
            time.sleep(0.1)  # reduce likelihood of race condition
            params = {
                "amount": payment[0],
                "nominator": payment[1],
                "nonce": payment[2],
                "number": payment[3],
                "type": payment[4],
            }
            # each individual outbound payment_child()
            # is a child of listener_sql(),
            # we'll use deepcopy so that the thread's locals are static to the payment
            threads[payment] = Thread(
                target=payment_child, args=(deepcopy(params), keys,),
            )
            threads[payment].start()


def payment_child(params, keys):
    """
    attempt to make simple payout
    if success:
        mark stake reward payment as "paid" in database
        add receipt to database
    if failed:
        attempt to move funds from bittrex and try again
        if failed:
            send 1 bts to nominator from bmg w/ support memo
            mark stake reward payment as "delinquent" in database
        if success:
            mark stake reward payment as "paid" in database
            add receipt to db for tx to nominator
            add receipt to db for tx from bittrex to bmg
    :params int(amount): the amount due to nominator
    :params str(nominator): bitshares username of staking nominator
    :params int(nonce): munix timestamp *originally* associated with this stake
    :params int(number): the counting number of this reward payment
    :param dict(keys): pybitshares wallet password
    :return None:
    """
    # localize params
    amount, nominator, nonce, number = map(
        params.get, ("amount", "nominator", "nonce", "number")
    )
    print(it("green", str(("make payout process", amount, nominator, nonce, number))))
    # calculate need vs check how much funds we have on hand in the custodian account
    # always keep 100 BTS on hand for fees, sending receipt memos, etc.
    params.update(
        {"need": amount + 100, "pybitshares_balance": get_balance_pybitshares()}
    )
    # if we don't have enough we'll have to move some BTS from bittrex to custodian
    covered = True
    if params["pybitshares_balance"] < params["need"]:
        covered = payment_cover(params, keys)
    # assuming we have enough, just pay the nominator his due
    # mark as paid, post withdrawal, add receipt to db
    if covered:
        memo = (
            f"Payment for stakeBTS nonce {nonce} type {params['type']} {number}, "
            + "we appreciate your business!"
        )
        stake_paid(params)
        # SECURITY - after it has been marked as paid...
        msg = memo + post_withdrawal_pybitshares(amount, nominator, memo, keys)
        msg += json_dumps(params)
        update_receipt_database(nonce, msg)
    # something went wrong, send the nominator an IOU with support details
    # do not mark as paid, but add receipt to db
    else:
        memo = (
            f"your stakeBTS payment of {amount} failed for an unknown reason, "
            + f"please contact {EMAIL} "
            + f"BTSstake nonce {nonce} type {params['type']} {number}"
        )
        msg = memo + post_withdrawal_pybitshares(1, nominator, memo, keys)
        msg += json_dumps(params)
        update_receipt_database(nonce, msg)


def payment_cover(params, keys):
    """
    when there are not enough funds in pybitshares wallet
    move some funds from bittrex, check all 3 corporate api accounts
    :param int(need): the amount due to nominator + 10
    :param str(nominator): the amount in custodian account
    :param dict(keys): pybitshares wallet password and bittrex keys
    :param int(nonce): munix timestamp *originally* associated with this stake
    :param int(number): the counting number of this reward payment
    :return bool(): whether of not we have enough funds to cover this payment
    """
    # localize params
    need, pybitshares_balance, nonce = map(
        params.get, ("need", "pybitshares_balance", "nonce")
    )
    # can we afford to cover nominator's payout?
    covered = False
    try:
        # calculate our deficit and and fetch our bittrex account balances
        deficit = need - pybitshares_balance
        bittrex_balance = get_balance_bittrex(keys)  # returns dict()
        # assuming we can cover it with bittrex balances
        if sum(bittrex_balance.values()) > deficit:
            # we start moving funds until we have just enough in the custodian acct
            for api in range(1, 4):
                bittrex_available = bittrex_balance[api]
                if bittrex_available > 510:
                    # at last check bittrex charges 5 BTS to withdraw
                    # presume 10 for safe measure
                    qty = min(deficit, bittrex_available - 10)
                    msg = "cover payment"
                    msg += post_withdrawal_bittrex(qty, CUSTODIAN, api, keys)
                    msg += json_dumps(params)
                    update_receipt_database(nonce, msg)
                    deficit -= qty
                    if deficit <= 0:
                        break  # eg. if 1st api has funds stop here
        # if we had enough funds,
        # wait for funds to arrive
        # breaks on timeout or on receipt of funds
        if deficit <= 0:
            covered = True
            begin = time.time()
            while get_balance_pybitshares() < need:
                time.sleep(120)
                # calculate elapsed time in MINUTES
                elapsed = int((time.time() - begin) / 60)
                msg = it(
                    "purple",
                    f"Awaiting on funds from Bittrex for nonce {nonce}, "
                    + f"minutes elapsed {elapsed}",
                )
                print(msg)
                # wait up to 12 hours for bittrex funds to arrive
                if elapsed > 60 * 12:
                    print(it("purlple", f"WARN: nonce {nonce} funds failed to arrive"))
                    covered = False
                    break
    except Exception as error:
        error = "cover payment failed" + json_dumps(params) + error
        update_receipt_database(nonce, error)
    return covered


# LISTENER THREADS
def listener_bitshares(keys):
    """
    get the last block number checked from the database
    and the latest block number from the node
    check each block in between for stake related transfers from nominators
    then update the last block checked in the database
    :param dict(keys): bittrex api keys and pybitshares wallet password
    """
    while True:
        block_last = get_block_num_database()
        block_new = get_block_num_current()
        for block_num in range(block_last + 1, block_new + 1):
            if block_num % 20 == 0:
                print(
                    it("blue", str((block_num, time.ctime(), int(1000 * time.time()))))
                )
            block = Block(block_num)
            Block.clear_cache()
            check_block(block_num, block, keys)
            set_block_num_database(block_num)
        # don't sleep during replay... else batch when live
        if (block_new - block_last) < 100:
            time.sleep(30)


def listener_sql(keys):
    """
    make all reward and base_amount payments due and mark them paid in database
    mark penalties due as aborted in database
    set processed time and block to current for all
    send individual payments using threading
    :param dict(keys): pybitshares wallet password
    """
    while True:
        # get millesecond timestamp and current block number
        now = munix_nonce()
        block_num = get_block_num_current()
        # read from database gather list of payments due
        query = (
            "SELECT amount, nominator, nonce, number, type FROM stakes "
            + "WHERE (type='base_amount' OR type='reward') AND due<? AND status='pending'"
        )
        values = (now,)
        payments_due = sql_db(query, values)
        # gather list of agreements that have matured
        query = (
            "SELECT amount, nominator, nonce, number FROM stakes "
            + "WHERE type='penalty' AND due<? AND status='pending'"
        )
        values = (now,)
        closed_agreements = sql_db(query, values)  # strictly for printing
        print(
            it("green", "payments due"),
            payments_due,
            it("red", "closed agreements"),
            closed_agreements,
        )
        # batch payment due queries and process them atomically
        queries = []
        # update base_amount and reward due status to processing
        query = (
            "UPDATE stakes "
            + "SET status='processing', block_processed=?, processed=? "
            + "WHERE (type='base_amount' OR type='reward') AND due<? AND status='pending'"
        )
        values = (block_num, now, now)
        dml = {"query": query, "values": values}
        queries.append(dml)
        # update penalties due to status aborted
        query = (
            "UPDATE stakes "
            + "SET status='aborted', block_processed=?, processed=? "
            + "WHERE type='penalty' AND due<? AND status='pending'"
        )
        values = (block_num, now, now)
        dml = {"query": query, "values": values}
        queries.append(dml)
        sql_db(queries)
        # make the payments due
        payment_parent(payments_due, keys)
        time.sleep(60)


def listener_balances(keys):
    """
    about every 2 hours update receipts table with current account balances
    """
    balances = {0: get_balance_pybitshares()}
    balances.update(get_balance_bittrex(keys))
    print(it("purple", "balances"), balances)
    update_receipt_database(0, json_dumps(balances))
    now = munix_nonce()
    # read from database gather list of payments due in next 24 hours
    query = (
        "SELECT amount FROM stakes "
        + "WHERE (type='base_amount' OR type='reward') AND due<? AND status='pending'"
    )
    values = (now + 86400 * 1000,)
    curfetchall = sql_db(query, values)
    due_today = int(sum([i[0] for i in curfetchall]))
    print(it("purple", "due today"), due_today)
    if due_today > balances[0]:
        print(it("red", "WARN INSUFFICIENT FUNDS IN LOCAL WALLET FOR 24 HOUR EXPENSES"))
    if due_today > sum(balances.values()):
        print(it("red", "WARN INSUFFICIENT FUNDS IN ALL WALLETS FOR 24 HOUR EXPENSES"))
    time.sleep(7195)


# PRIMARY EVENT BACKBONE
def welcome(keys):
    """
    UX at startup
    """
    block_num_current = get_block_num_current()
    print(it("blue", f"\033c\n{keys['custodian'].upper()} AUTHENTICATED\n"))
    # display developer mode, replay type, and current block number locally vs actual
    if DEV:
        print(it("red", "\n     *** DEVELOPER MODE ***\n\n"))
    if isinstance(REPLAY, bool):
        if REPLAY:
            print("start - REPLAY - from last block in database")
        else:
            print("start - NO REPLAY - from current block number")
            set_block_num_database(block_num_current)
    elif isinstance(REPLAY, int):
        print(f"start - REPLAY - from user specified block number {REPLAY}")
        # 59106023 tony-peacock created first legacy stake of 25000
        # 60692860 sune-3355 created last legacy stake of 50000
        if REPLAY < 59106000:
            raise ValueError(it("red", "WARN first stake was 59106023"))
        if REPLAY < 60693000:
            print(it("red", "WARN replaying legacy stakes, inspect database when done"))
        set_block_num_database(REPLAY - 1)
    print(
        "\n",
        "database block:",
        get_block_num_database(),
        "current block:",
        block_num_current,
    )
    print(time.ctime(), int(1000 * time.time()), "\n")


def login():
    """
    user input login credentials for pybitshares and bittrex
    :return dict(keys): authenticated bittrex api keys and pybitshares wallet password
    """
    if DEV_AUTH:
        return KEYS
    keys = {}
    authenticated = False
    if DEV:
        keys = {
            "custodian": CUSTODIAN,
            "password": "",
            "api_1_key": "",
            "api_1_secret": "",
            "api_2_key": "",
            "api_2_secret": "",
            "api_3_key": "",
            "api_3_secret": "",
        }
        return keys
    while not authenticated:
        keys = {
            "custodian": CUSTODIAN,
            "password": getpass(
                f"\nInput Pybitshares Password for {CUSTODIAN} and press ENTER:\n"
            ),
            "api_1_key": getpass("\nInput Bittrex API 1 Key and press ENTER:\n"),
            "api_2_key": getpass("\nInput Bittrex API 2 Key and press ENTER:\n"),
            "api_3_key": getpass("\nInput Bittrex API 3 Key and press ENTER:\n"),
            "api_1_secret": getpass("\nInput Bittrex API 1 Secret and press ENTER:\n"),
            "api_2_secret": getpass("\nInput Bittrex API 2 Secret and press ENTER:\n"),
            "api_3_secret": getpass("\nInput Bittrex API 3 Secret and press ENTER:\n"),
        }
        authenticated = authenticate(keys)
    return keys


def main():
    """
    login then begin while loop listening for nominator requests and making timely payouts
    """
    keys = login()
    welcome(keys)
    # branch into three run forever threads with run forever while loops
    # ==================================================================================
    # block operations listener_bitshares() for incoming nominator requests
    thread_1 = Thread(target=listener_bitshares, args=(keys,))
    thread_1.start()
    if MAKE_PAYMENTS:
        # listener_sql() check sql db for payments due
        thread_2 = Thread(target=listener_sql, args=(keys,))
        thread_2.start()
        # listener_balances() periodically updates receipts table with account balances
        thread_3 = Thread(target=listener_balances, args=(keys,))
        thread_3.start()


if __name__ == "__main__":
    main()
