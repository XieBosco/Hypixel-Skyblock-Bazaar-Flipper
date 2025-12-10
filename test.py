import minescript
import json
import re
import time
import threading
import urllib.request
from enum import Enum

# --- Configuration ---
API_URL = "https://api.hypixel.net/v2/skyblock/bazaar"
CONVERSIONS_URL = "https://raw.githubusercontent.com/symt/BazaarNotifier/master/discord-bot/src/bazaar/bazaarConversions.json"
CHECK_INTERVAL = 10  # Seconds

# --- Data Structures ---
class OrderType(Enum):
    BUY = "Buy Order"
    SELL = "Sell Offer"

class Order:
    def __init__(self, product_id, product_name, amount, price, order_type):
        self.product_id = product_id
        self.product_name = product_name
        self.amount = amount
        self.price = price
        self.order_type = order_type
        self.status = "SEARCHING"

    def __repr__(self):
        return f"<{self.order_type.name} {self.product_name} x{self.amount} @ {self.price}>"

# --- Global State ---
orders = []
orders_lock = threading.Lock()
name_to_id = {}
message_queue = [] # Queue for thread to send messages to main loop

# --- Helpers ---
def log_msg(msg):
    """Queue a message to be printed to chat by the main loop."""
    message_queue.append(msg)

def load_conversions():
    global name_to_id
    try:
        # Try fetching from URL
        with urllib.request.urlopen(CONVERSIONS_URL) as url:
            data = json.loads(url.read().decode())
            # The JSON is ID -> Name. We need Name -> ID.
            name_to_id = {v.lower(): k for k, v in data.items()}
            log_msg(f"Loaded {len(name_to_id)} bazaar conversions.")
    except Exception as e:
        log_msg(f"Error loading conversions: {e}")
        # Fallback: Add some common ones manually if needed, or rely on exact matches
        name_to_id = {}

def get_product_id(name):
    clean_name = name.lower().strip()
    return name_to_id.get(clean_name)

def parse_price(price_str):
    return float(price_str.replace(",", ""))

# --- Bazaar Logic ---
def check_bazaar():
    """Runs in a separate thread to avoid freezing the game."""
    while True:
        try:
            if not orders:
                time.sleep(CHECK_INTERVAL)
                continue

            with urllib.request.urlopen(API_URL) as url:
                data = json.loads(url.read().decode())

            if not data.get('success'):
                log_msg("Bazaar API failed.")
                time.sleep(CHECK_INTERVAL)
                continue

            products = data['products']
            
            with orders_lock:
                for order in orders:
                    if order.product_id not in products:
                        continue

                    product_data = products[order.product_id]
                    
                    # Logic:
                    # BUY Order competes with 'sell_summary' (Buy Orders)
                    # SELL Offer competes with 'buy_summary' (Sell Offers)
                    market_list = []
                    if order.order_type == OrderType.BUY:
                        market_list = product_data['sell_summary']
                    else:
                        market_list = product_data['buy_summary']

                    if not market_list:
                        continue

                    top_order = market_list[0]
                    top_price = top_order['pricePerUnit']
                    
                    new_status = order.status
                    
                    if order.order_type == OrderType.BUY:
                        if order.price < top_price:
                            new_status = "OUTDATED"
                        elif order.price == top_price:
                            # Check if we are the only one (volume check could be added here)
                            new_status = "BEST" 
                        else:
                            new_status = "BEST" # Overpaying is still "Best" position
                    else: # SELL
                        if order.price > top_price:
                            new_status = "OUTDATED"
                        elif order.price == top_price:
                            new_status = "BEST"
                        else:
                            new_status = "BEST" # Undercutting is still "Best" position

                    if new_status != order.status:
                        color = "red" if new_status == "OUTDATED" else "green"
                        log_msg(f"Order Update: {order.product_name} is now {new_status} (Top: {top_price})")
                        order.status = new_status

        except Exception as e:
            # log_msg(f"Bazaar check error: {e}")
            pass
        
        time.sleep(CHECK_INTERVAL)

