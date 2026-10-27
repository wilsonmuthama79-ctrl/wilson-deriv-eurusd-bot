
import json
import websocket

url = "wss://api.derivws.com/trading/v1/options/ws/public"

try:
    ws = websocket.create_connection(url, timeout=15)
    print("CONNECTED TO NEW ENDPOINT")

    ws.send(json.dumps({"ping": 1}))
    print("RESPONSE:", ws.recv())

    ws.close()

except Exception as e:
    print("CONNECTION FAILED:", repr(e))
