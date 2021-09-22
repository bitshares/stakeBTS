# StakeBTS Python Bot

`APP VERSION`

**v2.4**

`PYTHON VERSION`

**3.8+**

`PYTHON REQUIREMENTS`

 - bitshares
 - uptick
 - requests

`LICENSE`

## BIPCOT v1.2 www.bipcot.org

`RELEASE STATUS`

### Unit Tested, Feature Complete Release Candidate

`DESCRIPTION`

Recurring reward and base_amount payment automation
for bitsharesmanagement.group to stakeBTS nominators

`INSTALLATION`

**Install SQLite3:**

```
sudo apt install -y sqlite3
```

**Create and activate environment:**

```
sudo apt-get install python3-venv
python3 -m venv env
source env/bin/activate
```

**Install requirements into environment:**

```
pip3 install -r requirements.txt
```

**Restart the database**

Run:

`python3.8 db_setup.py`

input "y" then press Enter

It will:

 - delete any existing db
 - create database folder
 - Create stake_bitshares.db
 - set up the tables
 - check the schema and that the stake table is empty

**Next we'll replay the blocks containing legacy agreements**

in dev_auth.py input your credentials to these user specified CONSTANTS:

```
CUSTODIAN = ???
PASSWORD = ???
```

These credentials are required to decode the memos,

you can leave the other three dev_auth.py credentials blank at this time


Next, in config.py set these constants:

```
DEV = False
DEV_AUTH = True
ADMIN_REPLAY = False
MAKE_PAYMENTS = False
```

Next, run:

```
python3.8 import_data.py
```

It will:

 - Replay blocks where legacy contracts were created and set them up in the database

 - mark all manual payments to date paid on June 30, July 31, and Aug 31

At this point you should view the contents of the stakes table:

```
sqlite3 database/stake_bitshares.py
SELECT * FROM stakes;
.quit
```

It should display 25 legacy agreements + all recent additional agreements

They should now be updated with all manual payments marked as paid


If there are any additional agreements not yet entered

in config.py set replay to 2 less than the block they occur in:

```
REPLAY = ???
```

Then run:

`python3.8 stake_bitshares.py`

It will pick up the agreements and add them to the db.

You can stop the script a few blocks later.

