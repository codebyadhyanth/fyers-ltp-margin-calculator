
"""
Fyers LTP and ATM Options Margin Calculator - Optimized Version
Fetches real-time LTP, calculates ATM contracts, and computes margins
Uses dynamic strike intervals from NSE official data
Author: Trading Bot Assistant - Optimized Version
"""

import csv
import math
import requests
import json
import base64
import time
import pyotp
import os
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta, TH
from typing import Dict, List, Tuple, Optional, Union
import re
from fyers_apiv3 import fyersModel
from urllib.parse import parse_qs, urlparse

# ============================= CONFIGURATION ============================= #

class Config:
    """Configuration class for all settings"""

    # File paths
    CSV_FILE_PATH = "F:\\RASHMI\\RASHMI-MARKET_APPLICATION\\fo_mktlots.csv"
    STRIKE_INTERVALS_CSV = "F:\\RASHMI\\RASHMI-MARKET_APPLICATION\\gaps.csv"
    OUTPUT_FILE = "margin_results.txt"

    # Margin filter (in INR)
    MAX_MARGIN_FILTER = 20000

    # Rate limiting
    API_DELAY = 1  # seconds between API calls

    # Fyers credentials (import from conf.py)
    try:
        import conf as cf_fyers
        FY_ID = cf_fyers.FY_ID
        TOTP_KEY = cf_fyers.TOTP_KEY
        PIN = cf_fyers.PIN
        app_id = cf_fyers.app_id
        secret_id = cf_fyers.secret_id
        app_redirect = cf_fyers.app_redirect
    except ImportError:
        print("⚠️  Please create conf.py file with Fyers credentials")
        FY_ID = "YOUR_FYERS_ID"
        TOTP_KEY = "YOUR_TOTP_KEY"
        PIN = "YOUR_PIN"
        app_id = "YOUR_APP_ID"
        secret_id = "YOUR_SECRET_ID"
        app_redirect = "YOUR_REDIRECT_URI"

# ============================= UTILITY FUNCTIONS ============================= #

class Utils:
    """Utility functions for calculations and data processing"""

    @staticmethod
    def load_strike_intervals_from_file(filename: str) -> Dict[str, float]:
        """Load strike intervals from NSE official CSV file"""

        if not os.path.exists(filename):
            print(f"⚠️  Strike intervals file not found: {filename}")
            print("Using default intervals...")
            return Utils.get_default_intervals()

        strike_intervals = {}

        try:
            with open(filename, 'r', encoding='utf-8', newline='') as f:
                # Peek at the first line to see if it starts with 'Symbol'
                first_line = f.readline().strip()
                if not first_line.startswith('Symbol'):
                    # Skip this line, then continue with DictReader from next line
                    pass
                else:
                    # If first line is header, rewind by reopening or reset file pointer with seek(0) if needed
                    f.seek(0)

                reader = csv.DictReader(f)
                for row in reader:
                    symbol = row['Symbol'].strip()
                    step_value = float(row['Gap'])
                    if symbol not in strike_intervals or step_value < strike_intervals[symbol]:
                        strike_intervals[symbol] = step_value

            print(f"✅ Loaded {len(strike_intervals)} strike intervals from {filename}")
            return strike_intervals

        except Exception as e:
            print(f"❌ Error loading strike intervals: {e}")
            return Utils.get_default_intervals()

    @staticmethod
    def get_default_intervals() -> Dict[str, float]:
        """Fallback default intervals for major indices"""
        return {
            'NIFTY': 50,
            'BANKNIFTY': 100,
            'FINNIFTY': 50,
            'MIDCPNIFTY': 25,
            'NIFTY NEXT 50': 100,
            'SENSEX': 100
        }

    @staticmethod
    def get_expiry_code(symbol: str) -> str:
        """Generate expiry code based on symbol and current date"""
        now = datetime.now()
        yy = now.strftime("%y")

        # For indices, determine weekly vs monthly
        if symbol.upper() in ['NIFTY', 'BANKNIFTY', 'FINNIFTY', 'MIDCPNIFTY']:
            next_thursday = now + relativedelta(weekday=TH(1))
            last_thursday = now + relativedelta(day=31, weekday=TH(-1))

            # If next Thursday is the last Thursday, use monthly format
            if next_thursday.date() == last_thursday.date():
                return now.strftime(f"{yy}%b").upper()
            else:
                # Weekly format for NIFTY-like indices
                if symbol.upper() == 'NIFTY':
                    fyers_month_code = {
                        1: "1", 2: "2", 3: "3", 4: "4", 5: "5", 6: "6",
                        7: "7", 8: "8", 9: "9", 10: "O", 11: "N", 12: "D"
                    }
                    m = next_thursday.month
                    d = next_thursday.day
                    return f"{yy}{fyers_month_code[m]}{d:02d}"

        # Monthly format for other symbols
        return now.strftime(f"{yy}%b").upper()

    @staticmethod
    def calculate_atm_strike(ltp: float, symbol: str, intervals: Dict[str, float]) -> int:
        """Calculate ATM strike based on LTP and strike interval"""

        # Get interval for symbol, default to price-based logic
        interval = intervals.get(symbol.upper())

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

        atm_strike = (math.ceil(ltp / interval)) * interval
        return int(atm_strike)

    @staticmethod
    def convert_symbol_to_fyers_format(symbol: str) -> str:
        """Convert symbol to Fyers API format"""

        # Index mapping
        index_mapping = {
            'NIFTY': 'NSE:NIFTY50-INDEX',
            'BANKNIFTY': 'NSE:NIFTYBANK-INDEX', 
            'FINNIFTY': 'NSE:FINNIFTY-INDEX',
            'MIDCPNIFTY': 'NSE:MIDCPNIFTY-INDEX',
            'NIFTY NEXT 50': 'NSE:NIFTYNXT50-INDEX',
            'SENSEX': 'BSE:SENSEX-INDEX'
        }

        return index_mapping.get(symbol.upper(), f"NSE:{symbol.upper()}-EQ")

    @staticmethod
    def create_option_symbol(base_symbol: str, strike: int, option_type: str) -> str:
        """Create Fyers option symbol format"""

        expiry_code = Utils.get_expiry_code(base_symbol)

        # Option symbol mapping
        option_mapping = {
            'NIFTY': 'NIFTY',
            'BANKNIFTY': 'BANKNIFTY',
            'FINNIFTY': 'FINNIFTY', 
            'MIDCPNIFTY': 'MIDCPNIFTY',
            'NIFTY NEXT 50': 'NIFTYNXT50'
        }

        option_base = option_mapping.get(base_symbol.upper(), base_symbol.upper())
        return f"NSE:{option_base}{expiry_code}{strike}{option_type}"

