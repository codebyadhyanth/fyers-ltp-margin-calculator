from flask import Flask, request, render_template_string
from typing import List, Dict
from main_v2 import LTPMarginCalculator,Config

# Assuming you have imported or defined your classes and functions:
# - LTPMarginCalculator
# - Config

app = Flask(__name__)

HTML_TEMPLATE = """
<!doctype html>
<html>
<head>
    <title>Fyers LTP and Margin Calculator</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 40px; }
        table { border-collapse: collapse; width: 80%; }
        th, td { border: 1px solid #ddd; padding: 8px; text-align: right; }
        th { background-color: #f2f2f2; }
        caption { font-weight: bold; font-size: 1.2em; margin-bottom: 10px; }
    </style>
</head>
<body>
    <h1>Fyers LTP and Margin Calculator</h1>
    <form method="get" action="/">
        <label for="margin_filter">Margin Filter (INR): </label>
        <input type="number" id="margin_filter" name="margin_filter" value="{{ margin_filter }}" min="0" step="any" />
        <input type="submit" value="Run Calculator" />
    </form>
    {% if error %}
        <p style="color: red;">{{ error }}</p>
    {% endif %}
    {% if results %}
        <table>
            <caption>Symbols with margin under ₹{{ margin_filter }}</caption>
            <thead>
                <tr>
                    <th>Symbol</th>
                    <th>Underlying LTP (₹)</th>
                    <th>ATM Strike</th>
                    <th>CE Contract LTP (₹)</th>
                    <th>CE Margin (₹)</th>
                    <th>PE Contract LTP (₹)</th>
                    <th>PE Margin (₹)</th>
                    <th>Lot Size</th>
                </tr>
            </thead>
            <tbody>
                {% for r in results %}
                <tr>
                    <td style="text-align:left">{{ r.symbol }}</td>
                    <td>{{ "%.2f"|format(r.ltp) }}</td>
                    <td>{{ r.atm_strike }}</td>
                    <td>{{ "%.2f"|format(r.ce_ltp) }}</td>
                    <td>{{ "%.2f"|format(r.ce_margin) }}</td>
                    <td>{{ "%.2f"|format(r.pe_ltp) }}</td>
                    <td>{{ "%.2f"|format(r.pe_margin) }}</td>
                    <td>{{ r.lot_size }}</td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    {% else %}
        <p>No results to display. Run the calculator.</p>
    {% endif %}
</body>
</html>
"""

@app.route("/")
def index():
    margin_filter = request.args.get("margin_filter", default=Config.MAX_MARGIN_FILTER, type=float)

    try:
        calculator = LTPMarginCalculator(Config.CSV_FILE_PATH, margin_filter)
        calculator.fyers_api.initialize_fyers_model()
        symbols = calculator.read_symbols_from_csv()

        if not symbols:
            return render_template_string(HTML_TEMPLATE, margin_filter=margin_filter, results=[], error="No symbols loaded!")

        all_results = []
        for symbol, lot_size in symbols:
            result = calculator.process_symbol(symbol, lot_size)
            if result:
                all_results.append(result)

        filtered_results = calculator.filter_by_margin(all_results)

        return render_template_string(HTML_TEMPLATE, margin_filter=margin_filter, results=filtered_results, error=None)

    except Exception as e:
        return render_template_string(HTML_TEMPLATE, margin_filter=margin_filter, results=[], error=f"Error: {e}")

if __name__ == "__main__":
    # Run server accessible on local network
    app.run(host="0.0.0.0", port=5000, debug=True)
