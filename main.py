
"""
Fyers LTP and Margin Calculator
Fetches LTP for symbols from CSV, creates ATM contracts, and calculates margins
Author: Trading Bot Assistant
"""

import csv
import math
import requests
import json
import base64
import time
import pyotp
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta, TH
from typing import Dict, List, Tuple, Optional
import re
from fyers_apiv3 import fyersModel
from urllib.parse import parse_qs, urlparse

# ============================= CONFIGURATION ============================= #
# You need to replace these with your actual credentials
# Create a file named 'conf.py' with your Fyers credentials

try:
    import conf as cf_fyers  # Your Fyers config file
    FY_ID = cf_fyers.FY_ID
    TOTP_KEY = cf_fyers.TOTP_KEY
    PIN = cf_fyers.PIN
    app_id = cf_fyers.app_id
    secret_id = cf_fyers.secret_id
    app_redirect = cf_fyers.app_redirect
except ImportError:
    print("⚠️ Please create a conf.py file with your Fyers credentials")
    print("Required variables: FY_ID, TOTP_KEY, PIN, app_id, secret_id, app_redirect")
    # Demo credentials for testing (replace with actual)
    FY_ID = "YOUR_FYERS_ID"
    TOTP_KEY = "YOUR_TOTP_KEY"
    PIN = "YOUR_PIN"
    app_id = "YOUR_APP_ID"
    secret_id = "YOUR_SECRET_ID"
    app_redirect = "YOUR_REDIRECT_URI"

# Margin filter (in INR)
MAX_MARGIN_FILTER = 20000  # Default: 20,000 INR

# CSV file path
CSV_FILE_PATH = "F:\\RASHMI\\RASHMI-MARKET_APPLICATION\\fo_mktlots.csv"

# ============================= UTILITY FUNCTIONS ============================= #

def get_expiry_code(index: str) -> str:
    """Generate expiry code for different indices based on current date"""
    now = datetime.now()
    yy = now.strftime("%y")

    if index in ("BANKNIFTY", "STOCK") or index == "NIFTY":
        # For NIFTY, we'll determine if it's weekly or monthly
        next_thursday = now + relativedelta(weekday=TH(1))
        last_thursday = (now + relativedelta(day=31, weekday=TH(-1)))

        if next_thursday.date() == last_thursday.date():
            # Last Thursday - use monthly format
            return now.strftime(f"{yy}%b").upper()
        else:
            # Weekly expiry format for NIFTY
            fyers_month_code = {
                1: "1", 2: "2", 3: "3", 4: "4", 5: "5", 6: "6",
                7: "7", 8: "8", 9: "9", 10: "O", 11: "N", 12: "D"
            }
            m = now.month
            d = next_thursday.day
            return f"{yy}{fyers_month_code[m]}{d:02d}"

    # Monthly format for other indices
    return now.strftime(f"{yy}%b").upper()

def load_strike_intervals_from_file(filename: str) -> dict:
    strike_intervals = {}
    with open(filename, 'r', encoding='utf-8') as f:
        next(f)  # Skip date line if present
        reader = csv.DictReader(f)
        for row in reader:
            symbol = row['Symbol'].strip()
            step_value = float(row['Step Value'])
            # Store the smallest step value if multiple entries exist
            if symbol not in strike_intervals or step_value < strike_intervals[symbol]:
                strike_intervals[symbol] = step_value
    return strike_intervals

def calculate_atm_strike(ltp: float, symbol: str) -> int:
    """Calculate At-The-Money strike price based on LTP and symbol"""

    # Define strike intervals for different symbols
    strike_intervals = load_strike_intervals_from_file('F:\\RASHMI\\RASHMI-MARKET_APPLICATION\\gaps.csv')

    # Default strike interval for stocks
    interval = strike_intervals.get(symbol, 50)

    # For NIFTY, use 50 point intervals
    if symbol == 'NIFTY':
        # Round to nearest 50
        val2 = math.fmod(ltp, 50)
        val3 = 50 if val2 >= 25 else 0
        atm = ltp - val2 + val3
        return int(atm)

    # For BANKNIFTY, use 100 point intervals
    elif symbol == 'BANKNIFTY':
        # Round to nearest 100
        val2 = math.fmod(ltp, 100)
        val3 = 100 if val2 >= 50 else 0
        atm = ltp - val2 + val3
        return int(atm)

    # Generic calculation for other symbols
    else:
        val1 = math.floor(ltp / interval) * interval
        val2 = math.ceil(ltp / interval) * interval
        return int(val1 if abs(ltp - val1) < abs(ltp - val2) else val2)

