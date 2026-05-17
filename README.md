# ForgeStore — Palworld Plugin

Python script for Palworld dedicated servers. Uses the official Palworld REST API (v0.7.2) with Basic Auth to deliver purchases automatically.

## Requirements
- Python 3.8+
- Palworld server with `RESTAPIEnabled=True` in PalWorldSettings.ini
- pip install requests

## Setup
1. Set `RESTAPIEnabled=True` and `RESTAPIPort=8212` in `PalWorldSettings.ini`
2. Set `RESTAPIPassword=your_password`
3. Edit the CONFIG section at the top of `forgestore_palworld.py`
4. Run: `python3 forgestore_palworld.py`

## Config
```python
FORGESTORE_API_KEY  = "your_api_key"
FORGESTORE_STORE_ID = "your_store_id"
PALWORLD_HOST       = "http://127.0.0.1"
PALWORLD_PORT       = 8212
PALWORLD_PASSWORD   = "your_rest_password"
```

## Support
- Discord: discord.gg/km6buD6DeK
- Docs: forgestore.net/docs/plugin-api
