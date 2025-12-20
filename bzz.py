import minescript
from utils.minescript_plus import Inventory, Screen
import requests
import pprint
from enum import Enum
from dataclasses import dataclass
import os
import sys
import json
import time
from typing import List, Dict
import re
import threading
import queue
from randomizer import HumanDelay

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
    slot: int
    status: str = "SEARCHING"

    def __eq__(self, other):
        return (self.product_id == other.product_id and 
                self.price_per_unit == other.price_per_unit and 
                self.order_type == other.order_type and
                self.slot == other.slot)


# Global State
my_orders = []
bazaar_conversions = {} # API IDs ---> name
bazaar_conversions_inverse = {} # name ---> API IDs
outdated_orders = []
human = HumanDelay()
orders_lock = threading.RLock()

def load_bazaar_conversions() -> None:
    """
    Loads bazaarConversions.json into global dictionaries for ID-name mapping.
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
    Converts a product name to its corresponding bazaar product ID.
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
    Parses a in-chat price_str into its float representation.
    """
    return float(price_str.replace(",", ""))

def parse_amount(amount_str: str) -> int:
    """
    Parses a in-chat amount_str into its int representation.
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
            "product_id": get_product_id(p_name),
            "product_name": p_name,
            "amount": parse_amount(amount_str),
            "price_per_unit": parse_price(price_str)
        }
    return None

def parse_personal_orders() -> None:
    """
    Parses the player's personal bazaar orders from the "Your Bazaar Orders" screen.
    """
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
                    order = Order(
                        product_id=data['product_id'],
                        product_name=data['product_name'],
                        amount=data['amount'],
                        price_per_unit=data['price_per_unit'],
                        order_type=data['order_type'],
                        slot=itemstack.slot
                    )
                    found_orders.append(order)
        my_orders = found_orders

def update_orders_from_api() -> None:
    """
    Updates the status of tracked orders based on the latest bazaar data from the API.
    1. Fetches the latest bazaar data.
    2. Compares each tracked order with the current market data.
    3. Updates the order status accordingly.
    """
    global my_orders, outdated_orders

    with orders_lock:
        data = fetch_bazaar_data()
        if not data:
            return

        products = data['products']
        
        # continue if product does not exist in the bazaar
        for order in my_orders:
            if order.product_id not in products:
                minescript.echo(order.product_id + " is not recognized") # for debugging
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
                    add_outdated(order)
                elif new_status == "MATCHED":
                    minescript.echo(f"&e[BN] {order.order_type.value} for {order.product_name} is MATCHED.")
                    add_outdated(order)
                elif new_status == "BEST" and (order.status == "OUTDATED" or order.status == "MATCHED"):
                    minescript.echo(f"&a[BN] {order.order_type.value} for {order.product_name} is BEST again.")
                    outdated_orders.remove(order)
                
                order.status = new_status

def api_loop():
    """
    Background thread to periodically update orders from the API.
    1. Runs indefinitely, sleeping for CHECK_INTERVAL between updates.
    """
    while True:
        update_orders_from_api()
        time.sleep(CHECK_INTERVAL)

def add_outdated(order) -> None:
    """
    Docstring for add_outdated
    
    :param order: Description
    """
    global outdated_orders

    if order in outdated_orders:
        return
    outdated_orders.append(order)

def seek_manage_orders() -> None | int:
    """
    Finds the slot number of the "Manage Orders" item in the Bazaar screen.
    Returns the slot number if found, else None.
    """
    screen_name = minescript.screen_name()
    if screen_name == None:
        return
    if "Bazaar" in screen_name:
        container = minescript.container_get_items()

        for itemstack in container:
            item_name = None
            if hasattr(itemstack, 'nbt') and itemstack.nbt:
                # Robust regex to handle both quoted "text" and unquoted text keys
                match = re.search(r'"minecraft:custom_name":.*?"?text"?:?"(.*?)"', itemstack.nbt)
                if match:
                    item_name = match.group(1)

            if item_name == "Manage Orders":
                return itemstack.slot
        
        return 


def wait_for_screen(screen_keyword: str | None, timeout: float = 5.0) -> None:
    """
    Waits until the current screen name contains the keyword.
    Returns True if successful, False if timed out.
    """
    start_time = time.time()

    # Handles when scrreen_keyword is None / when no container is opened
    if screen_keyword == None:
        while time.time() - start_time < timeout:
            current_screen = minescript.screen_name()
            if current_screen == None:
                return 
            time.sleep(0.1)
        
        # Stop the program
        minescript.echo(f"Did not exit container in time")
        sys.exit()

    
    while time.time() - start_time < timeout:
        current_screen = minescript.screen_name()
        if current_screen and screen_keyword in current_screen: # If current_screen is None, it evaluates as false
            return 
        time.sleep(0.1)

    # Stop the program
    minescript.echo(f"{screen_keyword} did not load")
    sys.exit()

def open_bazaar_orders() -> None:
    human.typing_delay("/bz", wpm=100)

    minescript.execute("/bz")
    
    # Wait for server response (Lag handling)
    wait_for_screen("Bazaar", timeout=8.0)

    # Human reaction time AFTER the menu appears
    human.wait(min_seconds=0.8, max_seconds=1.2, skew=0.4, momentum=0.5)

    manage_orders_slot = seek_manage_orders()
    if manage_orders_slot == None:
        return
    Inventory.click_slot(manage_orders_slot)
    
    # Wait for "Your Bazaar Orders"
    wait_for_screen("Your Bazaar Orders", timeout=5.0)

    human.wait(min_seconds=1.5, max_seconds=3, skew=0.4, momentum=0.5)

def claim_orders() -> None:
    """
    Iteratively finds and claims orders until no more claimable orders exist.
    Handles slot shifting and partial claims by re-scanning after each click.
    """
    while True:
        claim_slots = []
        if minescript.screen_name() == "Your Bazaar Orders":
            container = minescript.container_get_items()

            for itemstack in container:
                if itemstack is None:
                    continue
                
                nbt = itemstack.nbt
                if not nbt:
                    continue

                # Check for SELL or BUY in custom_name
                is_order = re.search(r'text:"(SELL |BUY )"', nbt)
                
                # Check for "Click to claim!" in lore
                has_claim = re.search(r'text:"Click to claim!"', nbt)
                
                if is_order and has_claim:
                    claim_slots.append(itemstack.slot)
        else:
            wait_for_screen("Your Bazaar Orders", timeout=5.0)
        
        if not claim_slots:
            break

        # Click the first available claim slot
        slot = claim_slots[0]
        Inventory.click_slot(slot)
        human.wait(min_seconds=1, max_seconds=2, skew=0.4, momentum=0.5)


def renew_order() -> None:
    global outdated_orders
    cancel_button_slot_buy = 11
    cancel_button_slot_sell = 13
    buy_order_slot = 15
    buy_small_amount = 10
    buy_medium_amount = 12
    buy_large_amount = 14
    top_order_p01 = 12
    confirm_buy = 13

    sell_order_slot = 16
    sell_order_m01 = 12
    confirm_sell = 13

    if minescript.screen_name() != "Your Bazaar Orders":
        return
    if not outdated_orders:
        return

    parse_personal_orders()
    update_orders_from_api()

    order = outdated_orders[0]

    slot = order.slot

    # Clicks on the first outdated order
    Inventory.click_slot(slot)
    wait_for_screen("Order options", timeout=5.0)
    human.wait(min_seconds=1, max_seconds=2, skew=0.4, momentum=0.5)

    if order.order_type == OrderType.BUY:
        Inventory.click_slot(cancel_button_slot_buy)
        wait_for_screen("Your Bazaar Orders", timeout=5.0)
        human.wait(min_seconds=1, max_seconds=2, skew=0.4, momentum=0.5)
    
    elif order.order_type == OrderType.SELL:
        Inventory.click_slot(cancel_button_slot_sell)
        wait_for_screen("Your Bazaar Orders", timeout=5.0)
        human.wait(min_seconds=1, max_seconds=2, skew=0.4, momentum=0.5)
    
    leave_container()
    wait_for_screen(None, timeout=5.0)
    human.wait(min_seconds=0.6, max_seconds=0.8, skew=0.4, momentum=0.5)

    # Search for product
    human.typing_delay(f"/bz {order.product_name}", wpm=120)
    minescript.execute(f"/bz {order.product_name}")
    wait_for_screen(order.product_name[:20], timeout=8.0)
    human.wait(min_seconds=0.8, max_seconds=1.5, skew=0.4, momentum=0.5)

    # Click the product
    product_slot = seek_product(order.product_name)
    Inventory.click_slot(product_slot)
    wait_for_screen(order.product_name[:20], timeout=8.0)
    human.wait(min_seconds=1, max_seconds=2, skew=0.4, momentum=0.5)

    if order.order_type == OrderType.BUY:
        Inventory.click_slot(buy_order_slot)
        wait_for_screen("How many do you want?", timeout=8.0)
        human.wait(min_seconds=0.8, max_seconds=1.5, skew=0.4, momentum=0.5)

        # Chooses amount to buy
        if 2 * order.price_per_unit > 50000000: # When price per unit is above 50m
            Inventory.click_slot(buy_small_amount)
            wait_for_screen("How much do you want to pay?", timeout=8.0)
            human.wait(min_seconds=0.8, max_seconds=1.5, skew=0.4, momentum=0.5)
        else:
            Inventory.click_slot(buy_medium_amount)
            wait_for_screen("How much do you want to pay?", timeout=8.0)
            human.wait(min_seconds=0.8, max_seconds=1.5, skew=0.4, momentum=0.5)

        # Place top order
        Inventory.click_slot(top_order_p01)
        wait_for_screen("Confirm Buy Order", timeout=8.0)
        human.wait(min_seconds=0.8, max_seconds=1.5, skew=0.4, momentum=0.5)

        # Confirm buy order
        Inventory.click_slot(confirm_buy)
        wait_for_screen(None, timeout=8.0)
        human.wait(min_seconds=0.6, max_seconds=0.8, skew=0.4, momentum=0.5)

    elif order.order_type == OrderType.SELL:
        Inventory.click_slot(sell_order_slot)
        wait_for_screen("At what price are you selling?", timeout=8.0)
        human.wait(min_seconds=0.8, max_seconds=1.5, skew=0.4, momentum=0.5)

        # Place sell order
        Inventory.click_slot(sell_order_m01)
        wait_for_screen("Confirm Sell Offer", timeout=8.0)
        human.wait(min_seconds=0.8, max_seconds=1.5, skew=0.4, momentum=0.5)

        # Confirm sell order
        Inventory.click_slot(confirm_sell)
        wait_for_screen(None, timeout=8.0)
        human.wait(min_seconds=0.6, max_seconds=0.8, skew=0.4, momentum=0.5)

    # Remove the processed order to prevent infinite loops
    if order in outdated_orders:
        outdated_orders.remove(order)
        

def leave_container() -> None:
    if minescript.screen_name() is not None:
        Screen.close_screen()


def seek_product(product_name) -> int:
    screen_name = minescript.screen_name()
    if screen_name == None:
        return
    if "Bazaar" in screen_name:
        container = minescript.container_get_items()
        pattern = r'text:"' + re.escape(product_name) + r'"'
        
        for itemstack in container:
            if itemstack is None:
                continue
            
            if itemstack.nbt and re.search(pattern, itemstack.nbt):
                return itemstack.slot
            
    return None

def refresh_orders() -> None:
    global outdated_orders

    with orders_lock:
        while outdated_orders:
            open_bazaar_orders()

            claim_orders()

            renew_order()
        
        minescript.echo("All orders renewed")

        # TODO
        # seek for the outdated order

        # if there are items to claim, run a for loop to claim all

        # if there are no items to claim, then cancel order with a click on the outdated 
        # and then the cancel button

        # Press "E" to leave the container

        # Then execute \bz [product_name]

        # Click on the target product

        # Create new buy or sell order

        # Choose amount

        # Choose "Top Order +0.1"

        # Click "submit order"

if __name__ == "__main__":
    minescript.echo("&e[BN] Starting Bazaar Notifier...")

    # Load bazaarConversions.json
    load_bazaar_conversions()
    
    # Start API thread
    api_thread = threading.Thread(target=api_loop, daemon=True)
    api_thread.start()
    
    # Key Event Handler
    def on_key_event(event):
        if event.event_type == keyboard.KEY_DOWN:
            if event.name == "c":
                minescript.echo(str(my_orders))
            elif event.name == "x":
                minescript.echo("&c[BN] Emergency Stop Activated! Exiting...")
                os._exit(0)

    # Hook key events once
    keyboard.on_press(on_key_event)

    # Main Loop

    previous_screen = minescript.screen_name()
    while True:
        time.sleep(0.1) # Prevent freezing
        current_screen = minescript.screen_name()
            
        if previous_screen != current_screen and current_screen == "Your Bazaar Orders":
            parse_personal_orders()

        previous_screen = current_screen

        if outdated_orders:
            refresh_orders()

            
            
