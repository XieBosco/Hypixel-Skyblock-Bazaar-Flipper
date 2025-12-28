import minescript
from utils.minescript_plus import Inventory, Screen
import requests
import pprint
from data_structures import OrderType, Order, ProductTrackerObj
from utilities import parse_nbt_tooltip, log, get_product_id, load_bazaar_conversions, load_product_list, BazaarAPI
from get_best_product import ProductFinder
import os
import sys
import json
import time
from typing import List, Dict, Optional
import re
import threading
import queue
from randomizer import HumanDelay
import constants

# debuging

import keyboard

# --- Main ---

class ScreenTimeoutError(Exception):
    """Raised when a screen fails to appear within the timeout period."""
    pass

class ProductTracker:
    """
    Tracks the best products to flip and manages the target product list.
    """
    def __init__(self) -> None:
        self.filepath = os.path.join(os.path.dirname(__file__), "product_list.json")

        self.top_flips = ProductFinder().get_best_products()
        self.best_flips = self.get_best_flips()

        # Hard codes the products to be flipped
        # Only a maximum of 20 items can be flipped at a time
        self.product_list = load_product_list(self.filepath)
        
        # self.product_list = []
    
    def get_best_flips(self) -> List[str]:
        """
        Returns a filtered list of products from top_flips.

        Returns:
            List[str]: A list of product IDs representing the best flips.
        """
        best_flips = []
        for product in self.top_flips[:]:
            best_flips.append(product.product_id)
        
        return best_flips
    
    def is_best_flips(self, my_orders: List[Order]) -> None:
        """
        Checks if the current orders are among the best flips and logs if not.

        Args:
            my_orders (List[Order]): The list of current orders to check.
        """
        checked_ids = []
        for order in my_orders:
            if order.product_id in checked_ids:
                continue
            else:
                checked_ids.append(order.product_id)
        
            if order.product_id in self.best_flips:
                continue
            else:
                log(f"{order.product_name} is not one of the best flips")

    def eq_product_list(self, my_orders: List[Order]) -> bool:
        """
        Checks if the current orders match the target product list exactly.

        Args:
            my_orders (List[Order]): The list of current orders to compare.

        Returns:
            bool: True if the current orders match the target product list, False otherwise.
        """
        if len(my_orders) != len(self.product_list):
            return False

        # Convert both lists to a comparable format: list of (product_id, order_type)
        # Sort them to ensure order independence
        my_orders_simplified = sorted([(o.product_id, o.order_type.value) for o in my_orders])
        product_list_simplified = sorted([(p.product_id, p.order_type.value) for p in self.product_list])

        return my_orders_simplified == product_list_simplified

    def get_missing_products(self, my_orders: List[Order]) -> List[ProductTrackerObj]:
        """
        Identifies products from the target list that are missing from my_orders.

        Args:
            my_orders (List[Order]): The list of current orders.

        Returns:
            List[ProductTrackerObj]: A list of products that are in the target list but not in my_orders.
        """
        missing_products = list(self.product_list)
        
        for order in my_orders:
            for i, product in enumerate(missing_products):
                if product.product_id == order.product_id and product.order_type == order.order_type:
                    missing_products.pop(i)
                    break
        
        return missing_products


