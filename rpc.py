"""
BitShares.org StakeMachine
Remote Procedure Calls to BitShares Node and Bittrex API
BitShares Management Group Co. Ltd.
"""
# DISABLE SELECT PYLINT TESTS
# pylint: disable=broad-except

# STANDARD PYTHON MODULES
import math
import time
from json import dumps as json_dumps

# PYBITSHARES MODULES
from bitshares.account import Account
from bitshares.bitshares import BitShares
from bitshares.dex import Dex
from bitshares.instance import set_shared_bitshares_instance
from bitshares.memo import Memo

# BITTREX MODULES
from bittrex_api import Bittrex

# STAKE BTS MODULES
from config import BROKER, DEV, MAKE_PAYMENTS, NODE
from utilities import exception_handler, it, line_info

NINES = 999999999

# CONNECT WALLET TO BITSHARES NODE
def pybitshares_reconnect():
    """
    create locked owner and memo instances of the pybitshares wallet
    :return: two pybitshares instances
    """
    pause = 0
    while True:
        try:
            bitshares = BitShares(node=NODE, nobroadcast=False)
            set_shared_bitshares_instance(bitshares)
            memo = Memo(blockchain_instance=bitshares)
            return bitshares, memo
        except Exception as error:
            print(exception_handler(error), line_info())
            time.sleep(0.1 * 2 ** pause)
            if pause < 13:  # oddly works out to about 13 minutes
                pause += 1
            continue


# RPC BLOCK NUMBER
def get_block_num_current():
    """
    connect to node and get the irreversible block number
    :return int(): block number
    """
    bitshares, _ = pybitshares_reconnect()
    return bitshares.rpc.get_dynamic_global_properties()["last_irreversible_block_num"]


# RPC POST WITHDRAWALS
def post_withdrawal_bittrex(amount, client, api, keys):
    """
    send funds using the bittrex api
    bittrex sends the amount requested less the tx fee, so tx fee is added
    :param int(amount): quantity to be withdrawn
    :param str(client): bitshares username to send to
    :param dict(keys): api keys and secrets for bittrex accounts
    :param int(api): 1, 2, or 3; corporate account to send from
    :return str(msg): withdrawal response from bittrex
    """
    fee = get_txfee_bittrex()
    amount = float(amount) + fee
    msg = f"POST WITHDRAWAL BITTREX {amount} {client} {api}, response: "
    print(it("yellow", msg))
    if MAKE_PAYMENTS and not DEV:
        try:
            if amount <= 0:
                raise ValueError(f"Invalid Withdrawal Amount {amount}")
            bittrex_api = Bittrex(
                api_key=keys[f"api_{api}_key"], api_secret=keys[f"api_{api}_secret"]
            )
            params = {
                "currencySymbol": "BTS",
                "quantity": str(float(amount)),
                "cryptoAddress": str(client),
            }
            # returns response.json() as dict or list python object
            ret = bittrex_api.post_withdrawal(**params)
            msg += json_dumps(ret)
            if isinstance(ret, dict):
                if "code" in ret:
                    print(it("red", ret), line_info())
                    raise TypeError("Bittrex failed with response code")
        except Exception as error:
            msg += line_info() + " " + exception_handler(error)
            msg += it("red", f"bittrex failed to send {amount} to client {client}",)
            print(msg)
    return msg


def post_withdrawal_pybitshares(amount, client, memo, keys):
    """
    send BTS with memo to confirm new stake from pybitshares wallet
    :param int(amount): quantity to be withdrawn
    :param str(client): bitshares username to send to
    :param dict(keys): contains pybitshares wallet password for corporate account
    :param str(memo): message to client
    :return str(msg): withdrawal response from pybitshares wallet
    """
    amount = int(amount)
    msg = f"POST WITHDRAWAL PYBITSHARES {amount} {client} {memo}, response: "
    print(it("yellow", msg))
    if MAKE_PAYMENTS and not DEV:
        try:
            if amount <= 0:
                raise ValueError(f"Invalid Withdrawal Amount {amount}")
            bitshares, _ = pybitshares_reconnect()
            bitshares.wallet.unlock(keys["password"])
            msg += json_dumps(
                bitshares.transfer(client, amount, "BTS", memo, account=keys["broker"])
            )  # returns dict
            bitshares.wallet.lock()
            bitshares.clear_cache()
        except Exception as error:
            msg += line_info() + " " + exception_handler(error)
            msg += it(
                "red",
                f"pybitshares failed to send {amount}"
                + f"to client {client} with memo {memo}, ",
            )
            print(msg)
    return msg


