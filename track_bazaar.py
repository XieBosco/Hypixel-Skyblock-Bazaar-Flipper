import requests
import time
import json
import sys
from datetime import datetime

# --- CONFIGURATION ---
API_URL = "https://api.hypixel.net/skyblock/bazaar"
RENEWAL_TIME = 15.0  # Seconds it takes to notice and fix a beaten order
OUTPUT_FILE = "bazaar_market_share_results.txt"

# --- STATE MANAGEMENT ---
class ProductState:
    def __init__(self, product_id):
        self.product_id = product_id
        
        # BUY ORDER STATE
        self.my_buy_price = 0.0
        self.buy_status = "active" # active, recovering
        self.buy_recovery_end = 0.0
        self.buy_time_controlled = 0.0
        
        # SELL ORDER STATE
        self.my_sell_price = 0.0
        self.sell_status = "active"
        self.sell_recovery_end = 0.0
        self.sell_time_controlled = 0.0

def fetch_bazaar():
    """Fetches the Bazaar data safely."""
    try:
        response = requests.get(API_URL, timeout=10)
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        print(f"Error fetching API: {e}")
    return None

def get_best_prices(product_data):
    """Extracts best buy and sell prices from product data."""
    # Buy Order: We want to be the HIGHEST buyer.
    # Sell Order: We want to be the LOWEST seller.
    
    # If buy_summary is empty, price is 0
    best_buy = 0.0
    if product_data['sell_summary']:
        best_buy = product_data['sell_summary'][0]['pricePerUnit']
        
    best_sell = 0.0
    if product_data['buy_summary']:
        best_sell = product_data['buy_summary'][0]['pricePerUnit']
    else:
        # If no sellers, usually implies max price or inactive, treat as high
        best_sell = float('inf')

    return best_buy, best_sell

def main():
    print(f"--- Hypixel Bazaar Market Share Simulator ---")
    print(f"Renewal Time: {RENEWAL_TIME}s")
    print(f"Press CTRL+C to stop the test and save results.")
    print("Initializing...")

    # Initial Fetch to populate products
    initial_data = fetch_bazaar()
    if not initial_data or not initial_data.get('success'):
        print("Failed to fetch initial Bazaar data.")
        return

    products = initial_data['products']
    states = {}
    
    # Initialize all products with current prices
    for pid, data in products.items():
        state = ProductState(pid)
        market_buy, market_sell = get_best_prices(data)
        
        # We start by placing orders at market price + epsilon
        state.my_buy_price = market_buy + 0.1
        state.my_sell_price = market_sell - 0.1
        states[pid] = state

    start_time = time.time()
    last_update_time = start_time
    last_api_timestamp = initial_data['lastUpdated']

    print(f"Tracking {len(states)} products. Simulation started.")

    try:
        while True:
            # Sleep briefly to avoid spamming local CPU, but poll frequently enough to catch updates
            time.sleep(1) 
            
            current_time = time.time()
            
            # Fetch Data
            data_json = fetch_bazaar()
            if not data_json or not data_json.get('success'):
                continue

            # Check if API actually updated (timestamp change)
            api_timestamp = data_json['lastUpdated']
            
            # If the API hasn't updated yet, we just wait.
            # However, we must handle "Recovery" logic continuously, 
            # because recovery is based on real time, not API ticks.
            
            # We calculate time delta for the simulation step
            dt = current_time - last_update_time
            last_update_time = current_time
            
            # Process every product
            for pid, p_data in data_json['products'].items():
                if pid not in states:
                    continue # Skip new items added mid-simulation
                
                s = states[pid]
                market_buy, market_sell = get_best_prices(p_data)

                # --- BUY ORDER LOGIC ---
                if s.buy_status == "recovering":
                    # Check if recovery time is over
                    if current_time >= s.buy_recovery_end:
                        s.buy_status = "active"
                        # Re-list at current top + 0.1
                        s.my_buy_price = market_buy + 0.1
                
                if s.buy_status == "active":
                    # Check if we are still top
                    # Note: We simulate that we ARE the market price if we are close enough
                    # If market > my_price, I lost.
                    if market_buy >= s.my_buy_price or market_buy <= s.my_buy_price - 0.2:
                        # I was outbid!
                        s.buy_status = "recovering"
                        s.buy_recovery_end = current_time + RENEWAL_TIME
                        # No points awarded for this dt (pessimistic approach)
                    else:
                        # I am holding the top spot
                        s.buy_time_controlled += dt

                # --- SELL ORDER LOGIC ---
                if s.sell_status == "recovering":
                    if current_time >= s.sell_recovery_end:
                        s.sell_status = "active"
                        s.my_sell_price = market_sell - 0.1
                
                if s.sell_status == "active":
                    # For selling, lower is better. If market < my_price, I lost.
                    if (market_sell != float("inf")) and (market_sell <= s.my_sell_price or market_sell >= s.my_sell_price + 0.2):
                        s.sell_status = "recovering"
                        s.sell_recovery_end = current_time + RENEWAL_TIME
                    else:
                        s.sell_time_controlled += dt
            
            # Small visual heartbeat
            sys.stdout.write(f"\rTime Elapsed: {int(current_time - start_time)}s | API Timestamp: {api_timestamp}")
            sys.stdout.flush()

    except KeyboardInterrupt:
        # END OF TEST
        total_duration = time.time() - start_time
        print(f"\n\nSimulation stopped after {total_duration:.2f} seconds.")
        print("Calculating results and writing to file...")
        
        results = []
        
        for pid, s in states.items():
            buy_score = 0.0
            if total_duration > 0:
                buy_score = s.buy_time_controlled / total_duration
            
            sell_score = 0.0
            if total_duration > 0:
                sell_score = s.sell_time_controlled / total_duration
            
            # Cap scores at 1.0 (float precision might cause 1.000001)
            buy_score = min(buy_score, 1.0)
            sell_score = min(sell_score, 1.0)
            
            results.append({
                "product": pid,
                "buy_score": round(buy_score, 4),
                "sell_score": round(sell_score, 4),
                "buy_time_seconds": round(s.buy_time_controlled, 2),
                "sell_time_seconds": round(s.sell_time_controlled, 2)
            })
        
        # Sort by Buy Score descending (easiest to control first)
        results.sort(key=lambda x: x['buy_score'], reverse=True)
        
        with open(OUTPUT_FILE, "w") as f:
            f.write(f"Bazaar Market Control Simulation\n")
            f.write(f"Duration: {total_duration:.2f} seconds\n")
            f.write(f"Renewal Time (Reaction Speed): {RENEWAL_TIME} seconds\n")
            f.write(f"{'-'*60}\n")
            f.write(f"{'PRODUCT_ID':<30} | {'BUY SCORE':<10} | {'SELL SCORE':<10}\n")
            f.write(f"{'-'*60}\n")
            for r in results:
                f.write(f"{r['product']:<30} | {r['buy_score']:<10} | {r['sell_score']:<10}\n")
        
        print(f"Done! Results written to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()