def convert_symbol_to_fyers_format(symbol: str) -> str:
    """Convert symbol to Fyers format"""

    # Index symbols mapping
    index_mapping = {
        'NIFTY': 'NSE:NIFTY50-INDEX',
        'BANKNIFTY': 'NSE:NIFTYBANK-INDEX',
        'FINNIFTY': 'NSE:FINNIFTY-INDEX',
        'MIDCPNIFTY': 'NSE:MIDCPNIFTY-INDEX',
        'NIFTY NEXT 50': 'NSE:NIFTYNXT50-INDEX',
        'SENSEX': 'BSE:SENSEX-INDEX'
    }

    # If it's an index, return the mapped format
    if symbol in index_mapping:
        return index_mapping[symbol]

    # For individual stocks, assume NSE equity format
    return f"NSE:{symbol}-EQ"

def create_option_symbol(base_symbol: str, strike: int, option_type: str) -> str:
    """Create Fyers format option symbol"""

    # Get expiry code
    if base_symbol in ['NIFTY', 'BANKNIFTY', 'FINNIFTY', 'MIDCPNIFTY', 'NIFTY NEXT 50']:
        expiry_code = get_expiry_code(base_symbol)
    else:
        expiry_code = get_expiry_code('STOCK')

    # Map symbol names for options
    option_symbol_mapping = {
        'NIFTY': 'NIFTY',
        'BANKNIFTY': 'BANKNIFTY',
        'FINNIFTY': 'FINNIFTY',
        'MIDCPNIFTY': 'MIDCPNIFTY',
        'NIFTY NEXT 50': 'NIFTYNXT50'
    }

    option_base = option_symbol_mapping.get(base_symbol, base_symbol)

    return f"NSE:{option_base}{expiry_code}{strike}{option_type}"

# ============================= FYERS API CLASS ============================= #