# RPC TRANSACTION FEE
def get_txfee_bittrex():
    """
    get transaction fee to send BTS from bittrex api
    :return float():
    """
    fee = float(5)  # default value as of Sept 1, 2021
    try:
        bittrex_api = Bittrex()
        params = {"currencySymbol": "BTS"}
        ret = bittrex_api.get_currencies(**params)
        fee = float(ret["txFee"])
    except Exception as error:
        print(exception_handler(error), line_info())
        print(it("red", f"returning default bittrex withdrawal fee of {fee}"))
    return fee


def get_txfee_pybitshares():
    """
    get transaction fee to send BTS from pybitshares wallet
    :return float():
    """
    fee = float(1.35129)  # default value including 1kb memo as of Sept 1, 2021
    try:
        bitshares, _ = pybitshares_reconnect()
        dex = Dex(blockchain_instance=bitshares)
        ret = dex.returnFees()
        fee = (
            ret["transfer"]["fee"] * 10 ** 5
            + ret["transfer"]["price_per_kbyte"] * 10 ** 5
        ) / 10 ** 5
    except Exception as error:
        print(exception_handler(error), line_info())
        print(it("red", f"returning default pybitshares withdrawal fee of {fee}"))
    return fee


# RPC GET BALANCES
def get_balance_bittrex(keys):
    """
    get bittrex BTS balances for all three corporate accounts
    NOTE: each balance is returned less withdrawal fee
    NOTE: each balance is returned rounded down as int() each api
    if api call fails, 0 balance is returned
    :param keys: dict containing api keys and secrets for 3 accounts
    :return dict(balances):format {1: 0, 2: 0, 3: 0}
    """
    fee = int(math.ceil(get_txfee_bittrex()))
    balances = {1: NINES, 2: NINES, 3: NINES}
    if not DEV:
        for api in range(1, 4):
            try:
                bittrex_api = Bittrex(
                    api_key=keys[f"api_{api}_key"], api_secret=keys[f"api_{api}_secret"]
                )
                # returns list() on success or dict() on error
                ret = bittrex_api.get_balances()
                if isinstance(ret, dict):
                    print(it("red", ret), line_info())
                # ret balance will be strigified float; int(float(()) to return integer
                balance = int(
                    float(
                        [i for i in ret if i["currencySymbol"] == "BTS"][0]["available"]
                    )
                )
                balance -= fee
                balances[api] = int(max(0, balance))
            except Exception as error:
                print(exception_handler(error), line_info())
                balances[api] = 0
    print("bittrex balances:", balances)
    return balances


def get_balance_pybitshares():
    """
    get the broker's BTS balance
    NOTE: balance is returned less withdrawal fee
    NOTE: balance is returned rounded down as int()
    :return int(): BTS balance
    """
    fee = int(math.ceil(get_txfee_pybitshares()))
    try:
        if DEV:
            balance = NINES
        else:
            _, _ = pybitshares_reconnect()
            account = Account(BROKER)
            balance = int(account.balance("BTS")["amount"])
            balance -= fee
    except Exception as error:
        print(exception_handler(error), line_info())
        balance = 0
    print("pybitshares balance:", balance)
    return balance


def authenticate(keys):
    """
    make authenticated request to pybitshares wallet and bittrex to test login
    :param dict(keys): bittrex api keys and pybitshares wallet password
    :return bool(): do all secrets and passwords authenticate?
    """
    bitshares, _ = pybitshares_reconnect()
    try:
        bitshares.wallet.unlock(keys["password"])
    except Exception:
        pass
    bitshares_auth = bitshares.wallet.unlocked()
    if bitshares_auth:
        print("PYBITSHARES WALLET AUTHENTICATED")
    else:
        print("PYBITSHARES WALLET AUTHENTICATION FAILED")
    bitshares.wallet.lock()
    bittrex_auth = {1: False, 2: False, 3: False}
    try:
        for i in range(3):
            api = i + 1
            bittrex_api = Bittrex(
                api_key=keys[f"api_{api}_key"], api_secret=keys[f"api_{api}_secret"]
            )
            ret = bittrex_api.get_balances()
            if isinstance(ret, list):
                bittrex_auth[api] = True
    except Exception:
        pass
    if all(bittrex_auth.values()):
        print("BITTREX API SECRETS AUTHENTICATED:", bittrex_auth)
    else:
        print("BITTREX API SECRETS FAILED:", bittrex_auth)
    return bitshares_auth and all(bittrex_auth.values())
