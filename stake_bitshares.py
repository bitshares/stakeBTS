"""
BitShares.org StakeMachine
Interest Payments on Staking
BitShares Management Group Co. Ltd.
"""
# DISABLE SELECT PYLINT TESTS
# pylint: disable=broad-except, invalid-name, bad-continuation
# pylint: disable=too-many-lines, too-many-locals, too-many-branches
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
from config import (ADMIN_REPLAY, BITTREX_1, BITTREX_2, BITTREX_3, COLOR,
                    BITTREX_ACCT, CONFIRM_AGREEMENTS, CUSTODIAN, DEV, DEV_AUTH,
                    EMAIL, INVEST_AMOUNTS, LOGO, MAKE_PAYMENTS, MANAGERS,
                    MIN_BALANCE, NODE, PENALTY, REPLAY, REWARD)
from db_backup import db_backup
from dev_auth import KEYS
from rpc import (authenticate, get_balance_bittrex, get_balance_pybitshares,
                 get_block_num_current, post_withdrawal_bittrex,
                 post_withdrawal_pybitshares, pybitshares_reconnect)
from utilities import (convert_date_to_munix, exception_handler, it, line_info,
                       munix_nonce, sql_db)

# GLOBAL CONSTANTS
NINES = 999999999  # a default big number
MUNIX_HOUR = 3600 * 1000
MUNIX_DAY = 86400 * 1000
MUNIX_WEEK = 86400 * 1000 * 7
MUNIX_MONTH = 86400 * 1000 * 30
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
    curfetchall = sql_db(query)
    return int(curfetchall[0][0])


