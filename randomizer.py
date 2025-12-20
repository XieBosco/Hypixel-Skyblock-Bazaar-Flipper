import random
import time
import math

class HumanDelay:
    def __init__(self):
        self.last_delay = None

    def get_delay(self, min_seconds=2.5, max_seconds=6, skew=0.5, momentum=0.4) -> float:
        """
        min_seconds: Absolute minimum wait time (physical limit).
        max_seconds: Target maximum wait time.
        skew: Controls the 'tail' (0.1 = tight, 0.5 = long tail of slow clicks).
        momentum: 0.0 to 0.9. How much the previous delay affects the new one.
                  (Simulates getting into a rhythm or being tired).
        """
        
        # 1. Log-Normal Generation
        # Calculates parameters so the distribution peaks near the average of min/max
        target = (min_seconds + max_seconds) / 2
        mu = math.log(target) - (skew**2) / 2
        
        # Generate raw log-normal value
        raw_delay = random.lognormvariate(mu, skew)
        
        # 2. Autocorrelation (Momentum)
        if self.last_delay is None:
            self.last_delay = raw_delay
            
        # Blend: Keep some of the previous speed, add some new randomness
        # This creates "streaks" of faster or slower actions
        current_delay = (self.last_delay * momentum) + (raw_delay * (1 - momentum))
        
        # 3. Boundaries
        # Hard limit on min (physically impossible to be 0), soft limit on max
        if current_delay < min_seconds:
            current_delay = min_seconds + (current_delay - min_seconds) * skew
        
        # If we go over max, pull it back gently (soft cap)
        if current_delay > max_seconds:
            current_delay = max_seconds + (current_delay - max_seconds) * skew
            
        self.last_delay = current_delay
        
        # print(f"Delay: {current_delay:.3f}s")
        
        return current_delay
    
    def wait(self, min_seconds=2.5, max_seconds=6, skew=0.5, momentum=0.4) -> None:
        """
        Sleeps for a human-like delay based on the parameters.
        """
        time.sleep(self.get_delay(min_seconds, max_seconds, skew, momentum))

    def typing_delay(self, text: str, wpm: int = 100) -> None:
        """
        Simulates human typing delay based on words per minute (wpm).
        """
        wpm = random.normalvariate(wpm, wpm * 0.05)
        chracters_per_word = 5
        seconds_per_minute = 60
        spc = (seconds_per_minute / (wpm * chracters_per_word)) # seconds per character
        delay = len(text) * spc
        time.sleep(delay)


if __name__ == "__main__":

    # Example Usage
    human = HumanDelay()

    # Simulate 5 clicks
    print("Simulating 5 human-like delays:")
    for _ in range(5):
        human.get_delay()