`ctrl + \`

Repeat this process for any additional agreements you need to import

### NOTE: CAREFULLY REVIEW THIS DATA FOR ACCURACY!!!

finally we'll run the app from the current block:

in dev_auth.py delete your credentials for security

in config.py set these user specified CONSTANTS:

```
DEV = False
DEV_AUTH = False
ADMIN_REPLAY = False
MAKE_PAYMENTS = True
REPLAY = False
```

in config.py, also...

be sure you have entered `NODE`

finally, enter the 3 `BITTREX_N` deposit memos

It is important here that you keep them ordered the same

as your api keys and secrets for each, eg:

```BITTREX_1 = API_1_KEY = API_1_SECRET```

you'll be prompted via script for keys and secrets shortly


**Run app**

```
python3.8 stake_bitshares.py
```

You will be prompted for all credentials, pybitshares and bittrex

### The bot will now automate payments


`
CHANGELIST v2.0
`

 - previously payouts were occurring at end of month
 - all future payouts will occur in 30 day intervals from beginning of agreement
 - if you were paid early previously this may mean up to 59 days until next payout
 - all payout amounts will be rounded down to nearest whole bitshare
 - user will receive receipt as memo w/ 1 BTS upon creating a new agreement
 - all payouts will come from bitsharesmanagement.group
 - in the event of payout failure, 1 BTS will be sent with additional support info
 - nominator sends an invalid amount or invalid memo he will be refuned less 50 BTS penalty
 - manager can use bot to transfer funds to and from bittrex to custodianage account
 - manager can use bot to personally loan funds to the custodianage account
 - new database format, all payouts are added to database at start of agreement
 - new database format, all outbound payment details are kept as receipts
 - in the event custodianage account is low on funds, bot will pull from bittrex accounts
 - all current payouts due are grouped into a thread
 - each individual payout is also a thread
 - apscheduler has been replaced by a custom database items due listener
 - approved admin must be lifetime members of BitShares to run the bot

`
CHANGELIST v2.2
`

 - post withdrawal and get balances now account for fees
 - new trx_idx and ops_idx allow for multiple stakes from one user in same block
 - new initiation procedure gathers accurate block number for legacy agreements

`
CHANGELIST v2.3
`

 - nominator reward agreements are due from original blocktime, not database time

`
CHANGELIST v2.4
`

 - receipt messages are json
 - improved ux, additional color and formatting
 - added metadata on upcoming and past liabililities
 - outgoing transfers updated with callback block number


`NOTES`

 - Requires creation of uptick wallet w/ `CUSTODIAN`'s `Acitve` and `Memo` keys
 - On BOT start you will be asked to enter your uptick WALLET password
 - Bittrex api is used for outbound payments.
 - You must also have Bittrex API key/secret.
 - This will be repeated for all 3 Bittrex corporate accounts.
 - All timestamps are integers in milleseconds
 - All amounts of funds stored in DB and sent are integers of BTS
 - Nothing is ever removed from the database

`NOMINATOR JSON FORMAT`

{"type":"MEMO_OPTIONS"}

`MEMO OPTIONS`

nominator memo options

 - `three_months`
 - `six_months`
 - `twelve_months`
 - `stop`

admin memo options (requires LTM account AND nominator being in MANAGER list)

 - `bmg_to_bittrex`
 - `bittrex_to_bmg`
 - `loan_to_bmg`

if need be visit https://jsonlint.com/ to confirm you have created legit json

the bot will also accept non json formatted nominator memos eg; `six_months` would be sufficient

it will also attempt to be kind to some silly errors, eg:

 - `'   six_months `
 - `six_months  '`
 - `"six_months"`
 - `'six_months'`
 - `"si x_ mon  ths"`

should all parse, but other errors will be charged a fee...

`FEES`

The bot charges a fee of 50 BTS and returns your funds if:

 - sending invalid stake amount
 - sending invalid memo
 - sending admin request without being in MANAGER list
 - sending admin loan_to_bmg without lifetime member (LTM) status on your account
 - bot ignores bittrex to bmg and vice versa transfer requests if not LTM

`DATABASE`

```
CREATE TABLE block (
    block INTEGER           # bitshares block number last checked by bot
);
```

 - NOTE all payments *potentially* due
 - are entered into "stakes" TABLE at start of agreement
 - as events unfold, their "status", "block", and "processed" time changes

```
    CREATE TABLE stakes (
        nominator TEXT             # bitshares user name for nominator
        digital_asset TEXT              # bitshares asset name
        amount INTEGER          # amount of asset rounded to nearest integer
        type TEXT               # agreement, base_amount, penalty, or reward
        start INTEGER           # munix start time of agreement
        due INTEGER             # munix due date of this payment
        processed INTEGER       # munix time at which payment was actually processed
        status TEXT             # pending, paid, aborted, or premature
        block_start INTEGER     # bitshares block number upon stake creation
        trx_idx INTEGER         # unique transaction index
        ops_idx INTEGER         # unique operation index
        block_processed INTEGER # bitshares block number upon payment
        number INTEGER          # counting number for reward payments, eg 1,2,3,4...
        UNIQUE (                # unique prevents duplicate stakes in the db
            nominator, type, number, block_start, trx_idx, ops_idx
            ) ON CONFLICT IGNORE
    );
```

 - receipts will hold transaction details for all incoming and outgoing tx's

```
    CREATE TABLE receipts (
        nonce INTEGER           # munix start time of agreement (same as 'stakes/start')
        now INTEGER             # munix moment when event occurred
        msg TEXT                # receipt details for audit trail
    );
```

 - add a dummy block number into the block_num database

