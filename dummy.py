
import math

def calculate_atm_strike(ltp: float) -> int:
        """Calculate ATM strike based on LTP and strike interval"""

        # Get interval for symbol, default to price-based logic
        interval = 2.5
        if not interval:
            # Price-based interval determination
            if ltp < 500:
                interval = 5
            elif ltp < 1000:
                interval = 10
            elif ltp < 2000:
                interval = 20
            elif ltp < 5000:
                interval = 50
            else:
                interval = 100

        # Calculate ATM strike

        atm_strike = math.ceil(ltp / interval) * interval
        return int(atm_strike)

print(calculate_atm_strike(212))