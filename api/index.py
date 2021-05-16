from http.server import BaseHTTPRequestHandler
from intraday import IntradayPriceManager
import json
from study import bind_result
from discord import Discord

class handler(BaseHTTPRequestHandler):

    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type','text/plain')
        self.end_headers()
        ipm = IntradayPriceManager()

        ipm.get(type="chart",
            syms=[
                "BINANCE:BTCUSDT", "BINANCE:ETHUSD", "BINANCE:DOTUSD"
            ],
            indicators=["dbs"],
            timeframe=240,
            histbars=300)

        results = ipm.get_technical_results()
        f = open('meta.json')
        response = {}
        data = json.load(f)
        for key, indicators in results.items():
            for indicator, calculation in indicators.items():
                if(data.get(indicator)):
                    binded_result = bind_result(calculation[1:], data.get(indicator))
                    response[key] = {indicator: binded_result}

        discord_client = Discord()
        discord_data = discord_client.prepare_data(response, 240)

        for d_data in discord_data:
            discord_client.send_to_discord(d_data)
        self.wfile.write(json.dumps(response).encode())
        return