class FyersAPI:
    """Fyers API handler for authentication and data fetching"""

    def __init__(self):
        self.fyers = None
        self.access_token = None

    def generate_access_token(self) -> str:
        """Generate Fyers access token using TOTP and PIN"""
        try:
            def encode(s): 
                return base64.b64encode(str(s).encode()).decode()

            # Step 1: Send login OTP
            otp_res = requests.post(
                "https://api-t2.fyers.in/vagator/v2/send_login_otp_v2", 
                json={"fy_id": encode(FY_ID), "app_id": "2"}
            ).json()

            if otp_res.get('s') != 'ok':
                raise Exception(f"OTP request failed: {otp_res}")

            time.sleep(5)

            # Step 2: Verify OTP using TOTP
            otp = pyotp.TOTP(TOTP_KEY).now()
            otp_verify_res = requests.post(
                "https://api-t2.fyers.in/vagator/v2/verify_otp", 
                json={"request_key": otp_res["request_key"], "otp": otp}
            ).json()

            if otp_verify_res.get('s') != 'ok':
                raise Exception(f"OTP verification failed: {otp_verify_res}")

            # Step 3: Verify PIN
            session = requests.Session()
            pin_res = session.post(
                "https://api-t2.fyers.in/vagator/v2/verify_pin_v2", 
                json={
                    "request_key": otp_verify_res["request_key"], 
                    "identity_type": "pin", 
                    "identifier": encode(PIN)
                }
            ).json()

            if pin_res.get('s') != 'ok':
                raise Exception(f"PIN verification failed: {pin_res}")

            session.headers.update({
                'authorization': f"Bearer {pin_res['data']['access_token']}"
            })

            # Step 4: Generate auth code
            auth_code_url = session.post(
                "https://api-t1.fyers.in/api/v3/token", 
                json={
                    "fyers_id": FY_ID, 
                    "app_id": app_id[:-4], 
                    "redirect_uri": app_redirect,
                    "appType": "100", 
                    "response_type": "code", 
                    "state": "None"
                }
            ).json()

            if auth_code_url.get('s') != 'ok':
                raise Exception(f"Auth code generation failed: {auth_code_url}")

            # Extract auth code from URL
            auth_code = parse_qs(urlparse(auth_code_url['Url']).query)['auth_code'][0]

            # Step 5: Generate access token
            session_model = fyersModel.SessionModel(
                client_id=app_id, 
                secret_key=secret_id, 
                redirect_uri=app_redirect, 
                response_type="code", 
                grant_type="authorization_code"
            )
            session_model.set_token(auth_code)
            token_response = session_model.generate_token()

            if token_response.get('s') != 'ok':
                raise Exception(f"Token generation failed: {token_response}")

            self.access_token = token_response['access_token']
            return self.access_token

        except Exception as e:
            print(f"❌ Authentication failed: {e}")
            return None

    def initialize_fyers_model(self):
        """Initialize Fyers model with access token"""
        if not self.access_token:
            self.access_token = self.generate_access_token()

        if self.access_token:
            self.fyers = fyersModel.FyersModel(
                client_id=app_id, 
                token=self.access_token, 
                is_async=False
            )
            return True
        return False

    def get_ltp(self, symbol: str) -> float:
        """Get Last Traded Price for a symbol"""
        try:
            if not self.fyers:
                if not self.initialize_fyers_model():
                    return 0.0

            data = {"symbols": symbol}
            response = self.fyers.quotes(data)

            if response.get('s') == 'ok' and response.get('d'):
                ltp = response['d'][0]['v'].get('lp', 0)
                return float(ltp) if ltp else 0.0

            return 0.0

        except Exception as e:
            print(f"❌ Error fetching LTP for {symbol}: {e}")
            return 0.0

    def get_margin_requirement(self, symbol: str, qty: int, side: int = 1) -> float:
        """Get margin requirement for a symbol (estimated)"""
        try:
            if not self.fyers:
                if not self.initialize_fyers_model():
                    return 0.0

            # Try to use span margin API
            data = {
                "symbol": symbol,
                "qty": qty,
                "side": side,  # 1 for buy, -1 for sell
                "type": 1,     # Market order
                "productType": "CNC"
            }

            response = requests.post(
                "https://api.fyers.in/api/v3/span_margin",
                headers={
                    "Authorization": f"{app_id}:{self.access_token}",
                    "Content-Type": "application/json"
                },
                json=data
            )

            if response.status_code == 200:
                margin_data = response.json()
                if margin_data.get('s') == 'ok':
                    return float(margin_data.get('total', 0))

            # Fallback: Estimate margin based on LTP
            ltp = self.get_ltp(symbol)
            if ltp > 0:
                # For options buying, margin is approximately equal to premium
                if 'CE' in symbol or 'PE' in symbol:
                    return ltp * qty
                else:
                    # For equity, assume 20% margin
                    return ltp * qty * 0.2

            return 0.0

        except Exception as e:
            print(f"❌ Error calculating margin for {symbol}: {e}")
            return 0.0

# ============================= MAIN PROCESSING CLASS ============================= #

