import random
import time
import math
import matplotlib.pyplot as plt
from randomizer import HumanDelay

# Visualization
human = HumanDelay()
delays = []

print("Generating 1000 samples...")
for _ in range(100000):
    # We use return value instead of sleep for visualization
    d = human.get_delay(min_seconds=0.6, max_seconds=0.8, skew=0.4, momentum=0.5)
    delays.append(d)

plt.figure(figsize=(10, 6))

# Histogram
plt.subplot(2, 1, 1)
plt.hist(delays, bins=50, color='skyblue', edgecolor='black')
plt.title('Distribution of Delays (Log-Normal + Momentum)')
plt.xlabel('Delay (seconds)')
plt.ylabel('Frequency')

# Line Plot (Time Series)
plt.subplot(2, 1, 2)
plt.plot(delays[:100], marker='o', markersize=2, linestyle='-', linewidth=0.5)
plt.title('First 100 Delays (Showing Autocorrelation/Rhythm)')
plt.xlabel('Click Number')
plt.ylabel('Delay (seconds)')

plt.tight_layout()
plt.show()
