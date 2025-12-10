import minescript
import requests
import pprint
from enum import Enum
from dataclasses import dataclass
import os
import json
import time
from typing import List, Dict
import re
import threading
import queue

# debuging

import keyboard


# --- CONFIGURATION ---
API_URL = "https://api.hypixel.net/v2/skyblock/bazaar"
CHECK_INTERVAL = 10  # Seconds between API checks

# --- Data Structures ---

class OrderType(Enum):
    BUY = "Buy Order"
    SELL = "Sell Offer"

@dataclass
class Order:
    product_id: str
    product_name: str
    amount: int
    price_per_unit: float
    order_type: OrderType
    status: str = "SEARCHING"

    def __eq__(self, other):
        return (self.product_id == other.product_id and 
                self.price_per_unit == other.price_per_unit and 
                self.order_type == other.order_type)


# Global State
my_orders = []
bazaar_conversions = {} # API IDs ---> name
bazaar_conversions_inverse = {} # name ---> API IDs

def load_bazaar_conversions() -> None:
    """
    Docstring for load_bazaar_conversions
    """
    global bazaar_conversions, bazaar_conversions_inverse
    
    try:
        filepath = os.path.join(os.path.dirname(__file__), "bazaarConversions.json")
        with open(filepath, "r", encoding="utf-8") as f:
            bazaar_conversions = json.load(f)
            for key, value in bazaar_conversions.items():
                bazaar_conversions_inverse[value] = key # valid since there are no duplicate keys
    except Exception as e:
        minescript.echo(f"Error loading conversions: {e}")
    

def fetch_bazaar_data() -> Dict[str, bool | int | Dict[str, str | List[Dict[str, int]] | Dict[str, int | str]]]:
    """Fetches global bazaar data from Hypixel."""
    try:
        response = requests.get(API_URL, timeout=5)
        if response.status_code == 200:
            bazaar_data = response.json()
            if bazaar_data["success"]:
                return bazaar_data
    except Exception as e:
        minescript.echo(f"§c[BN] API Error: {e}")
    return None


def get_product_id(name: str) -> str:
    """
    Returns the API's reference to product name
    (e.g. "Enchanted Iron" -> "ENCHANTED_IRON")
    """
    # Try exact match which in most cases will work
    if name in bazaar_conversions_inverse:
        return bazaar_conversions_inverse[name]
    
    # Try case-insensitive
    for k, v in bazaar_conversions_inverse.items():
        if k.lower() == name.lower():
            return v
            
    # Fallback: Try to guess ID (e.g. "Enchanted Iron" -> "ENCHANTED_IRON")
    guess = name.upper().replace(" ", "_")
    return guess


def parse_price(price_str: str) -> float:
    """
    Parses a in-chat price_str into its float representation
    """
    return float(price_str.replace(",", ""))

def parse_amount(amount_str: str) -> int:
    """
    Parses a in-chat amount_str into its int representation
    """
    return int(amount_str.replace(",", ""))

def parse_nbt_tooltip(nbt_str: str) -> Dict:
    """
    Parses NBT data from an item tooltip to extract order details.
    """
    if not nbt_str:
        return None

    # 1. Order Type & Product Name
    # Matches: text:"SELL "},{color:"gold",text:"Chain of the End Times"}
    name_pattern = r'text:"(SELL|BUY) "},\{.*?,text:"(.*?)"\}'
    name_match = re.search(name_pattern, nbt_str)
    
    # 2. Amount
    # Matches: text:"Offer amount: "},{color:"green",text:"3"}
    # OR: text:"Order amount: "},{color:"green",text:"1"}
    amount_pattern = r'text:"(Offer|Order) amount: "},\{.*?,text:"([\d,]+)"\}'
    amount_match = re.search(amount_pattern, nbt_str)
    
    # 3. Price Per Unit
    # Matches: text:"Price per unit: "},{color:"gold",text:"1,317,020.1 coins"}
    price_pattern = r'text:"Price per unit: "},\{.*?,text:"([\d,.]+) coins"\}'
    price_match = re.search(price_pattern, nbt_str)
    
    if name_match and amount_match and price_match:
        o_type_str = name_match.group(1)
        p_name = name_match.group(2)
        amount_str = amount_match.group(2) # group(2) is the number
        price_str = price_match.group(1)
        return {
            "order_type": OrderType.BUY if o_type_str == "BUY" else OrderType.SELL,
            "product_name": p_name,
            "amount": parse_amount(amount_str),
            "price_per_unit": parse_price(price_str)
        }
    return None

