import requests
import pprint
from typing import List, Dict
from dataclasses import dataclass
import constants
from utilities import get_product_name, load_bazaar_conversions, load_products_marketshare, BazaarAPI
from data_structures import OrderType
import os


# --- Data Structures ---
@dataclass
class Product:
    product_id: str
    product_name: str
    buy_order_price: float
    sell_order_price: float
    instant_buy_weekly: int
    instant_sell_weekly: int
    spread: float # (sell_order_price*(1 - TAX_RATE)) - buy_order_price
    instant_buy_hourly: int # instant_buy_weekly/168
    instant_sell_hourly: int
    buy_orders: int # active buy orders
    sell_orders: int # active sell orders
    profit: float = 0.0
    bz_limit: float = 0.0

 
def filter_by_bz_limit(list: List[Product], minimum: float, maximum: float) -> None:
    """
    Filter by the minimum and maximum bazaar limits allowable inclusive.

    Args:
        list (List[Product]): The list of products to filter.
        minimum (float): The minimum bazaar limit.
        maximum (float): The maximum bazaar limit.
    """
    for product in list[:]: # Iterate over a copy
        if minimum <= product.bz_limit <= maximum:
            continue
        else:
            list.remove(product)

def filter_by_volume(list: List[Product], minimum: float, maximum: float) -> None:
    """
    Filter by the minimum and maximum volume allowable inclusive.

    Args:
        list (List[Product]): The list of products to filter.
        minimum (float): The minimum volume.
        maximum (float): The maximum volume.
    """
    for product in list[:]: # Iterate over a copy
        volume = min(product.instant_buy_hourly, product.instant_sell_hourly)
        if minimum <= volume <= maximum:
            continue
        else:
            list.remove(product)



class ProductFinder:
    """
    Finds the best products to flip on the bazaar.
    """
    def __init__(self) -> None:
        self.filepath = os.path.join(os.path.dirname(__file__), "bazaarConversions.json")
        self.filepath_marketshare = os.path.join(os.path.dirname(__file__), "bazaar_scores.json")

        self.bazaar_conversions, self.bazaar_conversions_inverse = load_bazaar_conversions(self.filepath)
        self.data = BazaarAPI.fetch_bazaar_data()
        self.products_marketshare = load_products_marketshare(self.filepath_marketshare)

    def parse_product(self, product_id: str, summary: Dict) -> Product | None:
        """
        Parses product data from the bazaar summary.

        Args:
            product_id (str): The product ID.
            summary (Dict): The product summary data.

        Returns:
            Product | None: The parsed Product object, or None if data is missing.
        """
        sell_summary = summary["sell_summary"]
        buy_summary = summary["buy_summary"]
        quick_status = summary["quick_status"]

        if not sell_summary or not buy_summary:
            return None

        product_name = get_product_name(product_id, self.bazaar_conversions)
        buy_order_price = sell_summary[0]["pricePerUnit"]
        sell_order_price = buy_summary[0]["pricePerUnit"]
        instant_buy_weekly = quick_status["buyMovingWeek"]
        instant_sell_weekly = quick_status["sellMovingWeek"]
        spread = (sell_order_price*(1 - constants.TAX_RATE)) - buy_order_price
        instant_buy_hourly = instant_buy_weekly/168
        instant_sell_hourly = instant_sell_weekly/168
        buy_orders = quick_status["buyOrders"]
        sell_orders = quick_status["sellOrders"]

        product = Product(
            product_id=product_id,
            product_name=product_name,
            buy_order_price=buy_order_price,
            sell_order_price=sell_order_price,
            instant_buy_weekly=instant_buy_weekly,
            instant_sell_weekly=instant_sell_weekly,
            spread=spread,
            instant_buy_hourly=instant_buy_hourly,
            instant_sell_hourly=instant_sell_hourly,
            buy_orders=buy_orders,
            sell_orders=sell_orders
        )
        return product

    def get_hourly_profit(self, product: Product) -> float:
        """
        Calculates the estimated hourly profit for a product.

        Args:
            product (Product): The product to calculate profit for.

        Returns:
            float: The estimated hourly profit.
        """
        spread = product.spread
        instant_buy_hourly = product.instant_buy_hourly
        instant_sell_hourly = product.instant_sell_hourly
        
        quantity_transacted = min(instant_buy_hourly, instant_sell_hourly)

        marketshare = min(self.products_marketshare[product.product_id]["buy_score"], self.products_marketshare[product.product_id]["sell_score"])

        profit = marketshare * spread * quantity_transacted
        
        return profit
    
    def get_bz_limit(self, product: Product) -> float:
        """
        An estimate of how much it will cost to keep your order at the top of the market for an hour

        Args:
            product (Product): The product to calculate the limit for.

        Returns:
            float: The estimated bazaar limit cost.
        """
        instant_buy_hourly = product.instant_buy_hourly
        instant_sell_hourly = product.instant_sell_hourly
        
        quantity_transacted = min(instant_buy_hourly, instant_sell_hourly)
        bz_limit = quantity_transacted * (product.buy_order_price + product.sell_order_price)

        return bz_limit

    def get_best_products(self) -> List[Product]:
        """
        Retrieves and ranks the best products to flip.

        Returns:
            List[Product]: A list of the top products sorted by profit.
        """
        products = self.data["products"]
        top_flips = []

        for item, summary in products.items():
            product = self.parse_product(item, summary)
            if product is None:
                continue

            product.profit = self.get_hourly_profit(product)
            product.bz_limit = self.get_bz_limit(product)
        
            top_flips.append(product)

        top_flips.sort(key=lambda product: product.profit, reverse=True)
        filter_by_bz_limit(top_flips, 0, 1000000000)
        filter_by_volume(top_flips, 0, 10)

        return top_flips
    

if __name__ == "__main__":
    finder = ProductFinder()
    top_flips = finder.get_best_products()

    print(f"Hourly Profit --- Product --- instant_buy_hourly --- instant_sell_hourly --- BZ Limit")
    for product in top_flips[:1000]:
        print(f"${product.profit:,.2f}", product.product_id, f"{product.instant_buy_hourly:,.2f}", f"{product.instant_sell_hourly:,.2f}", f"${product.bz_limit:,.2f}")