```
INSERT INTO block_num (block_num) VALUES (59120000); # the initial starting block
```

`preexisting_agreements.py and import_data.py`

preexisting_agreements.py houses a single global constant of block text in format:

```
username milliseconds_unix amount agreement_length months_paid
```

can be tab or space delimited, eg:

```
    STAKES = """
        user1233 1623177720000 25000 12 2
        user9043 1623176546500 50000  3 2
    """
```
import_data.py moves those existing agreements to the database in the same

manner as all other agreements thereafter.

`DISCUSSION`
 ```
The stakeBTS is 2 listeners with withdrawal priviledges
communicating via sql database.
1) bitshares block operation listener:
    listens for new nominator stakes
        sends stake confirmation (withdrawal)
        inputs potential stake payouts to database
    listens for cancelled nominator stakes
        ends stakes prematurely paying base_amount less penalty (withdrawal)
        updates database accordingly and aborts further reward payments
2) payment due sql database listener:
    listens for pending items past due
    pays reward and base_amount on due time (withdrawal)
    if penalty becomes due its aborted

a nominator approaches bmg w/ a new stake the bot creates database rows
for every potential outcome of that stake;
there will always be 3 + number of months rows created.
agreement_n, base_amount, penalty, reward, reward, reward, etc.
and reward payments will be numbered,
agreement will always be for amount 1, and penalty will always be negative.
every payment, regardless of type, will have a due date upon creation...
agreement is always due on day of creation.
base_amount and penalty are always due at close of agreement.
reward is due in ascending 30 day periods.
for example a 100000 3 month agreement has 6 lines

1) type=agreement_3 amount=1 status=paid number=0
2) type=base_amount amount=100000 status=pending number=0
3) type=penalty amount=-15000 status=pending number=0
4) type=reward amount=8000 status=pending number=1
5) type=reward amount=8000 status=pending number=2
6) type=reward amount=8000 status=pending number=3

this is the stake rows of 3 month agreement -
there are also additional columns for timestamps, etc...
but we'll skip them for now just to have discussion
so whether a new user approaches... or we put old agreements into the database...
if its a 3 month agreement there are 6 db entries
(6 month agreement has +3 entries and
12 month agreement has +6 entries to account for additional reward payments)
in the case of new user...
as each pending item approaches its due date, it will be processed.

The bot (aside from being a block ops listener)
is also effectively a "database listener"
looking for status=pending where time due < now.

1) if reward becomes due its paid.
2) if the penalty comes due it is aborted and final base_amount+reward is paid.
3) if the user takes base_amount prior to due...

then pending reward are aborted
and the (negative) penalty is paid against the base_amount.
in the case of an existing "old" agreement...
it is uploaded in the database the exact same way;
but automated/simulated by script to run through the text document containing them...
rather than via "block ops listener".
additionally... the import old data script goes in and overwrites the "pending" status
 on the 1st (or 1st and 2nd) reward payment to "paid"
 so that it does not get processed again by the main script.
it uses the number column in the database to update the correct payment
and marks them processed on june 30 or july 31 of this year
this happens once prior to the main script startup you'll have to run import_data.py
to build the initial database of old agreements. It

1) adds all line items for each old agreement and
2) marks those already manually processed as paid.

then when you start running the main script full time...
the 3rd final payout of an old agreement (some cases 2nd and 3rd)
will still be a pending item in the database to be processed.
It will either pay it as it comes due...
or if taken prematurely it will abort it
and return base_amount less penalty as it would with any other stake.

Once the main bot is running
it won't know the difference between old agreements and new.
it just sees "pending" vs "paid/aborted" line items
```

`RESET DATABASE`

 - `python3.8 db_setup.py`

`UNIT TESTING CHECKLIST`

### 1) BALANCES AND WITHDRAWALS

 - in a seperate script import withdrawal and balances definitions:
 - unit test `post_withdrawal_bittrex()` and `post_withdrawal_pybitshares()`
 - unit test `get_balance_bittrex()` and `get_balance_pybitshares()`