def parse_personal_orders() -> None:
    global my_orders
    found_orders = []
    if minescript.screen_name() == "Your Bazaar Orders":
        minescript.echo("Personal Orders Checked")
        container = minescript.container_get_items()

        for itemstack in container:
            if (itemstack.item == "minecraft:black_stained_glass_pane" 
                or itemstack.item == "minecraft:hopper" 
                or itemstack.item == "minescraft:arrow"):
                continue
            
            if hasattr(itemstack, 'nbt'):
                data = parse_nbt_tooltip(itemstack.nbt)
                if data:
                    p_id = get_product_id(data['product_name'])
                    order = Order(
                        product_id=p_id,
                        product_name=data['product_name'],
                        amount=data['amount'],
                        price_per_unit=data['price_per_unit'],
                        order_type=data['order_type'],
                    )
                    found_orders.append(order)
        my_orders = found_orders

def update_orders_from_api() -> None:
    """
    Docstring for update_orders_from_api
    """
    global my_orders

    data = fetch_bazaar_data()
    if not data:
        return

    products = data['products']
    
    # continue if product does not exist in the bazaar
    for order in my_orders:
        if order.product_id not in products:
            minescript.echo(order.product_id + "is not recognized") # debuger
            continue

        product_data = products[order.product_id]
        
        # Logic from Java Mod:
        # BUY Order -> Compare with sell_summary (Buy Orders)
        # SELL Offer -> Compare with buy_summary (Sell Offers)
        # These unusual names exists due to the API's naming of these fields
        
        market_list = []
        if order.order_type == OrderType.BUY:
            # Buy Orders
            market_list = product_data['sell_summary']
        elif order.order_type == OrderType.SELL:
            # Sell Orders
            market_list = product_data['buy_summary']

        if not market_list:
            continue
        
        # Top orders are the first item in the list
        top_market_order = market_list[0]
        top_price: float = top_market_order['pricePerUnit']
        
        new_status = order.status

        if order.order_type == OrderType.BUY: # BUY
            if order.price_per_unit < top_price:
                new_status = "OUTDATED"
            elif order.price_per_unit == top_price:
                # Check if we are the only one or matched
                if top_market_order['orders'] == 1:
                        new_status = "BEST"
                else:
                        new_status = "MATCHED"
            else:
                new_status = "BEST" # We are overpaying, so we are top
        elif order.order_type == OrderType.SELL: # SELL
            if order.price_per_unit > top_price:
                new_status = "OUTDATED"
            elif order.price_per_unit == top_price:
                if top_market_order['orders'] == 1:
                        new_status = "BEST"
                else:
                        new_status = "MATCHED"
            else:
                new_status = "BEST" # We are undercutting, so we are top

        if new_status != order.status:
            if new_status == "OUTDATED":
                minescript.echo(f"&c[BN] {order.order_type.value} for {order.product_name} is OUTDATED!")
            elif new_status == "MATCHED":
                minescript.echo(f"&e[BN] {order.order_type.value} for {order.product_name} is MATCHED.")
            elif new_status == "BEST" and order.status == "OUTDATED":
                minescript.echo(f"&a[BN] {order.order_type.value} for {order.product_name} is BEST again.")
            
            order.status = new_status


def api_loop():
    """
    Updates orders from new API calls every CHECK_INTERVAL seconds.
    """
    while True:
        update_orders_from_api()
        time.sleep(CHECK_INTERVAL)