# --- Chat Parsing ---
def process_chat(message):
    # Strip color codes (Minescript usually gives plain text in event.message, but just in case)
    # Regexes based on Hypixel messages
    
    # 1. Buy Order Setup
    # "Buy Order Setup! Buying 64x Enchanted Iron for 1,200.5 coins each."
    buy_setup = re.search(r"^Buy Order Setup! Buying ([\d,]+)x (.+) for ([\d,.]+) coins each\.", message)
    if buy_setup:
        amount = int(buy_setup.group(1).replace(",", ""))
        name = buy_setup.group(2)
        price = parse_price(buy_setup.group(3))
        pid = get_product_id(name)
        if pid:
            with orders_lock:
                orders.append(Order(pid, name, amount, price, OrderType.BUY))
            minescript.echo(f"§a[BN] Tracking Buy Order: {name}")
        else:
            minescript.echo(f"§c[BN] Unknown item: {name}")
        return

    # 2. Sell Offer Setup
    # "Sell Offer Setup! Selling 1x Hyperion for 1,000,000,000 coins each."
    sell_setup = re.search(r"^Sell Offer Setup! Selling ([\d,]+)x (.+) for ([\d,.]+) coins each\.", message)
    if sell_setup:
        amount = int(sell_setup.group(1).replace(",", ""))
        name = sell_setup.group(2)
        price = parse_price(sell_setup.group(3))
        pid = get_product_id(name)
        if pid:
            with orders_lock:
                orders.append(Order(pid, name, amount, price, OrderType.SELL))
            minescript.echo(f"§a[BN] Tracking Sell Offer: {name}")
        else:
            minescript.echo(f"§c[BN] Unknown item: {name}")
        return

    # 3. Order Filled
    # "[Bazaar] Your Sell Offer for 64x Enchanted Iron was filled!"
    filled = re.search(r"^\[Bazaar\] Your (Buy Order|Sell Offer) for ([\d,]+)x (.+) was filled!", message)
    if filled:
        o_type_str = filled.group(1)
        amount = int(filled.group(2).replace(",", ""))
        name = filled.group(3)
        o_type = OrderType.BUY if "Buy" in o_type_str else OrderType.SELL
        
        # Remove the matching order
        with orders_lock:
            for i, order in enumerate(orders):
                if order.product_name.lower() == name.lower() and order.order_type == o_type:
                    # In a real scenario, we might only remove part of the amount
                    # But for simplicity, we assume full fill or remove the tracked order
                    # To be more precise, we should decrement amount.
                    if order.amount <= amount:
                        orders.pop(i)
                        minescript.echo(f"§e[BN] Order filled & removed: {name}")
                    else:
                        order.amount -= amount
                        minescript.echo(f"§e[BN] Order partially filled: {name} ({order.amount} left)")
                    break
        return

    # 4. Cancelled
    # "[Bazaar] Cancelled!" followed by details usually, but sometimes on one line?
    # The Java code handles "Cancelled!" start.
    # Let's assume standard format:
    # "Cancelled! Refunded 1,200 coins from cancelling Buy Order for 64x Enchanted Iron!"
    # Or similar. Hypixel messages vary.
    # Simple approach: If we see "Cancelled", we might need to re-sync or just warn.
    # Since parsing cancellation is complex without exact messages, we'll skip for now or add a generic handler.
    if message.startswith("Cancelled!") or message.startswith("[Bazaar] Cancelled!"):
        minescript.echo("§e[BN] Order cancelled. Please check your active orders.")
        # Ideally we would parse which one was cancelled.

# --- Main Loop ---
def main():
    minescript.echo("§6Starting Bazaar Notifier...")
    load_conversions()
    
    # Start API thread
    api_thread = threading.Thread(target=check_bazaar, daemon=True)
    api_thread.start()
    
    minescript.echo("§aBazaar Notifier Active! Open Bazaar and make orders to track.")

    # Event Loop
    with minescript.EventQueue() as event_queue:
        event_queue.register_chat_listener()
        
        while True:
            # 1. Process any queued messages from the thread
            while message_queue:
                msg = message_queue.pop(0)
                minescript.echo(f"§b[BN] {msg}")

            # 2. Wait for events (short timeout to allow message_queue processing)
            try:
                event = event_queue.get(timeout=0.1)
                if event.type == "chat":
                    process_chat(event.message)
            except:
                # Timeout (empty queue), just loop back
                pass

if __name__ == "__main__":
    main()
