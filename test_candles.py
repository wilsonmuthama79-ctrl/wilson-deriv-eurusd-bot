
import json
import websocket

url = "wss://api.derivws.com/trading/v1/options/ws/public"

try:
    ws = websocket.create_connection(url, timeout=15)
    print("Connected successfully.")

    request = {
        "ticks_history": "frxEURUSD",
        "count": 10,
        "end": "latest",
        "style": "candles",
        "granularity": 300
    }

    ws.send(json.dumps(request))

    response = json.loads(ws.recv())
    print(json.dumps(response, indent=2))

    ws.close()

except Exception as e:
    print("TEST FAILED:", repr(e))
