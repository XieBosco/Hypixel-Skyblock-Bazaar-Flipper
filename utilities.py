import re
from typing import Dict, List, Optional
from data_structures import OrderType, Order, ProductTrackerObj
try:
    import minescript
except ImportError:
    minescript = None
import constants
import requests
import json

# --- Utilities ---

def log(message: str) -> None:
    """
    Wrapper for logging messages. Currently prints to in-game chat via minescript.echo.

    Args:
        message (str): The message to log.
    """
    minescript.echo(message)

def parse_nbt_tooltip(nbt_str: str, bazaar_conversions_inverse: Dict) -> Dict | None:
    """
    Parses NBT data from an item tooltip to extract order details.

    Args:
        nbt_str (str): The NBT string from the item tooltip.
        bazaar_conversions_inverse (Dict): Dictionary mapping product names to IDs.

    Returns:
        Dict | None: A dictionary containing order details if parsing is successful, else None.
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
            "product_id": get_product_id(p_name, bazaar_conversions_inverse),
            "product_name": p_name,
            "amount": parse_amount(amount_str),
            "price_per_unit": parse_price(price_str)
        }
    return None

def get_product_id(name: str, bazaar_conversions_inverse: Dict) -> str:
    """
    Converts a product name to its corresponding bazaar product ID.

    Args:
        name (str): The display name of the product.
        bazaar_conversions_inverse (Dict): Dictionary mapping product names to IDs.

    Returns:
        str: The product ID.
    """
    # Try exact match which in most cases will work
    if name in bazaar_conversions_inverse:
        return bazaar_conversions_inverse[name]
    
    # Try case-insensitive
    for k, v in bazaar_conversions_inverse.items():
        if k.lower() == name.lower():
            return v
            
    # Try stripping non-ASCII characters (for gemstones with unicode symbols)
    clean_input = re.sub(r'[^\x00-\x7F]+', '', name).strip()
    for k, v in bazaar_conversions_inverse.items():
        clean_k = re.sub(r'[^\x00-\x7F]+', '', k).strip()
        if clean_k == clean_input:
            return v

    # Fallback: Try to guess ID (e.g. "Enchanted Iron" -> "ENCHANTED_IRON")
    guess = name.upper().replace(" ", "_")
    return guess


def get_product_name(id: str, bazaar_conversions: Dict) -> str:
    """
    Converts a product ID to its corresponding bazaar product name.

    Args:
        id (str): The product ID.
        bazaar_conversions (Dict): Dictionary mapping product IDs to names.

    Returns:
        str: The product name.
    """
    # Try exact match which in most cases will work
    if id in bazaar_conversions:
        return bazaar_conversions[id]
    
    # Fallback: Try to guess name (e.g. "ENCHANTED_IRON" -> "Enchanted Iron")
    guess = id.lower().replace("_", " ")
    return guess


def parse_price(price_str: str) -> float:
    """
    Parses a in-chat price_str into its float representation.

    Args:
        price_str (str): The price string (e.g., "1,234.5").

    Returns:
        float: The parsed price.
    """
    return float(price_str.replace(",", ""))

def parse_amount(amount_str: str) -> int:
    """
    Parses a in-chat amount_str into its int representation.

    Args:
        amount_str (str): The amount string (e.g., "1,234").

    Returns:
        int: The parsed amount.
    """
    return int(amount_str.replace(",", ""))

def load_bazaar_conversions(filepath: str) -> tuple[Dict[str, str], Dict[str, str]]:
    """
    Loads bazaarConversions.json into global dictionaries for ID-name mapping.

    Args:
        filepath (str): The absolute path to the bazaarConversions.json file.

    Returns:
        tuple[Dict[str, str], Dict[str, str]]: A tuple containing:
            - bazaar_conversions: Mapping from Product ID to Product Name.
            - bazaar_conversions_inverse: Mapping from Product Name to Product ID.
            Returns ({}, {}) if loading fails.
    """
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            bazaar_conversions = json.load(f)
            bazaar_conversions_inverse = {v: k for k, v in bazaar_conversions.items()} # valid since there are no duplicate keys
            return bazaar_conversions, bazaar_conversions_inverse
    except Exception as e:
        log(f"Error loading conversions: {e}")

def load_products_marketshare(filepath: str) -> Dict:
    """
    Loads the market share data for products from a JSON file.

    Args:
        filepath (str): The absolute path to the bazaar_scores.json file.

    Returns:
        Dict: A dictionary containing market share data for each product.
              Returns {} if loading fails.
    """
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            products_marketshare = json.load(f)
            return products_marketshare
    except Exception as e:
        log(f"Error loading marketshare: {e}")

def load_product_list(filepath: str) -> List[ProductTrackerObj]:
    """
    Loads the list of products to track from a JSON file.

    Args:
        filepath (str): The absolute path to the product_list.json file.

    Returns:
        List[ProductTrackerObj]: A list of ProductTrackerObj instances representing the products to track.
                                 Returns [] if loading fails.
    """
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            raw_data = json.load(f)
            product_list = []
            
            for product in raw_data["SELL"]:
                product_list.append(ProductTrackerObj(product, OrderType.SELL))
            for product in raw_data["BUY"]:
                product_list.append(ProductTrackerObj(product, OrderType.BUY))
            
            return product_list

    except Exception as e:
        log(f"Error loading product list: {e}")

class BazaarAPI:
    """
    Handles loading and accessing bazaar products.
    """
    @staticmethod
    def fetch_bazaar_data() -> Dict[str, bool | int | Dict[str, str | List[Dict[str, int]] | Dict[str, int | str]]]:
        """Fetches global bazaar data from Hypixel."""
        try:
            response = requests.get(constants.API_URL, timeout=5)
            if response.status_code == 200:
                bazaar_data = response.json()
                if bazaar_data["success"]:
                    return bazaar_data
        except Exception as e:
            log(f"§c[BN] API Error: {e}")
        return None


