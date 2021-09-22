"""
BitShares.org StakeMachine
User Input
BitShares Management Group Co. Ltd.
"""

# USER DEFINED CONSTANTS
LOGO =  """
┌─┐┌┬┐┌─┐┬┌─┌─┐╔╗╔╦╗╔═╗
└─┐ │ ├─┤├┴┐├┤ ╠╩╗║ ╚═╗
└─┘ ┴ ┴ ┴┴ ┴└─┘╚═╝╩ ╚═╝"""
COLOR = [39, 117, 45, 81, 159] # bitshares logo colors
DB = "database/stake_bitshares.db"
NODE = ""
EMAIL = "complaints@stakebts.bitsharesmanagement.group"
CUSTODIAN = "bitsharesmanagement.group"
MANAGERS = ["dls.cipher", "escrow.zavod.premik"]
MIN_BALANCE = 100
BITTREX_ACCT = "bittrex-deposit"
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
DEV = False  # Ignore withdrawals, 99999999 balances, fake credentials when True
DEV_AUTH = False  # Use keys found in dev auth file? True=YES
ADMIN_REPLAY = False  # Perform admin transfers again during replay? True=YES
MAKE_PAYMENTS = True  # When False disables listener_sql and all withdrawals
CONFIRM_AGREEMENTS = True  # Send 1 BTS + memo for new transactions
