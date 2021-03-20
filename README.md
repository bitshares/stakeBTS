# Stake Machine
```apt install -y sqlite3```

```pip3 install bitshares uptick```

---

- 3 or 6 month stake
  - 2592000 blocks and 5184000 blocks, respectively
- Amount of 10k, 20k, or 50k BTS
- 15% penalty for early withdraw
  - send 15% of your stake in a transfer with the "stop" memo
  - if past staking period, send 1 BTS with the "stop" memo

---

## JSON Format
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
