# Stake Machine


## Install instructions

Install SQLite3:
```shell
apt install -y sqlite3
```

Create and activate environment:
```shell
python3 -m venv env
source env/bin/activate
```

Install requirements into environment:
```shell
pip3 install -r requirements.txt
```

---

## Staking Logic

- 1 Stake per BitShares account
- 8% payout per month, 96% APY
- 3, 6, or 12 month stake
  - 2,592,000, 5,184,000, and 10,368,000 blocks, respectively
- Amount of 25k, 50k, 100k, or 200k BTS
- Withdrawal:
  - if past staking period, no fee deducted. send 1 BTS with "stop" memo
  - 15% penalty for early withdraw
  - send 1 BTS with the "stop" memo, you will have 15% deducted from your
    return
- No automatic transfer back if wrong amount
- No payout account balance check

### to-do
- Check for LTM
- Brainstorm receipt methods
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
