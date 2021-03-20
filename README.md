# Stake Machine
```SH
apt install -y sqlite3
```

```SH
pip3 install bitshares uptick
```

---

- 3 or 6 month stake
  - 2592000 blocks and 5184000 blocks, respectively
- Amount of 10k, 20k, or 50k BTS
- 15% penalty for early withdraw
  - send 1 BTS with the "stop" memo, you will have 15% deducted from your
    return
  - if past staking period, no fee deducted. send 1 BTS with "stop" memo

---

## JSON Format for Transfer
```JSON
{
  "type": "<LENGTH_OF_STAKE>"
}
```
`LENGTH_OF_STAKE` = "three_months", or "six_months" (with quotation marks). Other option: "stop"

### Valid JSON examples:
```JSON
{
  "type": "three_months"
}
```
```JSON
{
  "type": "six_months"
}
```
```JSON
{
  "type": "stop"
}
```
