""" 
IntradayPriceManager connects to TradingView and stores indicators and price series in an
in memory dictionary self._alerts.
"""

import datetime
import json
import random
import re
import string
import time
import threading
import websocket

class IntradayPriceManager():
    def __init__(self, debug=False):
        self._alerts = {
            "indicators": {},
            "price": {}
        }  
        self._debug = debug
        self._histbars = 300
        self._indicators = []
        self._study_completed = {}
        self._current_calculated_study_number = 0
        self._state = {}
        self._ws = None
        self._syms = [
            "BINANCE:UNIUSD", "BINANCE:ETHUSD", "BINANCE:DOTUSD", "SGX:ES3",
            "SGX:CLR"
        ]
        self._t = None
        self._timeframe = 240  # Default to 4 hours chart
        self._ws_url = "wss://data.tradingview.com/socket.io/websocket"

    def get(self, type: str, **kwargs):
        """ 
        Type is either quote (live) or chart (historical + live) 
        Support kwargs: 
            syms: list of symbols, e.g. [BINANCE:ETHUSD]
            indicators: list of indicators, e.g. [rsi]
            timeframe: int of minutes of chart time frame, e.g. 240 -> 4 hours chart
            histbars: int of number of historical data points, e.g. 300
        """
        #websocket.enableTrace(True)
        ws = websocket.WebSocketApp(
            self._ws_url,
            on_open=lambda ws: self.on_open(ws, type, **kwargs),
            on_close=self.on_close,
            on_message=lambda ws, message: self.on_message(ws, message),
            on_error=self.on_error)
        self._ws = ws;
        ws.run_forever()

    def get_technical_results(self):
        return self._alerts.get("indicators")

    def on_message(self, ws, message):
        pattern = re.compile(r'~m~\d+~m~~h~\d+$')
        if pattern.match(message):
            ws.send(message)
        else:
            msg_body = re.compile(r'~m~\d+~m~')
            messages = msg_body.split(message)
            for msg in messages:
                if msg:
                    parsed_msg = json.loads(msg)
                    params = parsed_msg.get("p")
                    if parsed_msg.get("m") == "timescale_update":
                        # timescale_update -> initial historical data
                        # TODO: handling of these data for plotting on UI
                        continue
                    if parsed_msg.get("m") == "du":
                        # du -> data update
                        sym = self._state.get(params[0]).get("sym")
                        now = datetime.datetime.now().strftime(
                            '%Y-%m-%d %H:%M:%S')
                        for k, v in params[1].items():
                            #print(sym)
                            if v.get("st"):
                                # study
                                indicator = k.split("_")[0]
                                vals = v.get("st")[0].get("v")
                                #print(v.get("st"))
                                current_time = int(time.time())
                                if (int(vals[0]) != current_time - current_time % 14400):
                                    continue
                                if(self._study_completed.get(sym+indicator)):
                                    continue
                                self._study_completed[sym+indicator] = True
                                self._current_calculated_study_number +=1

                                val = vals[1]
                                val_dict = {"dtime": now, indicator: val}
                                #print({sym: val_dict})
                                if not self._alerts["indicators"].get(sym):
                                    self._alerts["indicators"][sym] = {}
                                self._alerts["indicators"][sym][
                                    indicator] = vals
                            elif v.get("s"):
                                # series
                                vals = v.get("s")[0].get("v")
                                val_dict = dict(
                                    zip([
                                        "dtime", "open", "high", "low", "last",
                                        "vol"
                                    ], vals))
                                val_dict["dtime"] = now
                                # print({sym: val_dict})
                                if not self._alerts["price"].get(sym):
                                    self._alerts["price"][sym] = {}
                                self._alerts["price"][sym]["last"] = val_dict[
                                    "last"] 
                        threshold = len(self._inds) + len(self._symbols) if len(self._inds) > 1 else len(self._symbols)
                        if(self._current_calculated_study_number >= threshold):
                            self._ws.close()
                            break

    @staticmethod
    def on_error(ws, error):
        print(error)

    @staticmethod
    def on_close(ws):
        print("### closed ###")

    def on_open(self, ws, type: str, **kwargs):
        def run(*args, **kwargs):
            # ~m~52~m~{"m":"quote_create_session","p":["qs_3bDnffZvz5ur"]}
            # ~m~395~m~{"m":"quote_set_fields","p":["qs_3bDnffZvz5ur","ch","chp","lp"]}
            # ~m~89~m~{"m":"quote_add_symbols","p":["qs_3bDnffZvz5ur","SP:SPX",{"flags":["force_permission"]}]}
            # ~m~315~m~{"m":"quote_fast_symbols","p":["qs_3bDnffZvz5ur","SP:SPX","TVC:NDX","CBOE:VIX","TVC:DXY","SGX:ES3","NASDAQ:AAPL","NASDAQ:MSFT","NASDAQ:TSLA","TVC:USOIL","TVC:GOLD","TVC:SILVER","FX:AUDUSD","FX:EURUSD","FX:GBPUSD","FX:USDJPY","BITSTAMP:BTCUSD","BITSTAMP:ETHUSD","COINBASE:UNIUSD","BINANCE:DOGEUSD","BINANCE:DOTUSD"]}

            syms = kwargs.get("syms") or self._syms
            timeframe = f'{kwargs.get("timeframe") or self._timeframe}'
            indicators = kwargs.get("indicators") or self._indicators
            histbars = kwargs.get("histbars") or self._histbars
            send = self._send
            #my_auth_token = self.get_auth_token()

            self._inds = indicators
            self._symbols = syms


            #send(ws, "set_auth_token", [my_auth_token])

            send(ws, "set_auth_token", ["unauthorized_user_token"])

            # Quote session
            if not args or (args and args[0] == "quote"):
                session = self._gen_session()  # Quote session ID
                send(ws, "quote_create_session", [session])
                send(ws, "quote_set_fields", [session, "lp", "volume"])
                [ws.send(self._add_symbol(session, s)) for s in syms]
                send(ws, "quote_fast_symbols", [session, *syms])
                send(ws, "quote_hibernate_all", [session])

            # Chart session - Prefer to use this over quote sessions since it has a historical series
            else:
                for i, sym in enumerate(syms):
                    # Each ticker warrants a separate chart session ID
                    c_session = self._gen_session(type="chart")
                    self._state[c_session] = {
                        "sym": sym,
                        "indicators": [],
                        "series": [],
                        "timeframe": timeframe
                    }

                    # Users are allowed to select specific tickers
                    send(ws, "chart_create_session", [c_session, ""])
                    send(ws, "switch_timezone", [c_session, "Asia/Singapore"])
                    send(ws, "resolve_symbol", [
                        c_session, f"symbol_{i}",
                        self._add_chart_symbol(sym)
                    ])
                    # s (in resp) -> series
                    self._state[c_session].get("series").append(f"s_{i}")
                    send(ws, "create_series", [
                        c_session, f"s_{i}", f"s_{i}", f"symbol_{i}",
                        timeframe, histbars
                    ])

                    for indicator in indicators:
                        # Users are allowed to select specific indicators
                        # st (in resp) -> study
                        self._state[c_session].get("indicators").append(
                            f"{indicator}_{i}")
                        send(ws, "create_study", [
                            c_session, f"{indicator}_{i}", f"{indicator}_{i}",
                            f"s_{i}", "Script@tv-scripting-101!",
                            self._indicator_mapper(indicator)
                        ])

        self._t = threading.Thread(target=run, args=(type, ), kwargs=kwargs)
        self._t.setDaemon(True)
        self._t.start()

    def _send(self, ws, func, params):
        """ Client sends msg to websockets server """
        ws.send(self._create_msg(func, params))

    def _indicator_mapper(self, indicator: str) -> dict:
        """ Indicator params that are accepted by the tv server """
        return {
            "rsi": {
                "text":
                "1f0fkZ72S0de2geyaUhXXw==_xwY73vljRXeew69Rl27RumLDs6aJ9NLsTYN9Xrht254BTb8uSOgccpLDt/cdRWopwJPNZx40m19yEFwJFswkSi62X4guNJYpXe4A6S9iq2n+OXM6mqWeWzDbjTl0lYmEf1ujbg7i3FvUdV/zCSrqd+iwnvvZSV+O2acpfNLpUlDdB6PZX4Y9y8tlQLWA2PiF8CVJng7DF1LPeecWC4fv+lNg+s5OXU46AjIhc+TFu8DOwiuKjNh7wWz6EZ7gpQS3",
                "pineId": "STD;RSI",
                "pineVersion": "12.0",
                "in_2": {
                    "v": "",
                    "f": True,
                    "t": "resolution"
                },
                "in_0": {
                    "v": 14,
                    "f": True,
                    "t": "integer"
                },
                "in_1": {
                    "v": "close",
                    "f": True,
                    "t": "source"
                }
            },
            "dbs": {
                "text":"tcH8VWAdsdVW+jyR9/6nZw==_5W3O0UDnsvAwYOgsb6qSojVujPishc+22LO5N8X6xG45J/P2Y7EAb4hiqeAx8eerZm3INrvznAq6PmIY5hJ2aM6jOdAWikUpXC0sSK5RZasFdR+viI2SIgJ79jpK1MwERtkHf2GdS0ruyJCY72wstkoJ/JABQX+vYqjgVbM31I8UZ6hZdBRjp2fk8UrzOcGF21abvsn3TbQhbSGIWRcMlNgTxIoI3ziaVZb/zeVFI6LaPXKqWGkc1B7OxOCvIurkIb1uarwwcIYyMhzPyCOaupubStYbJBuiLjclHUcNmsZSy5zq2ccOkXai/f55jRgEbLvieFU0XCGu+nV5pQgpjbGcRAcK9iFe+O+N/N2hSzRz5F6J+1JmIX4U1F8adcbFtiNFhkp7CkuIoZwLGILnZvzbd+kZKfGtA/KNv2Wu7MqSwPHETCljllqTiwjKZ0PFiRO0sTWJY9s/wKI0nQhQAbNyhW94bIDadH8xk6K3xDzdnO9QQgtpjvbSV21FsfQ1LzaQ3sVvmGyANTKH0CactL24CZB7x3nLDOPwN7qolbPercrnN8oU2LNCE23nhR37JEVhSCfCrAIMws9DfHxrUvH8JZ8ueyp7rAsJ92ON3Isv2oDsXo5XF5seMPStHkOdJbaD0nSMzWqr3A6M9OSUJPJ3nzvS3z4Dd/PxXcS6XbTL85eOJDuvvTe6wxrNHWPGBMRWlKV0h3pCTkcdgfcM7fdjWjy4rcIfa8GKpmjoiMSnfUKlKIN+RJfp82hX4o4ewE17iX6eQJwDVqzuvI7bSWpdS35jHlV4qw21R4heQsaUwu/qyoRbs8KxbCo15rEHHoZzOtyEKNlbKYIx/dIqvvHu/vdkthx7Cfpmv7zs21ClxnOZthNp6cm3FXX+g6y2MbLrbO679/aFBXyGBBwbAh2odnd3wPX/RUfuQ7xEij0+9fpcAiYeBzS7BzGC+7zKPPDqyISJkcrASZntvWDhyKd/xllUW3WrxW+srsaKUvT0Yednju/Yils2DTRuRGFjqgFkP4ERQlgUXu6Tqtqwft53z78e4nas5pUE0993zP+A7GFg+xRprq1Wyo8nZelCUm2X9TNqJE+y8JN02pPzYegeBRAgSR1Oiut9SppV6zoRXiPynYv3KPBGyhtnW0Pkkp3A4O8S2Y9WKzMLbunrXvGp0YB8yI40IDfJ5kIJ4rd6IPD5ivPIZuGK6sbf28PvqyWf0w2/wu5RG5QuiQNwZZ8avDSeUkHPpy0pfEibXq41/CRPkFwxaXMfVuG2uNjv5QUX/lPx1IYnLSEuQ1zxToHUCsFZ4q5AUteXnpPu/aj5p/kBBBKtiXLoehpjKhSWxESAXYIoD6nHBrCgCt4O2z49dQ+qA3y2yz2t1MieQjpvM8exB80kRY9GHIDZwpzdWF1FJyvF9b4hfWzVf0CnCvkNLAKL/2aYkQtle4QAj8BBW3E8Ttp9SIqpDez4dblTjYYJrH+C0EuSG0s2+Ybi0ibmgde2yErcjGACNCBNnIgux/TNVULl4x6pukf3HeeeCPgiZgdXPiP8NfjaoOTZcftgMqnU4T//LDIY/oCi0Ro500nGokWdqBl5c9kinGDobiIjdjAdVF4wVzpyRUB5rW0FFprVi1GUIKKb1qkU8Yaf1j63iNASQeqfFAl06uqKdtYE9ORtj1w8lqB3gmj5+l1h7pel9+7wr/uEIzjKR68e1prVgQAP1XMvVEa/KCMjPvBVoSiEm9Pq6arLfH1b3zFzW7TIWUI6aveXw9v/0VrqZn5Bzy6Fm7sWejVOSohDtuPP33fDiPo2bUeGhSn2D0AXiVuKqkA2lH4LY9wsZ8an7RVF2XM/8vKYgNy0rQLcImk0ujDIXILjX03WamjNneR3K3h2HSK3oKbKpDAIj+bg4NUSHZUEKMSqU36w9CMeJUU8EnATrYg7es8+ghycJPfOwbXoBJnSSn7rvOlzi253JC/fvNal6WrO+bFlrFojiJKgBMKEcn7UsdG7d7S73NMQFJzIpRlLA137R000MR5ELe7rJyFLg7htscTKOUvdQLV5bkbWTW6ye/tn37qfga9JtnaBaymopZ2D4Iu6fr8SpQm7r3DyUi8WPBeekzz8uzILqDrjtqKmMud8PWqmEo5LeWsRoCJ4VQoEl6hmo/6EYcP6tO0Mq4vQogg85icyGodqgmUaeY/Sf/9xFEbRT65STc3i+AFRiIxeY/aKkMzchoGf8HS5N/yR67LaxaI/wn9e5rEfOLEOOCkupr2au0PWfwJC5JoFTzCnO/vRSV5cvw7j6dmd2fASoDnAe9+nQsR28l8VFVLZYxKjGs3kQyP2ttUjgysCNu3MGMpzaI9RGmWq6CYHQg/Ohfpe7Sy25NUrEr9/W8SdenMGWr2yDKxFBSd+nEXEcNopeV7ZO0p2wADJ+6M4Ey/8oon3Q/pUmEMWzj4hJUH2ap3p39U55FjJwJPBR77PonOTJhXfrqNqX3nKiG4BZuRvmQn/6GmymCBQQKACy2ufJAmbjIw9qXKTgPeeCaPQXcksuJc9KOOEiF0KUud6eLL7zoBuortuV7R4yCICSDejgLUuMsPZxkQo4s+LgByg8LTyVQ3asymZ4bNMO0PmELIQYzCnC+3BoAPyAMXwwK6cXc1eNee59Z9DTeTdtGpeF/maZVoJYaoCNoZezi1czAswoBr0zLfG7dAffWD5+WncQ92QvSiMc2ruwKjYVSnHT2yczp5UlzhhT3LLWI71UHp+9rcjdpa+tlUN131/FVhDeMpr40MMYivXsS3NGD55nG34ZxkMQ+8EdMc+hrh6lhZc7JXE2XdNzEeBmYXU/lWyVs3CS1fIOcDIj0xA7aeanVVtW3MbcRLWThfZbU4LZyxGx0RCIN6k+2SQgAoJHDQu+U5vhdTnmKdcQc6KfNCIv1oRjc475SHdNa1HJW8u6vOgAfOw+7PxMvaOFun3N3Yp5gMDnPtU9vBYplNLytHzQ975jFWDFYCi/nW6idMP92RAJ0luz39SeZps4lgaDfUqh7+M0Kdi53N7R9XcrBkEaXhR//CYyp5vZv1aYOvdb19mQH7HqJ4q3GOgFjgmWACbRORUU1BX2H0S/fWodc2RIfQIj4KSo4kbO6AODEnTuI9cRnn2ZiHPYohS6ktMQ6n0CIZBpwQzJEqS7zs3lfQzdZtahS32ccCLOmzWivU3EqUtB9AMWLdmCKR6vjgh565gwWKqIyvT0CINsf0f6ydMWPe9LiDR6OBQEmULIOZxJfvF1qSOcjNUO7XWULhIBaMi3Q8hZot/LrwZNk5NrUy+ue0J6BEBPMyAoVRLkOZ3bAe/+6oP2w98fUS/zBnI7uH1AYHA7nM0ydNPG8QK4Ov4jXXpMQvKKmt96/MvBahglbL0TBgz076cZOUqGKJExwtBQpTfcaZyoPVCedk6Vu/M3HYCg/WP/dqhMc1KQlAjyiAq2v9INUlGVr8LMOHZmP2zsfthRATw3MdwKyuyWJMVdbzwW21AABp6oK8QXkumpRko/TAEHOerJO45AJf4p4QJbfzCkFGeAVfLWo9APU/q8ZYG6THyjNQBBNIm1kJLQfxxfSHBumyKwG1h3MtPQXoWRrEzPlkV74jYklBg5VtgWaZJrTm+qJsyeJaO4qzc+V/A3+914eqMxogqzjEGc13NeRn+SIRK3d74xYGC0K7VqIubpZvmPAj+oxumNrZVk2G2B9Pt7jOZzASu4SyJOGBl8/Bz8MJW2aTUrn+wFEfJkzbFW2ocKKrDs5sBTDV8BDyc24qcLBtT5FTJX4NTGATNgZ5wx58kQUCOBhoX0hvKkN1+tVloAUb2VZUbtFza8fOmfeuVW10uAcxc8QKlbA+L64ONYS4kPbDMliEFb+Glwdso167XxnmDkWU9kw/t8Q3Y9l0p3JZdafmFzM2jAr6O+KJMZbv6hqsvYIh4yVvlX3HWBZtL7Rmx1m8kvkxWOsVgv7nX65wCgegxWNNlWCvglyjH47FWkbJnqPvI+J2dzTGSo+DPLhp4gJQRTs6l43tZGmmIPtWVdWK9MVqsWa5wRWCvVTQVVMqULaosoVZechGOgvlL3n602SpuwpmFIF/svio5sgVVblclBhbssljPK/TXCddPqJqqPkD8yGx5rJRIqW0JDicz5jSct39mCbKWhs9/uCVT9TaGZymXnkQbnWofQRDH0MuwUL0W8LXIguM8WbDNL3w5eWn4WQsCNLjf0EIi9jcZ9lCbN/Ez8+kyaN8cYNHzIqYzdfvMn6jYAGbFZE4i94wGrJMid5g5OqbtsGciQZ20XTJvUhA7nhERMKlgJDknVLLk89GfDMjklABDXnSHCxrkMhLr8vCXU+cnKzahkfRJRaaci4NKbQIKlyn82zpS8jnLUj+IsxVIviHnT8oPcx7he6CiqMQq9VXLIl7liT/3awsQjxV7pbCIMn1YqKPej/GmRAWQF4g/3g0GHXUL8Wtj8t4WU9m7DBma7WhN96q38r+t1Q/J/3JeNjYnGIS5w72w9N1JYhtOvy+ssf2u68W8Fss75Mt+35lt5F+fxBLtzU/OHJLyb0HEReSbtUUsGk69/+IAhD+MUwAiEeAhZzzUCpud1pU50exuMjmbOm4iUokJNL3MUqHbsuHJtLR0Yi7fjIJV/fHqt0zmUF7F0YHi1AGQ/WaGQkudCk/aFACE6DCkXKPLnP8zigrMCxuYXzbiKaxaUuenuHJNQVPO0ZBUvkh0ShJtPa2tyQOeUEi1kH+BQJNf4Lg35Uauw7+jH8ORxDYYpuE5i+RyrxYPJ/OptHXsMSxDu7LC8nOqTGTJ7yW1nLlP5c2myqLh/sPkA+C1p23YzCtc39KfZ3EaRDgJFEdJNMN5KfalYk9ze/x9znJ4sE0gO9oXXVZhpw3V8oPeBVN8JAUKi09qaAg6z9Vh0GlS38upzX9aLR3Gmi+9CchmPmKYp5eHg3KqW/KVxi6LRVAQGN3mFu2MRARzF2x4jSWQAoZYcpR5lcuzs3Up9uaCDowKEIa4OmO7ey5SY6LfGUcXT2esOb7M0R5U48wXKkqRaIEH2+jsOU08XOmj3pjXTTvwYs6aa85WPfPFhRUv1iAME/MFacNeWJmRax56wy7PKVedynWvmuhcA2Kpt2FHc33PlHQDH/mIupWINZ2INjjGpjaYv21ndFtqfm2nFXmO84wzbDkFvG+wFtDjsvf6VUIlEDsgfitbd2Dr74BFHH4A+TPH11GcXW5zCRAGy33LjwIXzNWb8wDt5Pv10HAZGKw/ZRGBald2arLF3/Ky7lRR6SCQbzBuTQa10+ewJlWLohe2fhsMUq+S18zc4iGo06KejuEFiJT/y06/zbiUWi/8FttsJzMzvhM7p+LaUSvVhhhq2f43rt5vWwXWGXRqThWxQxonEQreZfK2z1h4YhXwmHxfvvQgZX1C208Twfd4IlKOnAZEUG0uqAoTf+tkYyUm4mqNf60Udf2yMDdhqX94eXS+YAKrI/qMmCpeY408w91UVkjlN9N2GsKppWFnM6eaSQ0cb/aPJocma+ZWz3WPLSAwz4EGXceROVmrarEaic6laXjNVRGG5DCAMXVLn8R2n9djz7lLroe9GKYG99EXLIe4da2yP2Bovxp3KRBe8vX2UAeMX24bov5QjU1vHPxv9gVggDz2sjvz/sC/9f+y8Zdv2SzDmExGWl5NHTCbCFpxcq0AUOZCUTUfJvHm0wJAPIzr2AQG2n8bkzeeEHPvtHprfyMrQJKECxhWCVjQCvERp27N7Atqyv+boh/J+96s9jDQ2i/Amb0bE2ggP02hkTbsWz/LInYbEdEJqXCm1lEjjrntv2eLRhw6XK2WIn5bJrDsBbgI9YtaY/KM4dIhVa1He/YRH1+iGFoAxcjEAcyT9dkh/npcSKIRdtNvdI44lW0lOYtHSs81",
                "pineId":"PUB;AJTP33QbWwPOsq3wAJmZEODIaxIvb0Ai",
                "pineVersion": "2.0",
                "in_0":{
                    "v":False,
                    "f":True,
                    "t":"bool"
                },
                "in_1":{
                    "v":9,
                    "f":True,
                    "t":"integer"
                },
                "in_2":{
                    "v":34,
                    "f":True,
                    "t":"integer"
                },
                "in_3":{
                    "v":"close",
                    "f":True,
                    "t":"source"
                },
                "in_4":{
                    "v":False,
                    "f":True,
                    "t":"bool"
                },
                "in_5":{
                    "v":True,
                    "f":True,
                    "t":"bool"
                },
                "in_6":{
                    "v":False,
                    "f":True,
                    "t":"bool"
                },
                "in_7":{
                    "v":False,
                    "f":True,
                    "t":"bool"
                },
                "in_8":{
                    "v":5,
                    "f":True,
                    "t":"integer"
                },
                "in_9":{
                    "v":13,
                    "f":True,
                    "t":"integer"
                },
                "in_10":{
                    "v":"close",
                    "f":True,
                    "t":"source"
                },
                "in_11":{
                    "v":True,
                    "f":True,
                    "t":"bool"
                },
                "in_12":{
                    "v":False,
                    "f":True,
                    "t":"bool"
                },
                "in_13":{
                    "v":1,
                    "f":True,
                    "t":"integer"
                },
                "in_14":{
                    "v":False,
                    "f":True,
                    "t":"bool"
                },
                "in_15":{
                    "v":False,
                    "f":True,
                    "t":"bool"
                },
                "in_16":{
                    "v":False,
                    "f":True,
                    "t":"bool"
                },
                "in_17":{
                    "v":False,
                    "f":True,
                    "t":"bool"
                },
                "in_18":{
                    "v":False,
                    "f":True,
                    "t":"bool"
                },
                "in_19":{
                    "v":"Mavi",
                    "f":True,
                    "t":"text"
                }
            },
            "srd": {"text":"hCzVccHyaZeAeTnWl9dhOQ==_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","pineId":"PUB;q6VybnoxDrkq5DzdnJSCz0M4GHm1DHE5","pineVersion":"4.0","in_0":{"v":300,"f":True,"t":"integer"},"in_1":{"v":6,"f":True,"t":"integer"}
            }

        }.get(indicator.lower())

    def _create_msg(self, func, params):
        """ _create_msg("set_auth_token", "unauthorized_user_token") """
        msg = self._prepend_header(json.dumps({"m": func, "p": params}))

        if self._debug:
            print("DEBUG:", msg)

        return msg

    def _gen_session(self, type="chart"):
        # ~m~52~m~{"m":"quote_create_session","p":["qs_3bDnffZvz5ur"]}
        session = ""
        if type == "quote":
            session = "qs_"
        elif type == "chart":
            session = "cs_"
        else:
            raise Exception("Invalid session type")
        return session + "".join(random.choices(string.ascii_letters, k=12))

    def _add_symbol(self, quote_session: str, sym: str):
        """ Quote symbol: _add_symbol("3bDnffZvz5ur", "BINANCE:UNIUSD") """
        return self._create_msg("quote_add_symbols", [quote_session, sym])

    def _add_chart_symbol(self, sym: str):
        """ Chart symbol - Only required for the first symbol """
        return "=" + json.dumps({"symbol": sym})

    def _prepend_header(self, msg):
        return f'~m~{len(msg)}~m~{msg}'


""" if __name__ == "__main__":

    ipm = IntradayPriceManager()

    ipm.get(type="chart",
            syms=[
                "BINANCE:ETHUSDT"
            ],
            indicators=["dbs"],
            timeframe=240,
            histbars=300) """