def process_chat(message: str) -> None:
    # Clean color codes if necessary (Minescript usually gives clean text or with codes)
    # Regex patterns
    
    # 1. Setup
    # "[Bazaar] Buy Order Setup! 64x Enchanted Iron for 100,000 coins."
    setup_pattern = r"\[Bazaar\] (Buy Order|Sell Offer) Setup! ([\d,]+)x (.+) for ([\d,.]+) coins\."
    match = re.search(setup_pattern, message)
    if match:
        o_type_str = match.group(1) # Order Type
        amount_str = match.group(2) # Product Amount
        p_name = match.group(3) # Product Name
        price_str = match.group(4) # Total Price
        
        o_type = OrderType.BUY if "Buy" in o_type_str else OrderType.SELL
        amount = parse_amount(amount_str)
        price_total = parse_price(price_str)
        price_unit = price_total / amount # Price per unit
        
        p_id = get_product_id(p_name)
        
        new_order = Order(p_id, p_name, amount, price_unit, o_type)
        my_orders.append(new_order)
        minescript.echo(f"&a[BN] Tracking new {o_type.value}: {p_name} at {price_unit:.1f}")
        return

    # 2. Filled (Fully)
    # "[Bazaar] Your Sell Offer for 64x Enchanted Iron was filled!"
    filled_pattern = r"\[Bazaar\] Your (Buy Order|Sell Offer) for ([\d,]+)x (.+) was filled!"
    match = re.search(filled_pattern, message)
    if match:
        o_type_str = match.group(1)
        amount_str = match.group(2)
        p_name = match.group(3)
        
        o_type = OrderType.BUY if "Buy" in o_type_str else OrderType.SELL
        amount = parse_amount(amount_str)
        p_id = get_product_id(p_name)
        
        # Find and remove order
        # We might have multiple orders for same item, remove the one that matches best or just first
        
        filled_order_idx = None
        for i, order in enumerate(my_orders):
            if order.product_id == p_id and order.order_type == o_type and order.amount == amount:
                # Ideally check amount, but amount changes as it fills. 
                # For simplicity, remove the first matching one.

                other_buy_price_unit = 0
                other_sell_price_unit = float('inf')

                if order.order_type == OrderType.BUY and order.price_per_unit > other_buy_price_unit:
                    other_buy_price_unit = order.price_per_unit
                    filled_order_idx = i

                elif order.order_type == OrderType.SELL and order.price_per_unit < other_sell_price_unit:
                    other_sell_price_unit = order.price_per_unit
                    filled_order_idx = i

        if filled_order_idx is not None:
            del my_orders[filled_order_idx]
            minescript.echo(f"&a[BN] Order filled and removed: {p_name}")

        return

    # 3. Cancelled
    # "[Bazaar] Cancelled! Refunded 12.8 coins from cancelling Buy Order!"
    cancelled_pattern = r"\[Bazaar\] Cancelled! Refunded ([\d,.]+) coins from cancelling (Buy Order|Sell Offer)!"
    match = re.search(cancelled_pattern, message)
    if match:
        refund_amount = parse_price(match.group(1))
        o_type_str = match.group(2)
        o_type = OrderType.BUY if "Buy" in o_type_str else OrderType.SELL
        
        # Try to find matching order by price
        for i, order in enumerate(my_orders):
            if order.order_type == o_type:
                total_price = order.amount * order.price_per_unit
                # Check if total price matches refund amount (with small tolerance for float errors)
                if abs(total_price - refund_amount) < 0.1:
                    del my_orders[i]
                    minescript.echo(f"&c[BN] Order cancelled and removed: {order.product_name}")
                    break
        return

if __name__ == "__main__":
    # api_loop()
    # load_bazaar_conversions()
    # minescript.echo(bazaar_conversions)
    # minescript.echo(bazaar_conversions_inverse)
    
    minescript.echo("&e[BN] Starting Bazaar Notifier...")

    # Load bazaarConversions.json
    load_bazaar_conversions()
    
    # Start API thread
    api_thread = threading.Thread(target=api_loop, daemon=True)
    api_thread.start()
    
    # For Debugging
    def on_key_event(event):
        if event.name == "c" and event.event_type == keyboard.KEY_DOWN:
            minescript.echo(str(my_orders))

    # Hook key events once
    keyboard.on_press(on_key_event)
    
    # Main Event Loop
    # with minescript.EventQueue() as event_queue:
    #     event_queue.register_chat_listener()
    #     minescript.echo("&a[BN] Listening for Bazaar chat messages...")

    #     previous_screen = None
        
    #     while True:
    #         try:
    #             event = event_queue.get(timeout=1.0)
    #             if event.type == minescript.EventType.CHAT:
    #                 process_chat(event.message)
    #         except queue.Empty:
    #             pass
            
    #         current_screen = minescript.screen_name()
            
    #         if previous_screen != current_screen and current_screen == "Your Bazaar Orders":
    #             parse_personal_orders()

    #         previous_screen = minescript.screen_name()

    previous_screen = minescript.screen_name()
    while True:
        time.sleep(0.1) # Prevent freezing
        current_screen = minescript.screen_name()
            
        if previous_screen != current_screen and current_screen == "Your Bazaar Orders":
            parse_personal_orders()

        previous_screen = current_screen

            
            