class GameState:
    """
    Handles parsing of inventory, NBT data, and tracking current orders.
    """
    def __init__(self, product_tracker: ProductTracker) -> None:
        self.filepath = os.path.join(os.path.dirname(__file__), "bazaarConversions.json")

        self.my_orders: List[Order] = []
        self.outdated_orders: List[Order] = []
        self.bazaar_conversions, self.bazaar_conversions_inverse = load_bazaar_conversions(self.filepath)
        self.orders_lock = threading.RLock()

        self.tracker = product_tracker

    def parse_personal_orders(self) -> None:
        """
        Parses the player's personal bazaar orders from the "Your Bazaar Orders" screen.
        Updates self.my_orders with the parsed orders.
        """
        found_orders = []
        if minescript.screen_name() == "Your Bazaar Orders":
            log("Personal Orders Checked")
            container = minescript.container_get_items()

            for itemstack in container:
                if (itemstack.item == "minecraft:black_stained_glass_pane" 
                    or itemstack.item == "minecraft:hopper" 
                    or itemstack.item == "minescraft:arrow"):
                    continue
                
                if hasattr(itemstack, 'nbt'):
                    data = parse_nbt_tooltip(itemstack.nbt, self.bazaar_conversions_inverse)
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
            self.my_orders = found_orders

            self.tracker.is_best_flips(self.my_orders)

            missing_products = self.tracker.get_missing_products(self.my_orders)
            if missing_products:
                return missing_products
            return []
    
    def update_orders_from_api(self) -> None:
        """
        Updates the status of tracked orders based on the latest bazaar data from the API.
        1. Fetches the latest bazaar data.
        2. Compares each tracked order with the current market data.
        3. Updates the order status accordingly.
        """
        with self.orders_lock:
            data = BazaarAPI.fetch_bazaar_data()
            if not data:
                return

            products = data['products']
            
            # continue if product does not exist in the bazaar
            for order in self.my_orders:
                if order.product_id not in products:
                    log(order.product_id + " is not recognized") # for debugging
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
                
                new_status = self.calculate_status(order, top_price, top_market_order)

                if new_status != order.status:
                    self.handle_status_change(order, new_status)
    
    def calculate_status(self, order: Order, top_price: float, top_market_order: Dict) -> str:
        """
        Calculates the status of an order based on market data.

        Args:
            order (Order): The order to check.
            top_price (float): The current top price in the market.
            top_market_order (Dict): The top order data from the API.

        Returns:
            str: The calculated status ("BEST", "OUTDATED", or "MATCHED").
        """
        if order.order_type == OrderType.BUY: # BUY
            if order.price_per_unit < top_price:
                return "OUTDATED"
            elif order.price_per_unit == top_price:
                # Check if we are the only one or matched
                if top_market_order['orders'] == 1:
                        return "BEST"
                else:
                        return "MATCHED"
            else:
                return "BEST" # We are overpaying, so we are top
        elif order.order_type == OrderType.SELL: # SELL
            if order.price_per_unit > top_price:
                return "OUTDATED"
            elif order.price_per_unit == top_price:
                if top_market_order['orders'] == 1:
                        return "BEST"
                else:
                        return "MATCHED"
            else:
                return "BEST" # We are undercutting, so we are top
        
    def handle_status_change(self, order: Order, new_status: str) -> None:
        """
        Updates the status of an order and manages the outdated orders list.

        Args:
            order (Order): The order to update.
            new_status (str): The new status of the order.
        """
        if new_status == "OUTDATED":
            log(f"&c[BN] {order.order_type.value} for {order.product_name} is OUTDATED!")
            self.add_outdated(order)
        elif new_status == "MATCHED":
            log(f"&e[BN] {order.order_type.value} for {order.product_name} is MATCHED.")
            self.add_outdated(order)
        elif new_status == "BEST" and (order.status == "OUTDATED" or order.status == "MATCHED"):
            log(f"&a[BN] {order.order_type.value} for {order.product_name} is BEST again.")
            self.outdated_orders.remove(order)
        
        order.status = new_status
    
    # --- UTILS ---
    def add_outdated(self, order: Order) -> None:
        """
        Adds an order to the outdated_orders list if not already present.

        Args:
            order (Order): The order to add.
        """
        if order in self.outdated_orders:
            return
        self.outdated_orders.append(order)
    