# SQL DATABASE RECEIPTS
def update_receipt_database(nonce, msg):
    """
    upon every audit worthy event update the receipt database with a pertinent message
    :param int(nonce): *start* munix timestamp associated with this stake
    :param json(msg): auditable event documentation as json
    :return None:
    """
    try:
        msg = json_dumps(json_loads(msg))
    except Exception as error:
        print("warn: msg is invalid json", exception_handler(error), msg)
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
    # SECURITY - sql client side filter on unique new stakes
    query = """
        SELECT nonce
        FROM stakes
        WHERE block_start=? AND trx_idx=? AND ops_idx=?
    """
    values = (block_num, trx_idx, ops_idx)
    # True; proceed only if no previous entry in db for this block:trx:op
    if not [i[0] for i in sql_db(query, values)]:
        # batch new stake queries and process them atomically
        queries = []
        # SECURITY - stakes start from blocktime converted to munix
        block = Block(block_num)
        Block.clear_cache()
        block_munix = convert_date_to_munix(block["timestamp"], fstring="%Y-%m-%dT%H:%M:%S")
        # same schema per line item of a new stake
        query = """
            INSERT INTO stakes (
            nominator,
            digital_asset,
            amount,
            type,
            nonce,
            start,
            due,
            processed,
            status,
            block_start,
            trx_idx,
            ops_idx,
            block_processed,
            number
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """
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
            block_munix + months * MUNIX_MONTH,  #  due at end of term
            0,
            "pending",  # only pending things should be paid
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
            block_munix + months * MUNIX_MONTH,  #  due at end of term
            0,
            "pending",  # only pending things should be paid
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
                block_munix + month * MUNIX_MONTH,  #  due every 30 days
                0,
                "pending",  # only pending things should be paid
                block_num,
                trx_idx,
                ops_idx,
                NINES,  # a huge number; not processed yet
                month,  # ascending number designation of the reward payment
            )
            dml = {"query": query, "values": values}
            queries.append(dml)
        sql_db(queries)
        # send confirmation receipt to nominator with memo using pybitshares
        if CONFIRM_AGREEMENTS:
            msg = {}
            msg["params"] = params
            msg["memo"] = (
                f"{months} month nomination agreement of {amount} BTS entered into database"
                f" at epoch {nonce} in block {block_num} trx {trx_idx} op {ops_idx}"
            )
            msg["response"] = json_loads(
                post_withdrawal_pybitshares(1, nominator, msg["memo"], keys)
            )
            update_receipt_database(nonce, json_dumps(msg))
        # update block_processed to actual callback block
        block_num = 0
        try:
            block_num = int(msg["response"]["block_num"])
        except Exception as error:
            msg = {"error": exception_handler(error) + " " + line_info()}
            update_receipt_database(nonce, json_dumps(msg))
        if block_num:
            params["block_num"] = block_num
            params["edits"] = [f"agreement_{months}"]
            params["nonces"] = [nonce]
            params["number"] = 0
            # SECURITY - status=confirmed
            payment_confirmed(params)
    else:
        print(it("red", "Attempting to put a stake in the database twice, aborted"))
        print(params)


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
    query = """
        SELECT amount FROM stakes
        WHERE nominator=? AND status='pending'
        AND (type='base_amount' OR type='penalty')
    """
    curfetchall_1 = sql_db(query, values)
    # query pending contract nonces by this nominator
    query = "SELECT nonce FROM stakes WHERE nominator=? AND status='pending'"
    curfetchall_2 = sql_db(query, values)  # note: same values as previous query
    # extract pertinent data from SELECT queries
    amounts_due = [int(i[0]) for i in curfetchall_1]
    agreement_nonces = list({int(i[0]) for i in curfetchall_2})
    amount = sum(amounts_due)
    items_due = len(amounts_due)
    # send premature payment to nominator
    # total base_amounts less total penalties
    if amount > 0:
        params["nonce"] = min(agreement_nonces)  # earliest pending nonce for receipt
        params["nonces"] = agreement_nonces
        params["amount"] = amount
        params["number"] = 0  # SECURITY - used by payment_confirmed()
        params["type"] = "stop"  # SECURITY - used by payment_child()
        thread = Thread(target=payment_child, args=(deepcopy(params), keys,),)
        thread.start()
    else:
        # no payouts if less than or equal to zero, add receipt to db, and print WARN
        msg = {}
        msg["warn"] = f"WARN {nominator} sent STOP in block {block_num}, "
        if items_due == 0:
            msg["warn"] += "but had no open agreements"
        elif amount == 0:
            msg["warn"] += "but base_amount less penalty equals zero"
        elif amount < 0:
            msg["warn"] += f"but has negative amount {amount} due"
        print(it("red", json_dumps(msg)))
        update_receipt_database(nonce, json_dumps(msg))


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
    # for now, use irreversible block number
    # later, payment_confirmed() will update to actual block number
    block_num = get_block_num_current()
    now = munix_nonce()
    if params["type"] == "stop":
        # SECURITY: there may be multiple contracts to stop
        queries = []
        for agreement in params["nonces"]:
            # use the same values for next 3 queries
            values = (now, block_num, nominator, agreement)
            # set base_amount to paid
            query = """
                UPDATE stakes
                SET status='paid', processed=?, block_processed=?
                WHERE nominator=? AND status='pending' AND nonce=?
                AND type='base_amount'
            """
            dml = {"query": query, "values": values}
            queries.append(dml)
            # set penalty to paid
            query = """
                UPDATE stakes
                SET status='paid', processed=?, block_processed=?
                WHERE nominator=? AND status='pending' AND nonce=?
                AND type='penalty'
            """
            dml = {"query": query, "values": values}
            queries.append(dml)
            # set reward to aborted
            query = """
                UPDATE stakes
                SET status='aborted', processed=?, block_processed=?
                WHERE nominator=? AND status='pending' AND nonce=?
                AND type='reward'
            """
            dml = {"query": query, "values": values}
            queries.append(dml)
        sql_db(queries)

    elif params["type"] in ["reward", "base_amount"]:
        query = """
            UPDATE stakes SET status='paid',
            block_processed=?,
            processed=?
            WHERE nominator=?
            AND nonce=?
            AND number=?
            AND status='processing' AND (type='reward' OR type='base_amount')
        """
        values = (
            block_num,
            now,
            nominator,
            nonce,
            number,
        )
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
    :return dict(msg):
    """
    # build a msg dict for receipt database
    msg = {}
    msg["function"] = line_info()
    msg["params"] = params
    msg["status"] = "serve_nominator failed for unknown reason"
    # localize parameters
    memo, amount, nominator, block_num = map(
        params.get, ("memo", "amount", "nominator", "block_num"),
    )
    # new nominator wants to stake and used a valid memo
    if memo["type"] in MONTHS:
        months = MONTHS[memo["type"]]
        params.update({"months": months})
        msg["params"].update({"months": months})
        msg["status"] = (
            f"received new nomination agreement from {nominator} in {block_num} "
            + f"for {months} months and {amount} amount"
        )
        stake_start(params, keys)
    # existing nominator wishes to stop all his stake agreements prematurely
    elif memo["type"] == "stop":
        msg["status"] = f"received stop demand from {nominator} in {block_num}"
        stake_stop(params, keys)
    # return the msg as json string
    return msg


def serve_admin(params, keys):
    """
    transfer funds to and from bittrex or loan funds to custodian account
    :legitimate memos:
        {"type": "bittrex_to_bmg", "amount": X, "api": Y}
        {"type": "bmg_to_bittrex", "amount": X, "api": Y}
        {"type": "loan_to_bmg"}
    :params dict(memo):
    :params int(amount):
    :params str(nominator):
    :param dict(keys):
    :return dict(msg):
    """
    # build a msg dict for receipt database
    msg = {}
    msg["function"] = line_info()
    msg["params"] = params
    msg["status"] = "skipping serve_admin during REPLAY"
    # avoid serving admin requests during replay
    if ((get_block_num_current() - get_block_num_database()) < 100) or ADMIN_REPLAY:
        # localize parameters
        memo, amount, nominator = map(params.get, ("memo", "amount", "nominator"))
        msg["status"] = f"admin request failed {(nominator, amount, memo)}"
        # the manager wishes to move funds from bittrex to custodian
        if memo["type"] == "bittrex_to_bmg":
            try:
                transfer_amount = int(memo["amount"])
                api = int(memo["api"])
                assert api in [1, 2, 3]
                assert transfer_amount > 400
                msg["api"] = api
                msg["memo"] = memo
                msg["response"] = json_loads(
                    post_withdrawal_bittrex(transfer_amount, nominator, api, keys)
                )
                msg[
                    "status"
                ] = f"{nominator} bittrex_to_bmg {transfer_amount} BTS, api {api}"
            except Exception as error:
                msg["error"] = exception_handler(error)
                print(msg)
        # the manager wishes to move funds from custodian to bittrex
        elif memo["type"] == "bmg_to_bittrex":
            try:
                transfer_amount = int(memo["amount"])
                api = int(memo["api"])
                assert api in [1, 2, 3]
                assert transfer_amount > 400
                decode_api = {1: BITTREX_1, 2: BITTREX_2, 3: BITTREX_3}
                bittrex_memo = decode_api[api]
                msg["api"] = api
                msg["memo"] = memo
                msg["response"] = json_loads(
                    post_withdrawal_pybitshares(
                        transfer_amount, BITTREX_ACCT, bittrex_memo, keys
                    )
                )
                msg[
                    "status"
                ] = f"{nominator} bmg_to_bittrex {transfer_amount} BTS, api {api}"
            except Exception as error:
                msg["error"] = exception_handler(error)
                print(msg)
        # the manager has loaned the custodian personal funds
        elif memo["type"] == "loan_to_bmg":
            msg["status"] = f"{nominator} has loaned the custodian {amount}"
        # the manager sent an invalid memo
        else:
            msg["status"] = f"{nominator} sent invalid admin memo with {amount}"
            msg["error"] = "invalid memo"
    # return the msg as json string
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
    :return dict(msg):
    """
    # build a msg dict for receipt database
    msg = {}
    msg["function"] = line_info()
    msg["params"] = params
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
    msg["status"] = f"{nominator} sent invalid admin memo {memo} with {amount}"
    msg["request_type"] = request_type
    msg["fee"] = "NO fee charged"
    if amount > 50:
        msg["fee"] = "50 BTS fee charged"
    print(msg)
    amount -= 50
    if amount > 10:
        msg["response"] = json_loads(
            post_withdrawal_pybitshares(int(amount), nominator, msg["fee"], keys)
        )
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
                # for later contracts we can allow non json memo
                # and loosen accuracy for agreement intent
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
    # each block has lists of operations in a list of transactions
    # each operation is two element list: [int, dict()]
    for trx_idx, trx in enumerate(block["transactions"]):
        for ops_idx, ops in enumerate(trx["operations"]):
            msg = {}
            msg["function"] = line_info()
            nonce = munix_nonce()
            incoming = False
            outgoing = False
            # if the operation is a transfer,
            # NOTE: the ops[0] == 0 clause first to prevent KeyError
            if ops[0] == 0:
                # of BTS core token
                if str(ops[1]["amount"]["asset_id"]) == "1.3.0":
                    # extract the amount and round down as an integer
                    amount = int(ops[1]["amount"]["amount"]) // 10 ** int(
                        Asset("1.3.0").precision
                    )
                    msg["transfer"] = {
                        "nonce": nonce,
                        "amount": amount,
                        "asset": "BTS",
                        "block_num": block_num,
                        "trx_idx": trx_idx,
                        "ops_idx": ops_idx,  # block_num:trx_idx:ops_idx is unique
                    }
                    # determine if outgoing from custodian
                    if keys["custodian"] == Account(ops[1]["from"]).name:
                        outgoing = True
                        nominator = Account(ops[1]["to"]).name
                        msg["transfer"].update(
                            {
                                "direction": "outgoing",
                                "from": keys["custodian"],
                                "to": nominator,
                            }
                        )
                    # determine if incoming to custodian
                    elif keys["custodian"] == Account(ops[1]["to"]).name:
                        incoming = True
                        nominator = Account(ops[1]["from"]).name
                        msg["transfer"].update(
                            {
                                "direction": "incoming",
                                "from": nominator,
                                "to": keys["custodian"],
                            }
                        )
            # SECURITY - ANY transfer of BTS involving the custodian written to db
            if incoming or outgoing:
                update_receipt_database(nonce, json_dumps(msg))
            # inbound transfer detected, act on it
            if incoming:
                # provide timestamp, extract amount and nominator, decoded memo
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
                msg["params"] = params
                update_receipt_database(nonce, json_dumps(msg))
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
                    and (Account(nominator).is_ltm or DEV_AUTH)
                ):
                    msg = serve_admin(params, keys)
                # handle invalid requests
                else:
                    msg = serve_invalid(params, keys)
                update_receipt_database(nonce, json_dumps(msg))


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
    # always keep min BTS on hand for fees, sending receipt memos, etc.
    params.update(
        {"need": amount + MIN_BALANCE, "pybitshares_balance": get_balance_pybitshares()}
    )
    if "nonces" not in params:
        params["nonces"] = [params["nonce"]]
    # SECURITY: stop type will require multiple edits
    params["edits"] = []
    if params["type"] == "stop":
        # multiple edits when type=stop
        params["edits"] = ["base_amount", "penalty"]
    elif params["type"] in ["reward", "base_amount"]:
        params["edits"] = [params["type"]]
    # if we don't have enough we'll have to move some BTS from bittrex to custodian
    covered = True
    if params["pybitshares_balance"] < params["need"]:
        covered = payment_cover(params, keys)
    # assuming we have enough, just pay the nominator his due
    # mark as paid, post withdrawal, add receipt to db
    msg = {}
    if covered:
        memo = (
            f"Payment for stakeBTS items {params['nonces']} "
            + f"type {params['type']} number {number}, "
            + "we appreciate your business!"
        )
        # SECURITY - status=paid
        # update block_processed to irreversible block
        stake_paid(params)
        # SECURITY - pay nominator
        msg["response"] = json_loads(
            post_withdrawal_pybitshares(amount, nominator, memo, keys)
        )
        # SECURITY - status=confirmed
        # update block_processed to actual callback block
        block_num = 0
        try:
            block_num = int(msg["response"]["block_num"])
        except Exception as error:
            msg["error"] = exception_handler(error) + line_info()
        if block_num:
            params["block_num"] = block_num
            payment_confirmed(params)
    # something went wrong, send the nominator an IOU with support details
    # do not mark as paid, but add receipt to db
    else:
        memo = (
            f"your stakeBTS payment of {amount} failed for an unknown reason, "
            + f"please contact {EMAIL} "
            + f"BTSstake nonce {nonce} type {params['type']} {number}"
        )

        msg["response"] = json_loads(
            post_withdrawal_pybitshares(1, nominator, memo, keys)
        )
    msg["memo"] = memo
    msg["params"] = params
    update_receipt_database(nonce, json_dumps(msg))


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
    msg = {}
    msg["params"] = params
    msg["function"] = line_info()
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
                    msg["response"] = json_loads(
                        post_withdrawal_bittrex(qty, CUSTODIAN, api, keys)
                    )
                    update_receipt_database(nonce, json_dumps(msg))
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
                msg["warn"] = (
                    f"awaiting on funds from Bittrex for nonce {nonce}, "
                    + f"minutes elapsed {elapsed}",
                )
                print(it("purple", msg["warn"]))
                # wait up to 12 hours for bittrex funds to arrive
                if elapsed > 60 * 12:
                    msg["warn"] = f"Nonce {nonce} funds failed to arrive"
                    update_receipt_database(nonce, json_dumps(msg))
                    print(it("purple", msg["warn"]))
                    covered = False
                    break
    except Exception as error:
        msg["error"] = "cover payment failed" + exception_handler(error)
        update_receipt_database(nonce, json_dumps(msg))
    return covered


