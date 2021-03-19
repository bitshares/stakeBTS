```
{"type":LENGTH_OF_STAKE}
```
```
{
    "type": LENGTH_OF_STAKE
}
```
`LENGTH_OF_STAKE` = "day", "week", or "month" (with quotation marks). Other options: "stop", "funding"

```json
{"type":"stop","length":"day"}
```
```json
{
    "type": "stop",
    "length": "day"
}
```

Length indicates which type of stake you would like to remove. This removes all stakes of chosen type.

```json
{"type":"funding"}
```
```json
{
    "type": "funding"
}
```

This allows for funding of the bot without having to worry about it being returned.
