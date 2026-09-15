from enum import Enum
from dataclasses import dataclass

class OrderType(Enum):
    BUY = "Buy Order"
    SELL = "Sell Offer"

@dataclass
class Order:
    """
    Represents a bazaar order.

    Attributes:
        product_id (str): The unique identifier for the product (e.g., "ENCHANTED_IRON").
        product_name (str): The display name of the product.
        amount (int): The quantity of items in the order.
        price_per_unit (float): The price per unit of the item.
        order_type (OrderType): The type of order (BUY or SELL).
        slot (int): The inventory slot index where the order is located.
        status (str): The current status of the order (e.g., "SEARCHING", "MATCHED", "OUTDATED", "BEST").
    """
    product_id: str
    product_name: str
    amount: int
    price_per_unit: float
    order_type: OrderType
    slot: int
    status: str = "SEARCHING"

    def __eq__(self, other):
        if not isinstance(other, Order):
            return False
        return (self.product_id == other.product_id and 
                self.price_per_unit == other.price_per_unit and 
                self.order_type == other.order_type and
                self.slot == other.slot)

@dataclass
class ProductTrackerObj:
    """
    Represents a product to be tracked by the bot.

    Attributes:
        product_id (str): The unique identifier for the product.
        order_type (OrderType): The type of order to track (BUY or SELL).
    """
    product_id: str
    order_type: OrderType