### 2) BLOCK OPERATIONS LISTENER

 - reset database
 - in config.py set `DEV = True`
 - send 0.1 BTS to custodian, ensure script hears it arrive to the `CUSTODIAN` account.
 - check state of `receipts` and `stakes` database tables

### 3) DATABASE LISTENER

 - in config.py set `DEV = True`
 - reset database
 - load old agreements:
 - - `python3.8 import_data.py`
 - print database contents:
 - - `sqlite3 stake_bitshares.db`
 - - `SELECT * FROM stakes;`
 - run
 - - `python3 stake_bitshares.py`
 - in a second terminal via sql, change the due date on a single payment to 0,
 - see that it gets paid
 - - `sqlite3 stake_bitshares.db`
 - - `UPDATE stakes SET due=0 WHERE nominator='user1234' AND number=6;`
 - check state of `receipts` and `stakes` database tables

### 4) REPLAY BLOCKS

 - reset database
 - in config.py set `DEV = True`
 - in config.py test True, False, int() of `REPLAY`
 - ensure script starts at correct block number
 - script should not create duplicates in stakes database when replaying
 - check state of `receipts` and `stakes` database tables

### 5) NOMINATOR MEMOS

 - reset database
 - with config.py set `DEV = False` and `100` added to the list of `INVEST_AMOUNTS`
 - send an invalid amount `99`
 - send an invalid memo `fail_memo`
 - send a valid amount `100` and valid memo to start a new stake
 - send memo to `stop` a stake

### 6) ADMIN MEMOS

 - using a `MANAGER` account test admin memos (with and without `LTM`)
 - `bmg_to_bittrex`
 - `bittrex_to_bmg`
 - `loan_to_bmg`
 - check state of `receipts` and `stakes` database tables

### 7) BITTREX COVER

 - reset database
 - send 1000 BTS to Bittrex
 - with config.py set `DEV = False` and `100` added to the list of `INVEST_AMOUNTS`
 - insert line item in `stakes` table with amount ~500 BTS more than balance of CUSTODIAN:
 - - `INSERT INTO`
 - - `stakes`
 - - `(nominator, digital_asset, amount, type, start, due, processed, status, block_start, block_processed, number)`
 - - `VALUES`
 - - `('user1234', 'BTS', BALANCE_CUSTODIAN, 'reward', 0, 0, 0, 'pending', 0, 0, 1)`
 - empty the custodian account
 - send memo to `stop` a stake
 - bot should move funds from bittrex to pybitshares wallet, then to nominator to cover
 - ideally this should be tested with various amounts in all 3 Bittrex wallets

`FEATURES`

 - automatically move funds from bittrex to hot wallet to cover payments due
 - does not allow non-ltm users to administrate
 - allows replay from current block, last block in database, or user specified block.
 - prevents double entries during replay

`WARNING`

This software is provided without warranty.

Automating withdrawals is inherently exploit prone.

Conduct an security review commensurate with your investment.

`SPONSOR`

This software is sponsored and managed by BitShares Management Group Limited

 - https://bitsharesmanagement.group
 - https://bitsharestalk.org
 - https://bitshares.org

`TRADEMARK`

2014-2021. BitShares, and any associated logos are trademarks,

service marks, and/or registered trademarks of Move Institute, Slovenia.

`DEVELOPERS`

v1.0 initial prototype

 - iamredbar: iamredbar@protonmail.com https://github.com/iamredbar

v2.0 refactor, refinement, added features

 - litepresence: finitestate@tutamail.com https://github.com/litepresence

`COMMENTS, COMPLAINTS, other ISSUES`

If you are a current or prospective `bitshares management group`

nominator with any concerns or would like to confidentially report

security vulnerabilities, please contact:

complaints@stakebts.bitsharesmanagement.group
