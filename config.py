"""
BitShares.org StakeMachine
User Input
BitShares Management Group Co. Ltd.
"""

# USER DEFINED CONSTANTS
DB = "database/stake_bitshares.db"
NODE = "wss://bitshares.bts123.cc:15138"
EMAIL = "complaints@stakebts.bitsharesmanagement.group"
CUSTODIAN = "bitsharesmanagement.group"
MANAGERS = ["dls.cipher", "escrow.zavod.premik"]
BITTREX_ACCT = ""
BITTREX_1 = ""  # deposit memo account 1
BITTREX_2 = ""  # deposit memo account 2
BITTREX_3 = ""  # deposit memo account 3
REWARD = 0.08
PENALTY = 0.15
INVEST_AMOUNTS = [
    25000,
    50000,
    100000,
    200000,
    250000,
    500000,
    1000000,
    2500000,
    5000000,
    10000000,
]
# REPLAY #
# True : start from block number last checked in database
# False : start from current block number
# int() : start from user specified block number
REPLAY = False

# UNIT TESTING MODE
DEV = False  # Ignore withdrawals, 99999999 balances, fake credentials when True
DEV_AUTH = True  # Use keys found in dev auth file? True=YES
ADMIN_REPLAY = False  # Perform admin transfers again during replay? True=YES
MAKE_PAYMENTS = False  # When False disables listener_sql and all withdrawals

