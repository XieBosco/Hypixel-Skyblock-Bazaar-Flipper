import requests
import time
# import minescript
# from utils.minescript_plus import Inventory, mc, Screen
import pprint
import random
# from bzz import open_bazaar_orders, seek_manage_orders

API_URL = "https://api.hypixel.net/v2/skyblock/bazaar"

data = requests.get(API_URL).json()

for product in data["products"]:
    pass

pprint.pprint(data["products"]["MANA_VAMPIRE_V"])

# open_bazaar_orders()
# time.sleep(3)
# minescript.echo(minescript.container_get_items())

# time.sleep(3)

# Screen.close_screen()
# time.sleep(1)
# minescript.press_key_bind("key.attack", False)



