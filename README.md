# StakeBTS Python Bot

## Install instructions

**Install SQLite3:**
```shell
apt install -y sqlite3
```

**Create investment.db from db_setup.txt file:**

```sqlite3 investment.db```

(Copy/paste content of db_setup.txt)

```.quit```

**Create and activate environment:**
```shell
python3 -m venv env
source env/bin/activate
```

**Install requirements into environment:**
```shell
pip3 install -r requirements.txt
```

**NOTICE: UPTICK is a must to operate bot properly. Account that you wish to use for the bot must be imported with all 3 private keys (Owner, Active and Memo) into the uptick. On BOT start 
you will be asked to enter WALLET password from the uptick.**

---

## Staking Logic

- 1 Stake per 1 BitShares account
- 8% payout per month, up to 96% APY
- 3, 6, or 12 month stake options.
  - 2,592,000, 5,184,000, and 10,368,000 blocks, respectively
- Basic Stake Amounts of 25,000 BTS, 50,000 BTS, 100,000 BTS, 200,000 BTS available for stake. 
- High Stake Amounts 500,000 BTS, 750,000 BTS, 1,000,000 BTS, 2,500,000 BTS, 5,000,000 BTS, 10,000,000 BTS added and available for stake. 
- Withdrawal:
  - if past staking period, no fee deducted, automatic return of the base staked
  - Early withdrawals - send 1 BTS with the {"type":"stop"} memo, you will have 15% deducted from base as penalty for braking agreement.
- Automatic payout transfers monthly (every 30 days, 0 hours and 1 minute)
- No automatic transfer back if wrong amount
- No transfer back if user already has a stake
- No payout account balance check

---

## JSON Format

```JSON
{"type":"<LENGTH_OF_STAKE>"}
```
`LENGTH_OF_STAKE`
- "three_months"
- "six_months"
- "twelve_months"
- "stop"

### Valid JSON examples:
```JSON
{"type":"three_months"}
```
```JSON
{"type":"six_months"}
```
```JSON
{"type":"twelve_months"}
```
```JSON
{"type":"stop"}
```


This software is sponsored and managed by BitShares Management Group Limited
