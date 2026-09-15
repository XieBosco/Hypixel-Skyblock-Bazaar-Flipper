# API Loop
API_URL = "https://api.hypixel.net/v2/skyblock/bazaar"
CHECK_INTERVAL = 10 # Seconds between API checks

# GUI Slots
SLOT_CANCEL_BUY = 11
SLOT_CANCEL_SELL = 13
SLOT_BUY_ORDER = 15
SLOT_SELL_OFFER = 16

SLOT_BUY_SMALL = 10
SLOT_BUY_MEDIUM = 12
SLOT_TOP_ORDER_P01 = 12
SLOT_CONFIRM_BUY = 13

SLOT_SELL_OFFER_M01 = 12
SLOT_CONFIRM_SELL = 13

# Limits

MAX_BUY_COST = 50000000

# Delays
HUMAN_WPM = 180

# --- Constants for get_best_product.py ---

DAILY_BZ_LIMIT = 15000000000 # 15 billion

# --- Messages when bz limit is reached ---

BZ_LIMIT_MSG_1 = "[Bazaar] You reached the daily limit in items value that you may sell on the bazaar!"
BZ_LIMIT_MSG_2 = "[Bazaar] You reached the daily limit of coins you may create orders for on the Bazaar!"

# --- Limbo message ---

LIMBO_MSG = "You were spawned in Limbo."

# --- Server reboot message ---

SERVER_REBOOT_MSG = "[Important] This server will restart soon: Scheduled Reboot"

# Tax in decimal format
TAX_RATE = 0.02

# Assumed renewal time for an outdated order in seconds
RENEWAL_TIME = 30
AVERAGE_COMPETITOR_RENEWAL = 600

# instant_buy_weekly = IBW
# instant_sell_weekly = ISW
IBW_THRESHOLD = 500
ISW_THRESHOLD = 500