# ============================= FYERS API CLASS ============================= #

class FyersAPI:
    """Optimized Fyers API handler with better error handling"""

    def __init__(self):
        self.fyers = None
        self.access_token = None
        self._authenticated = False

    def _encode(self, s: str) -> str:
        """Encode string to base64"""
        return base64.b64encode(str(s).encode()).decode()

    def generate_access_token(self) -> Optional[str]:
        """Generate Fyers access token with improved error handling"""
        try:
            # Step 1: Send login OTP
            print("🔐 Authenticating with Fyers API...")
            otp_res = requests.post(
                "https://api-t2.fyers.in/vagator/v2/send_login_otp_v2",
                json={"fy_id": self._encode(Config.FY_ID), "app_id": "2"},
                timeout=10
            ).json()

            if otp_res.get('s') != 'ok':
                raise Exception(f"OTP request failed: {otp_res.get('message', 'Unknown error')}")

            time.sleep(5)

            # Step 2: Verify OTP using TOTP
            otp = pyotp.TOTP(Config.TOTP_KEY).now()
            otp_verify_res = requests.post(
                "https://api-t2.fyers.in/vagator/v2/verify_otp",
                json={"request_key": otp_res["request_key"], "otp": otp},
                timeout=10
            ).json()

            if otp_verify_res.get('s') != 'ok':
                raise Exception(f"OTP verification failed: {otp_verify_res.get('message', 'Unknown error')}")

            # Step 3: Verify PIN
            session = requests.Session()
            pin_res = session.post(
                "https://api-t2.fyers.in/vagator/v2/verify_pin_v2",
                json={
                    "request_key": otp_verify_res["request_key"],
                    "identity_type": "pin",
                    "identifier": self._encode(Config.PIN)
                },
                timeout=10
            ).json()

            if pin_res.get('s') != 'ok':
                raise Exception(f"PIN verification failed: {pin_res.get('message', 'Unknown error')}")

            session.headers.update({
                'authorization': f"Bearer {pin_res['data']['access_token']}"
            })

            # Step 4: Generate auth code
            auth_code_url = session.post(
                "https://api-t1.fyers.in/api/v3/token",
                json={
                    "fyers_id": Config.FY_ID,
                    "app_id": Config.app_id[:-4],
                    "redirect_uri": Config.app_redirect,
                    "appType": "100",
                    "response_type": "code",
                    "state": "None"
                },
                timeout=10
            ).json()

            if auth_code_url.get('s') != 'ok':
                raise Exception(f"Auth code failed: {auth_code_url.get('message', 'Unknown error')}")

            # Extract auth code
            auth_code = parse_qs(urlparse(auth_code_url['Url']).query)['auth_code'][0]

            # Step 5: Generate access token
            session_model = fyersModel.SessionModel(
                client_id=Config.app_id,
                secret_key=Config.secret_id,
                redirect_uri=Config.app_redirect,
                response_type="code",
                grant_type="authorization_code"
            )
            session_model.set_token(auth_code)
            token_response = session_model.generate_token()

            if token_response.get('s') != 'ok':
                raise Exception(f"Token generation failed: {token_response.get('message', 'Unknown error')}")

            self.access_token = token_response['access_token']
            print("✅ Fyers authentication successful")
            return self.access_token

        except Exception as e:
            print(f"❌ Authentication failed: {e}")
            return None

    def initialize_fyers_model(self) -> bool:
        """Initialize Fyers model"""
        if self._authenticated:
            return True

        if not self.access_token:
            self.access_token = self.generate_access_token()

        if self.access_token:
            self.fyers = fyersModel.FyersModel(
                client_id=Config.app_id,
                token=self.access_token,
                is_async=False
            )
            self._authenticated = True
            return True
        return False

    def get_ltp(self, symbol: str) -> float:
        """Get Last Traded Price with better error handling"""
        try:
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

    def calculate_margin(self, ltp: float, lot_size: int) -> float:
        """Calculate margin as LTP * Lot Size (simplified)"""
        return ltp * lot_size

