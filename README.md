
# FYERS LTP & Margin Calculator

### 📈 Overview
`fyers_ltp_margin_calculator` is a Python tool that automatically fetches **spot prices (LTP)** and determines **At-The-Money (ATM)** option contracts (both CE & PE) for various symbols from the **FYERS API**.  
It then fetches their **option LTPs**, multiplies them by their **lot sizes**, and displays the **required margin** to buy each option contract.

The program helps traders quickly filter opportunities under a specific budget (default: ₹20,000).

---

### 🧮 Example Output

```

========================================================================================================================
FYERS LTP AND MARGIN CALCULATOR RESULTS
Margin Filter: Under ₹20,000.00 | Margin = LTP × Lot Size
=========================================================

## Symbol          Underlying LTP    ATM Contract Contract LTP       Margin

BANKNIFTY       ₹   56407.80         56500PE ₹     519.00 ₹   18165.00
FINNIFTY        ₹   26857.75         26900PE ₹     259.95 ₹   16896.75
360ONE          ₹    1068.90          1080CE ₹      24.40 ₹   12200.00
ABB             ₹    5227.50          5250CE ₹     132.00 ₹   16500.00
...

````

All results are written to a text file (`fyers_margin_results.txt`) for easy reference.

---

### ⚙️ Features

- ✅ Fetches **spot price (LTP)** for each symbol from FYERS API  
- ✅ Automatically calculates **nearest ATM strike**  
- ✅ Fetches **CE/PE LTP** for those ATM contracts  
- ✅ Multiplies LTP × Lot Size = Margin  
- ✅ Filters results under a set margin threshold (default ₹20,000)  
- ✅ Saves results in a **neatly formatted text file**

---

### 💻 Requirements

- Python 3.9 or later  
- FYERS API credentials  
- Dependencies (install using pip):

```bash
pip install fyers-apiv3 pandas requests
````

---

### 🚀 Usage

1. Clone the repository:

   ```bash
   git clone https://github.com/<your-username>/fyers_ltp_margin_calculator.git
   cd fyers_ltp_margin_calculator
   ```

2. Add your **FYERS access token** in the configuration section of the script.

3. Run the script:

   ```bash
   python fyers_ltp_margin_calculator.py
   ```

4. Check your output:

   ```
   fyers_margin_results.txt
   ```

---

### 📁 Output Format

Each line shows:

```
SYMBOL | SPOT LTP | ATM STRIKE | CE/PE LTP | MARGIN
```

The script includes headers, proper alignment, and ₹-formatted values.

---

### 🧠 How It Works

1. Fetches the **spot price** for each symbol using FYERS API.
2. Calculates **ATM strike** by rounding to nearest valid strike interval.
3. Fetches **LTP** of both CE and PE options for that strike.
4. Computes margin = LTP × Lot Size.
5. Filters out symbols exceeding ₹20,000 margin.
6. Writes results in a readable formatted `.txt` file.

---

### ⚡ Example Use Case

You can use this tool to:

* Quickly find **low-margin options** for intraday or small capital strategies.
* Compare **option prices across multiple symbols**.
* Automate margin-based screening for **option buying setups**.

---

### 🧾 License

This project is open source and available under the **MIT License**.

---
