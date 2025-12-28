# Hypixel Skyblock Bazaar Flipper

A sophisticated, automated trading bot designed for the Hypixel Skyblock Bazaar. Built on the **Minescript** framework, this tool leverages real-time API data to identify high-margin flips, manage orders autonomously, and execute trades with human-like behavioral patterns to maximize profit while minimizing detection risk.

## 🚀 Features

### 🧠 Intelligent Market Analysis
- **Algorithmic Product Selection**: Uses `get_best_product.py` to analyze the entire bazaar instantly.
- **Profit Calculation**: Ranks items based on spread, weekly/hourly volume, and estimated market share.
- **Dynamic Filtering**: Automatically filters out low-volume items or those exceeding bazaar limits.

### ⚡ Automated Order Management
- **Real-time Monitoring**: Continuously checks the status of your orders against the Hypixel API.
- **Smart Undercutting**: Detects when your orders are "OUTDATED" (undercut) and automatically cancels and reposts them at the competitive price.
- **Order Lifecycle**: Handles the entire loop: `Buy Order` -> `Claim` -> `Sell Offer` -> `Claim Profit`.

### 🛡️ Human-Like Behavior (Anti-Detection)
- **Advanced Randomization**: The `HumanDelay` class (`randomizer.py`) uses log-normal distributions and momentum algorithms to simulate realistic reaction times.
- **Variable WPM**: Simulates typing delays based on variable words-per-minute.

### ⚙️ Robust Error Handling
- **Server Safety**: Detects server reboots and pauses execution.
- **Limbo Detection**: Handles being sent to limbo.
- **Limit Protection**: Monitors daily bazaar limits to prevent API errors.

## 📂 Project Structure

- **`bzz.py`**: The main entry point. Orchestrates the bot's lifecycle, state management, and automation loops.
- **`get_best_product.py`**: The "brain" of the operation. Fetches API data and calculates the most profitable items to flip.
- **`utilities.py`**: Helper functions for NBT parsing, API requests, and logging.
- **`randomizer.py`**: Contains the `HumanDelay` logic for realistic timing.
- **`data_structures.py`**: Defines core classes like `Order`, `OrderType`, and `Product`.
- **`constants.py`**: Configuration for API endpoints, GUI slot IDs, and timing thresholds.
- **`config.txt` / `product_list.json`**: Configuration files for tracked items and settings.

## 🛠️ Prerequisites

1.  **Minecraft Java Edition** (Compatible version for Minescript).
2.  **Minescript Mod**: Must be installed in your `.minecraft/mods` folder.
3.  **Python 3.x**: Installed and configured within the Minescript environment.

## 📦 Installation

1.  **Clone the Repository**:
    Place the project files into your Minescript scripts folder (usually `%appdata%/.minecraft/minescript`).

2.  **Install Dependencies**:
    Ensure the required Python packages in requirements.txt are installed in your Minescript Python environment:

    *(Note: Minescript usually handles standard library imports, but external requests are needed for the API).*

3.  **Configuration**:
    - Edit `constants.py` to adjust `MAX_BUY_COST` or `HUMAN_WPM` if necessary.
    - Ensure `bazaarConversions.json` and `bazaar_scores.json` are present for ID mapping and market scoring.

## ▶️ Usage

1.  Launch Minecraft with Minescript.
2.  Open the Minescript console or chat.
3.  Run the script:
    ```
    /bzz
    ```
4.  The bot will begin fetching API data, analyzing the market, and managing your orders.

## ⚠️ Disclaimer

**Use at your own risk.** Automated trading bots may violate the Hypixel Skyblock Terms of Service. This software is provided for educational purposes only. The authors are not responsible for any bans, punishments, or lost in-game currency resulting from the use of this tool.