class Automation:
    """
    Handles automated interactions with the game client.
    """
    def __init__(self, state: GameState, human: HumanDelay) -> None:
        self.state = state
        self.human = human
        self.last_clicked_slot = None
        self.last_clicked_button = False
        self.last_executed_command = None

    def click_slot(self, slot: int, right_button: bool=False) -> bool:
        """
        Clicks a slot in the inventory.

        Args:
            slot (int): The slot index to click.
            right_button (bool): Whether to use the right mouse button.

        Returns:
            bool: True if the click was successful, False otherwise.
        """
        self.last_clicked_slot = slot
        self.last_clicked_button = right_button
        self.last_executed_command = None
        return Inventory.click_slot(slot, right_button)

    def execute_command(self, command: str) -> None:
        """
        Executes a command in the game.

        Args:
            command (str): The command to execute.
        """
        self.last_executed_command = command
        self.last_clicked_slot = None
        minescript.execute(command)

    
    def claim_orders(self) -> None:
        """
        Iteratively finds and claims orders until no more claimable orders exist.
        Handles slot shifting and partial claims by re-scanning after each click.
        """
        while True:
            claim_slots = []
            if minescript.screen_name() == "Your Bazaar Orders":
                container = minescript.container_get_items()

                # Checks if the "Claim All Coins" button is available
                for itemstack in container:
                    if itemstack.item == "minecraft:hopper":
                        if itemstack is None:
                            continue
                        
                        nbt = itemstack.nbt
                        if not nbt:
                            continue
                        
                        # Check for "Click to claim!" in lore
                        has_claim = re.search(r'text:"Click to claim!"', nbt)

                        if has_claim:
                            self.click_slot(itemstack.slot)
                            self.human.wait(min_seconds=1, max_seconds=2, skew=0.4, momentum=0.5)

                container = minescript.container_get_items()
                # Checks each order
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
                self.wait_for_screen("Your Bazaar Orders", timeout=5.0)
            
            if not claim_slots:
                break

            # Click the first available claim slot
            slot = claim_slots[0]
            self.click_slot(slot)
            self.human.wait(min_seconds=1, max_seconds=2, skew=0.4, momentum=0.5)

    def cancel_order(self, order: Order) -> None:
        """
        Cancels an outdated order.

        Args:
            order (Order): The order to cancel.
        """
        if minescript.screen_name() != "Your Bazaar Orders":
            return
        if not self.state.outdated_orders:
            return

        slot = order.slot

        # Clicks on the first outdated order
        self.click_slot(slot)
        self.wait_for_screen("Order options", timeout=5.0)
        self.human.wait(min_seconds=0.6, max_seconds=0.8, skew=0.4, momentum=0.5)

        cancel_slot = constants.SLOT_CANCEL_BUY if order.order_type == OrderType.BUY else constants.SLOT_CANCEL_SELL
        self.click_slot(cancel_slot)
        self.wait_for_screen("Your Bazaar Orders", timeout=5.0)
        self.human.wait(min_seconds=0.6, max_seconds=0.8, skew=0.4, momentum=0.5)

    def search_and_open_product(self, order: Order) -> None:
        """
        Searches for a product and opens its bazaar page.

        Args:
            order (Order): The order containing the product to search for.
        """
        # Search for product
        # Remove non-ASCII characters for the command execution
        clean_name = re.sub(r'[^\x00-\x7F]+', '', order.product_name).strip()
        
        self.human.typing_delay(f"/bz {clean_name}", wpm=constants.HUMAN_WPM)
        self.execute_command(f"/bz {clean_name}")
        self.wait_for_screen(clean_name[:20], timeout=8.0)
        self.human.wait(min_seconds=0.8, max_seconds=1.5, skew=0.4, momentum=0.5)

        # Click the product
        product_slot = self.seek_product(order.product_name)
        self.click_slot(product_slot)
        self.wait_for_screen(order.product_name[:20], timeout=8.0)
        self.human.wait(min_seconds=1, max_seconds=2, skew=0.4, momentum=0.5)

    def place_new_order(self, order: Order) -> None:
        """
        Places a new order for a product.

        Args:
            order (Order): The order to place.
        """
        if order.order_type == OrderType.BUY:
            self.click_slot(constants.SLOT_BUY_ORDER)
            self.wait_for_screen("How many do you want?", timeout=8.0)
            self.human.wait(min_seconds=0.8, max_seconds=1.5, skew=0.4, momentum=0.5)

            # Chooses amount to buy
            if 3 * order.price_per_unit > constants.MAX_BUY_COST: # When price per unit is above 50m
                self.click_slot(constants.SLOT_BUY_SMALL)
                self.wait_for_screen("How much do you want to pay?", timeout=8.0)
                self.human.wait(min_seconds=0.8, max_seconds=1.5, skew=0.4, momentum=0.5)
            else:
                self.click_slot(constants.SLOT_BUY_MEDIUM)
                self.wait_for_screen("How much do you want to pay?", timeout=8.0)
                self.human.wait(min_seconds=0.8, max_seconds=1.5, skew=0.4, momentum=0.5)

            # Place top order
            self.click_slot(constants.SLOT_TOP_ORDER_P01)
            self.wait_for_screen("Confirm Buy Order", timeout=8.0)
            self.human.wait(min_seconds=0.8, max_seconds=1.5, skew=0.4, momentum=0.5)

            # Confirm buy order
            self.click_slot(constants.SLOT_CONFIRM_BUY)
            self.wait_for_screen(None, timeout=8.0)
            self.human.wait(min_seconds=0.6, max_seconds=0.8, skew=0.4, momentum=0.5)

        elif order.order_type == OrderType.SELL:
            self.click_slot(constants.SLOT_SELL_OFFER)
            self.wait_for_screen("At what price are you selling?", timeout=8.0)
            self.human.wait(min_seconds=0.8, max_seconds=1.5, skew=0.4, momentum=0.5)

            # Place sell order
            self.click_slot(constants.SLOT_SELL_OFFER_M01)
            self.wait_for_screen("Confirm Sell Offer", timeout=8.0)
            self.human.wait(min_seconds=0.8, max_seconds=1.5, skew=0.4, momentum=0.5)

            # Confirm sell order
            self.click_slot(constants.SLOT_CONFIRM_SELL)
            self.wait_for_screen(None, timeout=8.0)
            self.human.wait(min_seconds=0.6, max_seconds=0.8, skew=0.4, momentum=0.5)

        # Remove the processed order to prevent infinite loops
        if order in self.state.outdated_orders:
            self.state.outdated_orders.remove(order)

    def add_missing_products(self, missing_products: List[ProductTrackerObj]) -> None:
        """
        Adds missing products to the bazaar.

        Args:
            missing_products (List[ProductTrackerObj]): The list of missing products to add.
        """
        if not missing_products:
            return
            
        # Fetch current prices to determine order size
        bazaar_data = BazaarAPI.fetch_bazaar_data()
        products_data = bazaar_data['products'] if bazaar_data else {}

        for product_obj in missing_products:
            # Get product name
            product_name = self.state.bazaar_conversions[product_obj.product_id]
            
            # Get price estimate
            price = 0.0
            if product_obj.product_id in products_data:
                p_data = products_data[product_obj.product_id]
                # Use summary for a rough price estimate
                if product_obj.order_type == OrderType.BUY:
                    price = p_data['sell_summary'][0]["pricePerUnit"]
                else:
                    price = p_data['buy_summary'][0]["pricePerUnit"]
            
            # Create a temporary Order object
            temp_order = Order(
                product_id=product_obj.product_id,
                product_name=product_name,
                amount=1, # Dummy amount
                price_per_unit=price,
                order_type=product_obj.order_type,
                slot=-1 # Dummy slot
            )

            if temp_order.order_type == OrderType.SELL and minescript.screen_name() == None:
                self.open_bazaar_orders()
            
            if temp_order.order_type == OrderType.BUY and minescript.screen_name() == "Your Bazaar Orders":
                self.leave_container()
            
            if temp_order.order_type == OrderType.SELL and self.product_in_inventory(temp_order):
                self.place_new_order(temp_order)
            elif temp_order.order_type == OrderType.BUY:
                self.search_and_open_product(temp_order)
                self.place_new_order(temp_order)
        
        if minescript.screen_name() != None:
            self.leave_container()
            
    
    def product_in_inventory(self, order: Order) -> bool:
        """
        Checks if a product is in the player's inventory (specifically in the "Your Bazaar Orders" screen).
        If found, the slot is clicked.

        Args:
            order (Order): The order containing the product to check for.

        Returns:
            bool: True if the product was found and clicked, False otherwise.
        """
        if minescript.screen_name() == "Your Bazaar Orders":
                container = minescript.container_get_items()

                for itemstack in container:
                    if itemstack is None:
                        continue
                    
                    nbt = itemstack.nbt
                    if not nbt:
                        continue
                    
                    # Regex to find the custom name block
                    # We look for "minecraft:custom_name":{extra:[ ... ]}
                    # We capture the content inside the extra array [ ... ]
                    # We assume the extra array ends with the first ] character, as nested arrays are not expected in the name components
                    name_match = re.search(r'"minecraft:custom_name":\{extra:\[(.*?)\]', nbt)
                    
                    if name_match:
                        extra_content = name_match.group(1)
                        # Extract all text values from the extra components
                        # Pattern looks for text:"..."
                        # We use [^"]* to match the text content, assuming no escaped quotes inside the name for now
                        texts = re.findall(r'text:"([^"]*)"', extra_content)
                        item_name = "".join(texts)
                        item_id = get_product_id(item_name, self.state.bazaar_conversions_inverse)

                        if item_id == order.product_id:
                            self.click_slot(itemstack.slot)
                            self.human.wait(min_seconds=1, max_seconds=2, skew=0.4, momentum=0.5)
                            return True
        return False

    def renew_order(self) -> None:
        """
        Renews a single outdated order.
        1. Cancels the outdated order.
        2. Navigates to the product page.
        3. Places a new order.
        """
        # Get up-to-date outdated orders
        self.state.outdated_orders.clear() 
        self.state.parse_personal_orders()
        self.state.update_orders_from_api()

        if not self.state.outdated_orders:
            return

        order = self.state.outdated_orders[0]

        # 1. Cancel a single order
        self.cancel_order(order)
        
        if self.product_in_inventory(order):
            pass
        else:
            # Leave the container
            self.leave_container()

            # 2. Navigate to Product
            self.search_and_open_product(order)
        
        # 3. Place New Order
        self.place_new_order(order)

    def refresh_orders(self) -> None:
        """
        Refreshes all outdated orders and adds missing products.
        """
        with self.state.orders_lock:
            while self.state.outdated_orders:
                self.open_bazaar_orders()

                self.claim_orders()

                # Renews an order one at a time
                self.renew_order()

            # Update my_orders before releasing the lock so api_loop does not crash
            self.open_bazaar_orders()
            missing = self.state.parse_personal_orders()
            if missing:
                self.add_missing_products(missing)

            # Leave the container
            if minescript.screen_name() != None:
                self.leave_container()

            log("All orders renewed")





    # --- Class UTILS ---

    def handle_unexpected_error(self) -> bool:
        """
        Attempts to recover from an unexpected error (e.g., ignored click or command).
        
        Returns:
            bool: True if recovery was attempted, False otherwise.
        """
        if self.last_clicked_slot is not None:
            log("&e[BN] Click ignored? Retrying...")
            Inventory.click_slot(self.last_clicked_slot, self.last_clicked_button)
            self.human.wait(min_seconds=0.5, max_seconds=1.0) # Wait a bit after retry
            return True
        elif self.last_executed_command is not None:
            log(f"&e[BN] Command '{self.last_executed_command}' ignored? Retrying...")
            minescript.execute(self.last_executed_command)
            self.human.wait(min_seconds=0.5, max_seconds=1.0)
            return True
        return False

    def wait_for_screen(self, screen_keyword: str | None, timeout: float = 5.0) -> None:
        """
        Waits until the current screen name contains the keyword.

        Args:
            screen_keyword (str | None): The keyword to search for in the screen name. If None, waits for no screen.
            timeout (float): The maximum time to wait in seconds.

        Raises:
            ScreenTimeoutError: If the screen does not appear within the timeout.
        """
        for attempt in range(3): # Number of attempts
            start_time = time.time()
            while time.time() - start_time < timeout:
                current_screen = minescript.screen_name()
                if screen_keyword is None:
                    if current_screen is None: 
                        self.last_clicked_slot = None
                        self.last_executed_command = None
                        return
                elif current_screen and screen_keyword in current_screen: # If current_screen is None, it evaluates as false
                    self.last_clicked_slot = None
                    self.last_executed_command = None
                    return  
                time.sleep(0.1)

            # Handle unexpected error
            if attempt < 2 and self.handle_unexpected_error():
                continue

            # Try restarting the program

            # Handle timeout (maybe raise exception or log)
            # log(f"&cTimeout waiting for screen: {screen_keyword}")

            # Raise exception instead of exiting
            raise ScreenTimeoutError(f"Timeout waiting for screen: {screen_keyword}")

            # sys.exit()
    
    def leave_container(self) -> None:
        """
        Closes the current container/screen.
        """
        if minescript.screen_name() is not None:
            Screen.close_screen()
            self.wait_for_screen(None, timeout=5.0)
            self.human.wait(min_seconds=0.6, max_seconds=0.8, skew=0.4, momentum=0.5)
        
    def seek_product(self, product_name: str) -> int | None:
        """
        Finds the slot number of a product in the current container.

        Args:
            product_name (str): The name of the product to find.

        Returns:
            int | None: The slot number if found, else None.
        """
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
    
    def seek_manage_orders(self) -> None | int:
        """
        Finds the slot number of the "Manage Orders" item in the Bazaar screen.
        
        Returns:
            int | None: The slot number if found, else None.
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
    
    def open_bazaar_orders(self) -> None:
        """
        Opens the "Your Bazaar Orders" screen.
        """
        self.human.typing_delay("/bz", wpm=constants.HUMAN_WPM)

        self.execute_command("/bz")
        
        # Wait for server response (Lag handling)
        self.wait_for_screen("Bazaar", timeout=8.0)

        # Human reaction time AFTER the menu appears
        self.human.wait(min_seconds=0.8, max_seconds=1.2, skew=0.4, momentum=0.5)

        manage_orders_slot = self.seek_manage_orders()
        if manage_orders_slot == None:
            return
        self.click_slot(manage_orders_slot)
        
        # Wait for "Your Bazaar Orders"
        self.wait_for_screen("Your Bazaar Orders", timeout=5.0)

        self.human.wait(min_seconds=1, max_seconds=2, skew=0.4, momentum=0.5)


class BazaarBot:
    """
    The main bot class that controls the bazaar flipping process.
    """
    def __init__(self) -> None:
        # Global State
        self.tracker = ProductTracker()
        self.human = HumanDelay()
        self.state = GameState(self.tracker)
        self.automation = Automation(self.state, self.human)
    
    def start(self) -> None:
        """
        Starts the bot's main loop and background threads.
        """
        log("&e[BN] Starting Bazaar Notifier...")

        # Start API thread
        api_thread = threading.Thread(target=self.api_loop, daemon=True)
        api_thread.start()

        # Start terminate_both thread
        terminate_bot_thread = threading.Thread(target=self.terminate_bot, daemon=True)
        terminate_bot_thread.start()
        
        # Hook key events once
        keyboard.on_press(self.on_key_event)

        while True:
            try:
                # Main Loop
                previous_screen = minescript.screen_name()
                while True:
                    time.sleep(0.1) # Prevent freezing
                    current_screen = minescript.screen_name()
                        
                    if previous_screen != current_screen and current_screen == "Your Bazaar Orders":
                        missing = self.state.parse_personal_orders()
                        log(missing)
                        if missing:
                            self.automation.add_missing_products(missing)

                    previous_screen = current_screen

                    if self.state.outdated_orders:
                        self.automation.refresh_orders()
                    
            except ScreenTimeoutError as e:
                log(f"&c[BN] {e}")
                log("&e[BN] Restarting bot...")

                # Leave the container
                self.automation.leave_container()

                self.automation.open_bazaar_orders()
                missing = self.state.parse_personal_orders()
                if missing:
                    self.automation.add_missing_products(missing)

                # Leave the container
                self.automation.leave_container()

                log("&e[BN] Restart Complete")
                time.sleep(2)  # Wait a bit before restarting
                continue  # Restart the main loop

    # Key Event Handler
    def on_key_event(self, event) -> None:
        """
        Handles keyboard events for manual control.

        Args:
            event: The keyboard event.
        """
        if event.event_type == keyboard.KEY_DOWN:
            if event.name == "c":
                log(str(self.state.my_orders))
            elif event.name == "x":
                log("&c[BN] Emergency Stop Activated! Exiting...")
                os._exit(0)

    def api_loop(self) -> None:
        """
        Background thread to periodically update orders from the API.
        1. Runs indefinitely, sleeping for CHECK_INTERVAL between updates.
        """
        while True:
            self.state.update_orders_from_api()
            time.sleep(constants.CHECK_INTERVAL)

    def terminate_bot(self) -> None:
        """
        Terminates the bot when the bazaar limit has been reached or when the player
        is sent to limbo.
        """
        with minescript.EventQueue() as event_queue:
            event_queue.register_chat_listener()
            while True:
                event = event_queue.get()
                if event.type == minescript.EventType.CHAT:
                    message = event.message
                    if message == constants.BZ_LIMIT_MSG_1 or message == constants.BZ_LIMIT_MSG_2:
                        log("&c[BN] Bazaar Limit Reached! Exiting...")
                        os._exit(0)
                    if message == constants.LIMBO_MSG:
                        log("&c[BN] Sent To Limbo! Exiting...")
                        os._exit(0)
                    if message == constants.SERVER_REBOOT_MSG:
                        log("&c[BN] Sever is Rebooting! Exiting...")
                        os._exit(0)
                    


if __name__ == "__main__":
    BazaarBot().start()

            
            