def payment_confirmed(params):
    """
    after payment child receives callback block number
    update the database for audit with the block containing the outbound transfer
    """
    # SECURITY process atomically
    # for every agreement associated with this payout
    queries = []
    for nonce in params["nonces"]:
        # for every applicable line item of that agreement
        for edit in params["edits"]:
            query = """
                UPDATE stakes SET block_processed=?,
                status='confirmed' WHERE nonce=?
                AND number=?
                AND type=?
            """
            values = (
                params["block_num"],
                nonce,
                params["number"],
                edit,
            )
            dml = {"query": query, "values": values}
            queries.append(dml)
    sql_db(queries)


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
                    it(
                        COLOR[2],
                        f"{time.ctime()} listener_bitshares() db:irr block {block_num}:"
                        + f"{get_block_num_current()}"
                    )
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
        now = munix_nonce()
        block_num = get_block_num_current()
        # read from database gather list of payments due in next 2 hours for ux
        query = """
            SELECT amount, status, nominator, due, number, type FROM stakes
            WHERE (type='base_amount' OR type='reward')
            AND status='pending'
            AND due<?
        """
        values = (now + 2 * MUNIX_HOUR,)
        payments_due_2h = sql_db(query, values)
        print(
            it(
                COLOR[4],
                f"{time.ctime()} listener_sql()       due next 2 hours "
                + f"{len(payments_due_2h)}",
            )
        )
        for payment in payments_due_2h:
            print(payment)
        # read from database gather list of payments due
        query = """
            SELECT amount, nominator, nonce, number, type FROM stakes
            WHERE (type='base_amount' OR type='reward')
            AND due<? AND status='pending'
        """
        values = (now,)
        payments_due = sql_db(query, values)
        # SECURITY: batch payment due and penalty queries and process them atomically
        queries = []
        # update base_amount and reward due status to processing
        query = """
            UPDATE stakes
            SET status='processing', block_processed=?, processed=?
            WHERE (type='base_amount' OR type='reward')
            AND due<? AND status='pending'
        """
        values = (block_num, now, now)
        dml = {"query": query, "values": values}
        queries.append(dml)
        # update penalties due to status aborted
        query = """
            UPDATE stakes
            SET status='aborted', block_processed=?, processed=?
            WHERE type='penalty' AND due<? AND status='pending'
        """
        values = (block_num, now, now)
        dml = {"query": query, "values": values}
        queries.append(dml)
        sql_db(queries)
        # make the payments due
        payment_parent(payments_due, keys)
        time.sleep(60)


