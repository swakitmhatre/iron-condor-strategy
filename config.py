# config.py

# Dhan credentials
DHAN_API_TOKEN = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzUxMiJ9.eyJpc3MiOiJkaGFuIiwicGFydG5lcklkIjoiIiwiZXhwIjoxNzU0OTI0MTYyLCJ0b2tlbkNvbnN1bWVyVHlwZSI6IlNFTEYiLCJ3ZWJob29rVXJsIjoiIiwiZGhhbkNsaWVudElkIjoiMTEwMDkyMjIyNiJ9.YcY7_aIOuhDBQ9VD3yyfz9eIMnDcD3o3aEgwfR38q4ZRJ2Vkdl44103dIZIdibk0kilRUeA451LH9mBHQjra4A"
DHAN_CLIENT_ID = "1100922226"
DHAN_BASE_URL = "https://api.dhan.co"

# Telegram
TELEGRAM_BOT_TOKEN = "7770202577:AAHjZFGJg2Gt3c5S77i__SOCMVqRXd6ofY0"
TELEGRAM_CHAT_ID = "1872844861"

# Strategy logic
STRATEGY_MARGIN = 150000  # for one Iron Condor lot
MTM_TARGET_PCT = 0.002  # 0.20%
ENTRY_START_TIME = (9, 20)
ENTRY_END_TIME = (10, 30)


'''
# config.py

# Dhan credentials
DHAN_ACCESS_TOKEN = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzUxMiJ9.eyJpc3MiOiJkaGFuIiwicGFydG5lcklkIjoiIiwiZXhwIjoxNzU0OTI0MTYyLCJ0b2tlbkNvbnN1bWVyVHlwZSI6IlNFTEYiLCJ3ZWJob29rVXJsIjoiIiwiZGhhbkNsaWVudElkIjoiMTEwMDkyMjIyNiJ9.YcY7_aIOuhDBQ9VD3yyfz9eIMnDcD3o3aEgwfR38q4ZRJ2Vkdl44103dIZIdibk0kilRUeA451LH9mBHQjra4A"
DHAN_CLIENT_ID = "1100922226"

# Telegram credentials
TELEGRAM_BOT_TOKEN = "7770202577:AAHjZFGJg2Gt3c5S77i__SOCMVqRXd6ofY0"
TELEGRAM_CHAT_ID = "1872844861"

# MTM and risk settings
STRATEGY_MARGIN = 130000  # Total margin for 1-lot iron condor (adjust if different)
MTM_TARGET_PERCENT = 0.20  # 0.20% of margin = ₹260 target profit
MTM_STOPLOSS_PERCENT = None  # Add later if needed (e.g., 0.30)

# Entry time window
ENTRY_START_TIME = "09:20"
ENTRY_END_TIME = "10:30"

# Option sell leg width (distance from ATM)
WING_WIDTH = 300

# Force expiry to next week always
FORCE_NEXT_WEEK_EXPIRY = True

# Delay between retries (in seconds) if API fails
RETRY_DELAY = 2
MAX_RETRIES = 3
'''