# ============================= MAIN PROCESSING CLASS ============================= #

class LTPMarginCalculator:
    """Optimized main calculator class"""

    def __init__(self, csv_file: str, margin_filter: float):
        self.csv_file = csv_file
        self.margin_filter = margin_filter
        self.fyers_api = FyersAPI()
        self.strike_intervals = Utils.load_strike_intervals_from_file(Config.STRIKE_INTERVALS_CSV)
        self.results = []

    def read_symbols_from_csv(self) -> List[Tuple[str, int]]:
        """Read symbols and lot sizes from CSV"""
        symbols = []

        if not os.path.exists(self.csv_file):
            print(f"❌ CSV file not found: {self.csv_file}")
            return symbols

        try:
            with open(self.csv_file, 'r', encoding='utf-8') as file:
                reader = csv.DictReader(file)
                for row in reader:
                    symbol = row['Symbol'].strip()
                    lot_size = int(row['Lot Size'].strip())
                    symbols.append((symbol, lot_size))

            print(f"✅ Loaded {len(symbols)} symbols from CSV")
            return symbols

        except Exception as e:
            print(f"❌ Error reading CSV: {e}")
            return []

    def process_symbol(self, symbol: str, lot_size: int) -> Optional[Dict]:
        """Process individual symbol with optimized logic"""
        try:
            print(f"🔍 Processing {symbol}...", end=' ')

            # Get underlying LTP
            fyers_symbol = Utils.convert_symbol_to_fyers_format(symbol)
            ltp = self.fyers_api.get_ltp(fyers_symbol)

            if ltp <= 0:
                print(f"❌ No LTP data")
                return None

            print(f"LTP: ₹{ltp:.2f}", end=' ')

            # Calculate ATM strike
            atm_strike = Utils.calculate_atm_strike(ltp, symbol, self.strike_intervals)

            # Create option symbols
            ce_symbol = Utils.create_option_symbol(symbol, atm_strike, 'CE')
            pe_symbol = Utils.create_option_symbol(symbol, atm_strike, 'PE')

            # Get option LTPs
            ce_ltp = self.fyers_api.get_ltp(ce_symbol)
            pe_ltp = self.fyers_api.get_ltp(pe_symbol)

            # Calculate margins
            ce_margin = self.fyers_api.calculate_margin(ce_ltp, lot_size) if ce_ltp > 0 else 0
            pe_margin = self.fyers_api.calculate_margin(pe_ltp, lot_size) if pe_ltp > 0 else 0

            print(f"ATM: {atm_strike} | CE: ₹{ce_ltp:.2f} | PE: ₹{pe_ltp:.2f}")

            return {
                'symbol': symbol,
                'ltp': ltp,
                'atm_strike': atm_strike,
                'ce_symbol': ce_symbol,
                'ce_ltp': ce_ltp,
                'ce_margin': ce_margin,
                'pe_symbol': pe_symbol,
                'pe_ltp': pe_ltp,
                'pe_margin': pe_margin,
                'lot_size': lot_size
            }

        except Exception as e:
            print(f"❌ Error: {e}")
            return None

    def filter_by_margin(self, results: List[Dict]) -> List[Dict]:
        """Filter results by margin requirements"""
        filtered = []

        for result in results:
            ce_within_limit = 0 < result['ce_margin'] <= self.margin_filter
            pe_within_limit = 0 < result['pe_margin'] <= self.margin_filter

            if ce_within_limit or pe_within_limit:
                filtered.append(result)

        return filtered

    def format_output(self, results: List[Dict]) -> str:
        """Format results for display and file output"""
        lines = []
        lines.append("=" * 120)
        lines.append("FYERS LTP AND MARGIN CALCULATOR RESULTS")
        lines.append(f"Margin Filter: Under ₹{self.margin_filter:,.2f} | Margin = LTP × Lot Size")
        lines.append("=" * 120)
        lines.append("")
        lines.append(f"{'Symbol':<15} {'Underlying LTP':>12} {'ATM Contract':>15} {'Contract LTP':>12} {'Margin':>12}")
        lines.append("-" * 120)

        for result in results:
            symbol = result['symbol']
            ltp = result['ltp']
            atm_strike = result['atm_strike']

            # CE Results
            if 0 < result['ce_margin'] <= self.margin_filter:
                ce_contract = f"{atm_strike}CE"
                lines.append(
                    f"{symbol:<15} ₹{ltp:>11.2f} {ce_contract:>15} ₹{result['ce_ltp']:>11.2f} "
                    f"₹{result['ce_margin']:>11.2f}"
                )

            # PE Results  
            if 0 < result['pe_margin'] <= self.margin_filter:
                pe_contract = f"{atm_strike}PE"
                lines.append(
                    f"{symbol:<15} ₹{ltp:>11.2f} {pe_contract:>15} ₹{result['pe_ltp']:>11.2f} "
                    f"₹{result['pe_margin']:>11.2f}"
                )

        lines.append("-" * 120)
        return "\n".join(lines)

    def run(self):
        """Main execution method"""
        print("🚀 Starting Fyers LTP and Margin Calculator (Optimized)")
        print(f"📊 Margin Filter: Under ₹{self.margin_filter:,.2f}")
        print(f"📁 CSV File: {self.csv_file}")
        print(f"📈 Strike Intervals: {len(self.strike_intervals)} symbols loaded")
        print()

        # Read symbols
        symbols = self.read_symbols_from_csv()
        if not symbols:
            return

        # Initialize API
        if not self.fyers_api.initialize_fyers_model():
            print("❌ Failed to initialize Fyers API")
            return

        print(f"🔄 Processing {len(symbols)} symbols...")
        print()

        # Process symbols
        all_results = []
        for i, (symbol, lot_size) in enumerate(symbols, 1):
            result = self.process_symbol(symbol, lot_size)
            if result:
                all_results.append(result)

            # Rate limiting
            if i < len(symbols):
                time.sleep(Config.API_DELAY)

        print()

        # Filter results
        filtered_results = self.filter_by_margin(all_results)

        if not filtered_results:
            print(f"❌ No symbols found with margin under ₹{self.margin_filter:,.2f}")
            return

        # Display and save results
        output = self.format_output(filtered_results)
        print(output)

        try:
            with open(Config.OUTPUT_FILE, 'w', encoding='utf-8') as f:
                f.write(output)
            print(f"\n📝 Results saved to: {Config.OUTPUT_FILE}")
        except Exception as e:
            print(f"⚠️  Could not save results: {e}")

        print(f"✅ Found {len(filtered_results)} symbols within margin limit")

# ============================= MAIN EXECUTION ============================= #

def main():
    """Main function with configuration options"""
    print("=" * 70)
    print("    FYERS LTP AND MARGIN CALCULATOR - OPTIMIZED")
    print("=" * 70)
    print()

    # Configuration can be modified here
    csv_file = Config.CSV_FILE_PATH
    margin_filter = Config.MAX_MARGIN_FILTER

    # Allow command line override of margin filter
    import sys
    if len(sys.argv) > 1:
        try:
            margin_filter = float(sys.argv[1])
            print(f"🔧 Margin filter overridden to: ₹{margin_filter:,.2f}")
        except ValueError:
            print("⚠️  Invalid margin filter argument, using default")

    # Create and run calculator
    calculator = LTPMarginCalculator(csv_file, margin_filter)
    calculator.run()

if __name__ == "__main__":
    main()