def listener_balances(keys):
    """
    update receipts table with current account balances
    print some metadata on recent / upcoming payouts
    """
    now = munix_nonce()
    # get balances and update receipts
    balances = {0: get_balance_pybitshares()}
    balances.update(get_balance_bittrex(keys))
    msg = {"balances": balances}
    update_receipt_database(0, json_dumps(msg))
    # read from database gather list of payments due in next 24 hours
    query = """
        SELECT amount FROM stakes
        WHERE (type='base_amount' OR type='reward') AND due<? AND status='pending'
    """
    # use same query to sum amounts due in next 1, 7, and 30 days
    due_day = int(sum([i[0] for i in sql_db(query, (now + MUNIX_DAY,))]))
    due_week = int(sum([i[0] for i in sql_db(query, (now + MUNIX_WEEK,))]))
    due_month = int(sum([i[0] for i in sql_db(query, (now + MUNIX_MONTH,))]))
    # read from database total amount of ALL payments due
    query = """
        SELECT amount FROM stakes
        WHERE (type='base_amount' OR type='reward') AND status='pending'
    """
    due_total = int(sum([i[0] for i in sql_db(query)]))
    # gather list of payments that have been recently processed (48hr)
    query = """
        SELECT amount, status, nominator, processed, type, number FROM stakes
        WHERE processed>? AND processed<?
    """
    values = (now - 2 * MUNIX_DAY, now)
    payments_paid = sql_db(query, values)
    # read from database gather list of payments soon due (48hr)
    query = """
        SELECT amount, status, nominator, due, number, type FROM stakes
        WHERE (type='base_amount' OR type='reward')
        AND status='pending'
        AND due<?
    """
    values = (now + 2 * MUNIX_DAY,)
    payments_due = sql_db(query, values)
    # read from database gather list of payments past due
    query = """
        SELECT amount, status, nominator, due, type, number FROM stakes
        WHERE (type='base_amount' OR type='reward')
        AND status='pending'
        AND due<?
        AND processed>?
    """
    values = (now, now)
    payments_past_due = sql_db(query, values)
    # gather a list of nominators owed liabilities
    query = """
        SELECT nominator FROM stakes
        WHERE status='pending'
    """
    values = (now - 2 * MUNIX_DAY, now)
    nominators = list({i[0] for i in sql_db(query)})  # list(set([]))
    # begin user experience, print account balances
    print(it("purple", "balances"), balances)
    # provide ux of rolling liabilities
    print(
        it("purple", "liability gross:"),
        due_total,
        it("purple", "month:"),
        due_month,
        it("purple", "week:"),
        due_week,
        it("purple", "day:"),
        due_day,
    )
    # provide ux of recent payouts
    print(it("green", "items processed past 48 hours"), len(payments_paid))
    for payment in payments_paid:
        print([str(i).ljust(18) for i in payment])
    print(it("yellow", "items to process next 48 hours"), len(payments_due))
    for payment in payments_due:
        print([str(i).ljust(18) for i in payment])
    print(it("red", "payments past due"), len(payments_past_due))
    for payment in payments_past_due:
        print([str(i).ljust(18) for i in payment])
    # provide ux for nominator list
    print(it("blue", {"count": len(nominators), "nominators": nominators}))
    # provide ux of means to cover expenses
    if due_day > balances[0]:
        print(it("red", "WARN INSUFFICIENT FUNDS IN LOCAL WALLET FOR 24 HOUR EXPENSES"))
    if due_day > sum(balances.values()):
        print(it("red", "WARN INSUFFICIENT FUNDS IN ALL WALLETS FOR 24 HOUR EXPENSES"))
    if payments_past_due:
        print(it("red", "WARN INSUFFICIENT FUNDS AND PAST DUE PAYOUTS"))


