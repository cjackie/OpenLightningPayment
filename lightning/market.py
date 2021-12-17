import requests

def exchange_info():
    sat_per_usd = None
    usd_per_btc = None
    response = requests.get("https://blockchain.info/tobtc?currency=USD&value=1")
    if response.status_code == 200:
        try: 
            btc_per_usd = float(response.text)
            sat_per_usd = int(round(btc_per_usd * COIN))
            usd_per_btc = round(1.0 / btc_per_usd, 2)
        except Exception as e:
            logger.warn("exchange_info failed: {}".format(str(e)))

    return {"sat_per_usd": sat_per_usd, "usd_per_btc": usd_per_btc}