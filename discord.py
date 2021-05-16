import requests #dependency

class Discord():
    def __init__(self):
        self._webhook_url = "https://discord.com/api/webhooks/824007368772681739/FeENyJ51FtX020i186CbimFNPvw82BdRfsUTaQGRZKIsUZVWGKSkrh1KblnkCLh3LM2T"
    
    def send_to_discord(self, data):
        print(data)
        result = requests.post(self._webhook_url, json = data)
        try:
            result.raise_for_status()
        except requests.exceptions.HTTPError as err:
            print(err)
        else:
            print("Payload delivered successfully, code {}.".format(result.status_code))
    
    def prepare_data(self, data, tf):
        discord_data = []
        for symbol, indicators in data.items():
            webhook_data = {}
            webhook_data["embeds"] = []
            webhook_data["username"] = symbol + str(tf)
            for indicator, value in indicators.items():
                webhook_data["embeds"].append({
                    "title": indicator,
                    "fields": value
                })
            discord_data.append(webhook_data)
        return discord_data