def listener_balances_loop(keys):
    """
    about every 2 hours, refresh ux
    """
    while True:
        listener_balances(keys)
        time.sleep(7195)


def watchdog():
    """
    give visual indication of hung app
    """
    while True:
        print(time.ctime(), "watchdog()")
        time.sleep(600)


# PRIMARY EVENT BACKBONE
def welcome(keys):
    """
    UX at startup
    """
    print("\033c")
    print(it("yellow", LOGO))
    print(it("yellow", "=======================\nAUTOMATED PAYOUTS\n"))
    print(it(COLOR[2], f"\n{keys['custodian'].upper()} AUTHENTICATED\n"))
    msg = {}
    msg["initialize"] = {
        "node": NODE,
        "custodian": CUSTODIAN,
        "penalty": PENALTY,
        "reward": REWARD,
        "managers": MANAGERS,
        "invest amounts": INVEST_AMOUNTS,
        "confirm agreements": CONFIRM_AGREEMENTS,
        "min balance": MIN_BALANCE,
        "replay": REPLAY,
        "dev": DEV,
        "dev auth": DEV_AUTH,
        "admin replay": ADMIN_REPLAY,
        "make payments": MAKE_PAYMENTS,
        "database block": get_block_num_database(),
        "current block": get_block_num_current(),
        "time": time.ctime(),
        "munix": munix_nonce(),
    }
    update_receipt_database(0, json_dumps(msg))
    for key, val in msg["initialize"].items():
        print(it(COLOR[4], f"{key.ljust(19)}: {val}"))
    print("")
    # display developer mode, replay type, and current block number locally vs actual
    if DEV:
        print(it("red", "\n     *** DEVELOPER MODE ***\n\n"))
    if isinstance(REPLAY, bool):
        if REPLAY:
            print("start - REPLAY - from last block in database")
        else:
            print("start - NO REPLAY - from current block number")
            set_block_num_database(get_block_num_current())
    elif isinstance(REPLAY, int):
        print(f"start - REPLAY - from user specified block number {REPLAY}")
        # 59106023 tony-peacock created first legacy stake of 25000
        # 60692860 sune-3355 created last legacy stake of 50000
        if REPLAY < 59106000:
            raise ValueError(it("red", "WARN first stake was 59106023"))
        if REPLAY < 60693000:
            print(it("red", "WARN replaying legacy stakes, inspect database when done"))
        set_block_num_database(REPLAY - 1)


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
    login then begin while loop
    listening for nominator requests and making timely payouts
    """
    # backup the database, immediately and periodically
    thread_0 = Thread(target=db_backup)
    thread_0.start()
    time.sleep(1)
    # login ui / welcome ux
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
        thread_3 = Thread(target=listener_balances_loop, args=(keys,))
        thread_3.start()
    thread_4 = Thread(target=watchdog)
    thread_4.start()


if __name__ == "__main__":
    main()
