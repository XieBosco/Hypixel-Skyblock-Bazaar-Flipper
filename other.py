import requests
import time
# import minescript
# from utils.minescript_plus import Inventory, mc
import pprint

API_URL = "https://api.hypixel.net/v2/skyblock/bazaar"

data = requests.get(API_URL).json()

for product in data["products"]:
    if product.startswith("END"):
        print(product)

