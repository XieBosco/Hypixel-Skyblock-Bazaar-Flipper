import requests
import pprint
from typing import List, Dict

# Tax in decimal format
TAX_RATE = 0.02
API_URL = "https://api.hypixel.net/v2/skyblock/bazaar"

# instant_buy_weekly = IBW
# instant_sell_weekly = ISW
IBW_THRESHOLD = 500
ISW_THRESHOLD = 500

DAILY_BZ_LIMIT = 15000000000 # 30 billion


def get_general_info(
        data: Dict[str, bool | int | Dict[str, str | List[Dict[str, int]] | Dict[str, int | str]]],
        num_items: int,
        IBW_threshold: int = 0,
        ISW_threshold: int = 0
) -> List[tuple[str, int, int, int]]:
    products = data["products"]


    best_items = [("None", 0, 0, 0)]*(num_items)

    for item, summary in products.items():
        sell_summary = summary["sell_summary"]
        buy_summary = summary["buy_summary"]
        quick_status = summary["quick_status"]

        if sell_summary and buy_summary:
            buy_order_price = sell_summary[0]["pricePerUnit"]
            sell_order_price = buy_summary[0]["pricePerUnit"]

            instant_buy_weekly = quick_status["buyMovingWeek"]
            instant_sell_weekly = quick_status["sellMovingWeek"]

            spread = (sell_order_price*(1 - TAX_RATE))- buy_order_price

            if spread > best_items[num_items - 1][1]:
                if instant_buy_weekly >= IBW_threshold and instant_sell_weekly >= ISW_threshold:
                    best_items.pop()
                    best_items.append((item, spread, instant_buy_weekly/168, instant_sell_weekly/168))
                    best_items.sort(key=lambda item : item[1], reverse=True)


    print(f"Price --- Product --- Insta Buy Volume Hourly --- Insta Sell Volume Hourly")
    for item in best_items:
        print(f"${item[1]:,.2f}", item[0], round(item[2]), round(item[3]))

def get_best_profit(
        data: Dict[str, bool | int | Dict[str, str | List[Dict[str, int]] | Dict[str, int | str]]],
        num_items: int,
        IBW_threshold: int = 0,
        ISW_threshold: int = 0
) -> List[tuple[str, int, int, int]]:
    products = data["products"]


    best_profit = [("None", 0, 0, 0)]*(num_items)

    for item, summary in products.items():
        sell_summary = summary["sell_summary"]
        buy_summary = summary["buy_summary"]
        quick_status = summary["quick_status"]

        if sell_summary and buy_summary:
            buy_order_price = sell_summary[0]["pricePerUnit"]
            sell_order_price = buy_summary[0]["pricePerUnit"]

            instant_buy_weekly = quick_status["buyMovingWeek"]
            instant_sell_weekly = quick_status["sellMovingWeek"]

            # 168 hours in one week
            instant_buy_hourly = instant_buy_weekly/168
            instant_sell_hourly = instant_sell_weekly/168
            spread = (sell_order_price*(1 - TAX_RATE)) - buy_order_price

            hourly_profit = spread * min(instant_buy_hourly, instant_sell_hourly)


            if hourly_profit > best_profit[num_items - 1][1]:
                if instant_buy_weekly >= IBW_threshold and instant_sell_weekly >= ISW_threshold:
                    # If all products are transacted without refreshing orders
                    bazaar_limit = min(instant_buy_hourly, instant_sell_hourly) * (buy_order_price + sell_order_price)

                    best_profit.pop()
                    best_profit.append((item, hourly_profit, instant_buy_hourly, instant_sell_hourly, bazaar_limit))
                    best_profit.sort(key=lambda item : item[1], reverse=True)

    print(f"Profit Hourly --- Product --- Insta Buy Volume Hourly --- Insta Sell Volume Hourly --- bazaar limit hourly")
    for item in best_profit:
        print(f"${item[1]:,.2f}", item[0], round(item[2]), round(item[3]), f"${item[4]:,.2f}")



if __name__ == "__main__":

    data = requests.get(API_URL).json()

    if data["success"]:

        # get_general_info(data, 20, IBW_threshold=IBW_THRESHOLD, ISW_threshold=ISW_THRESHOLD)
        get_best_profit(data, 100, IBW_threshold=0, ISW_threshold=0)
    
    else:
        print(f"Failed to get request: {data["cause"]}")
