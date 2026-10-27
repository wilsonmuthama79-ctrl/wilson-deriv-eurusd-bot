
import websocket

url = "wss://ws.derivws.com/websockets/v3?app_id=1089"

try:
    ws = websocket.create_connection(url, timeout=15)
    print("CONNECTED TO DERIV")
    ws.send('{"ping":1}')
    print("SERVER RESPONSE:", ws.recv())
    ws.close()
except Exception as e:
    print("CONNECTION FAILED:", repr(e))