class LTPMarginCalculator:
    """Main class to process symbols and calculate margins"""

    def __init__(self, csv_file: str, margin_filter: float):
        self.csv_file = csv_file
        self.margin_filter = margin_filter
        self.fyers_api = FyersAPI()
        self.results = []

    def read_symbols_from_csv(self) -> List[Tuple[str, int]]:
        """Read symbols and lot sizes from CSV file"""
        symbols = []
        try:
            with open(self.csv_file, 'r', encoding='utf-8') as file:
                reader = csv.DictReader(file)
                for row in reader:
                    symbol = row['Symbol'].strip()
                    lot_size = int(row['Lot Size'].strip())
                    symbols.append((symbol, lot_size))

            print(f"✅ Loaded {len(symbols)} symbols from {self.csv_file}")
            return symbols

        except Exception as e:
            print(f"❌ Error reading CSV file: {e}")
            return []

    def process_symbol(self, symbol: str, lot_size: int) -> Optional[Dict]:
        """Process a single symbol and return results"""
        try:
            print(f"🔍 Processing {symbol}...")

            # Convert to Fyers format and get LTP
            fyers_symbol = convert_symbol_to_fyers_format(symbol)
            ltp = self.fyers_api.get_ltp(fyers_symbol)

            if ltp <= 0:
                print(f"⚠️ No LTP data for {symbol}")
                return None

            # Calculate ATM strike
            atm_strike = calculate_atm_strike(ltp, symbol)

            # Create ATM CE and PE contracts
            ce_symbol = create_option_symbol(symbol, atm_strike, 'CE')
            pe_symbol = create_option_symbol(symbol, atm_strike, 'PE')

            # Get LTP for CE and PE
            ce_ltp = self.fyers_api.get_ltp(ce_symbol)
            pe_ltp = self.fyers_api.get_ltp(pe_symbol)

            # Calculate margins
            ce_margin = self.fyers_api.get_margin_requirement(ce_symbol, lot_size) if ce_ltp > 0 else 0
            pe_margin = self.fyers_api.get_margin_requirement(pe_symbol, lot_size) if pe_ltp > 0 else 0

            # Create result dictionary
            result = {
                'symbol': symbol,
                'ltp': ltp,
                'atm_strike': atm_strike,
                'ce_contract': ce_symbol,
                'ce_ltp': ce_ltp,
                'ce_margin': ce_margin,
                'pe_contract': pe_symbol,
                'pe_ltp': pe_ltp,
                'pe_margin': pe_margin,
                'lot_size': lot_size
            }

            return result

        except Exception as e:
            print(f"❌ Error processing {symbol}: {e}")
            return None

    def filter_by_margin(self, results: List[Dict]) -> List[Dict]:
        """Filter results based on margin requirements"""
        filtered = []

        for result in results:
            if (result['ce_margin'] > 0 and result['ce_margin'] <= self.margin_filter) or \
               (result['pe_margin'] > 0 and result['pe_margin'] <= self.margin_filter):
                filtered.append(result)

        return filtered

    def format_output(self, results: List[Dict]) -> str:
        """Format results in the requested output format"""
        output_lines = []
        output_lines.append("=" * 100)
        output_lines.append("FYERS LTP AND MARGIN CALCULATOR RESULTS")
        output_lines.append(f"Margin Filter: Under ₹{self.margin_filter:,.2f}")
        output_lines.append("=" * 100)
        output_lines.append()

        for result in results:
            symbol = result['symbol']
            ltp = result['ltp']
            atm_strike = result['atm_strike']

            # CE Results
            if result['ce_ltp'] > 0 and result['ce_margin'] <= self.margin_filter:
                ce_contract = f"ATM{atm_strike}CE"
                output_lines.append(
                    f"{symbol:<15} | LTP: ₹{ltp:>8.2f} | {ce_contract:<12} | "
                    f"LTP: ₹{result['ce_ltp']:>6.2f} | Margin: ₹{result['ce_margin']:>8.2f}"
                )

            # PE Results
            if result['pe_ltp'] > 0 and result['pe_margin'] <= self.margin_filter:
                pe_contract = f"ATM{atm_strike}PE"
                output_lines.append(
                    f"{symbol:<15} | LTP: ₹{ltp:>8.2f} | {pe_contract:<12} | "
                    f"LTP: ₹{result['pe_ltp']:>6.2f} | Margin: ₹{result['pe_margin']:>8.2f}"
                )

            output_lines.append("-" * 100)

        return "\n".join(output_lines)

    def run(self):
        """Main execution method"""
        print("🚀 Starting Fyers LTP and Margin Calculator...")
        print(f"📊 Margin Filter: Under ₹{self.margin_filter:,.2f}")
        print()

        # Initialize Fyers API
        if not self.fyers_api.initialize_fyers_model():
            print("❌ Failed to initialize Fyers API")
            return

        print("✅ Fyers API initialized successfully")
        print()

        # Read symbols from CSV
        symbols = self.read_symbols_from_csv()
        if not symbols:
            return

        # Process each symbol
        all_results = []
        for symbol, lot_size in symbols:
            result = self.process_symbol(symbol, lot_size)
            if result:
                all_results.append(result)
            time.sleep(1)  # Rate limiting

        # Filter by margin
        filtered_results = self.filter_by_margin(all_results)

        if not filtered_results:
            print(f"❌ No symbols found with margin under ₹{self.margin_filter:,.2f}")
            return

        # Display results
        output = self.format_output(filtered_results)
        print(output)

        # Save results to file
        with open('margin_results.txt', 'w', encoding='utf-8') as f:
            f.write(output)

        print(f"\n📝 Results saved to 'margin_results.txt'")
        print(f"✅ Found {len(filtered_results)} symbols within margin limit")

# ============================= MAIN EXECUTION ============================= #

def main():
    """Main function"""
    print("=" * 60)
    print("    FYERS LTP AND MARGIN CALCULATOR")
    print("=" * 60)
    print()

    # You can modify these parameters
    csv_file = CSV_FILE_PATH
    margin_filter = MAX_MARGIN_FILTER

    # Create and run calculator
    calculator = LTPMarginCalculator(csv_file, margin_filter)
    calculator.run()

if __name__ == "__main__":
    main()
