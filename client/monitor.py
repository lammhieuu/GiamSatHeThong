import argparse
import os
import psutil
import socketio
import platform
import time
import socket
import uuid
from datetime import datetime
import requests

sio = socketio.Client(reconnection=True)

def _get_default_api():
    return os.getenv("MONITOR_API_URL", "http://localhost:4001")

parser = argparse.ArgumentParser(description="Lightweight system monitor client")
parser.add_argument("--api", "-a", help="Backend API URL", default=_get_default_api())
parser.add_argument("--interval", "-i", type=float, help="Send interval in seconds", default=2.0)
args = parser.parse_args()

API_URL = args.api
SEND_INTERVAL = max(0.5, float(args.interval))

def get_static_info():
    hostname = platform.node()
    cpu_count = psutil.cpu_count(logical=True)
    try:
        ip_address = socket.gethostbyname(socket.gethostname())
    except:
        ip_address = "127.0.0.1"
    disks, total_used, total_size = get_disk_info()
    return {
        "machine_id": hex(uuid.getnode())[2:],
        "hostname": hostname,
        "os": platform.system() + " " + platform.release(),
        "ip": ip_address,
        "cpu_count": cpu_count,
        "disk_total": total_size,
        "disks": disks,
        "platform": "-"
    }

def get_disk_info():
    disks, total_used, total_size = [], 0, 0
    for part in psutil.disk_partitions():
        try:
            usage = psutil.disk_usage(part.mountpoint)
            if usage.total >= 1 * 1024**3:
                disks.append({
                    "mount": part.device,
                    "used": usage.used / (1024**3),
                    "total": usage.total / (1024**3),
                    "percent": usage.percent
                })
                total_used += usage.used
                total_size += usage.total
        except PermissionError:
            continue
    return disks, total_used / (1024**3), total_size / (1024**3)

def get_dynamic_info():
    ram = psutil.virtual_memory()
    cpu_percent = psutil.cpu_percent(interval=None)
    disks, total_used, _ = get_disk_info()
    return {
        "cpu_percent": cpu_percent,
        "ram_used": ram.used / (1024**3),
        "ram_total": ram.total / (1024**3),
        "ram_percent": ram.percent,
        "disk_used": total_used,
        "disks": disks,
        "last_update": datetime.now().isoformat()
    }

@sio.event
def connect():
    print("Connected to Server!", API_URL)

@sio.event
def disconnect():
    print("Disconnected from Server!")

@sio.on("stop_monitor")
def stop_monitor(data):
    machine_id = data.get("machine_id")
    if machine_id == static_info["machine_id"]:
        global running
        running = False
        print("Received stop_monitor, exiting...")
        try:
            sio.disconnect()
        except:
            pass

def _connect_with_backoff(url):
    backoff = 1.0
    while True:
        try:
            sio.connect(url, namespaces=["/"], transports=["websocket"])
            return
        except Exception as e:
            print(f"WebSocket connect failed: {e}, retrying in {backoff}s...")
            time.sleep(backoff)
            backoff = min(30, backoff * 1.5)

def main():
    global static_info, running
    static_info = get_static_info()
    running = True

    _connect_with_backoff(API_URL)
    print("Starting system monitor... (Ctrl+C to stop)")

    try:
        while running:
            if not sio.connected:
                _connect_with_backoff(API_URL)

            # Lấy dynamic data
            dynamic_data = get_dynamic_info()
            dynamic_data["machine_id"] = static_info["machine_id"]

            # --- Kiểm tra backend trực tiếp trước mỗi lần gửi
            try:
                res = requests.get(f"{API_URL}/clients/{static_info['machine_id']}", timeout=1)
                exists = res.status_code == 200
            except:
                exists = False

            if exists:
                # Máy đã có trong DB → chỉ gửi realtime fields
                data_to_send = dynamic_data
                print("Machine exists, sending only dynamic data")
            else:
                # Máy chưa có → gửi full data
                data_to_send = {**static_info, **dynamic_data}
                print("Machine not found in backend, sending full data")

            try:
                sio.emit("system_update", data_to_send, namespace="/")
            except Exception as e:
                print("Emit failed:", e)

            time.sleep(SEND_INTERVAL)

    except KeyboardInterrupt:
        print("Stopping monitor...")
        try:
            sio.disconnect()
        except:
            pass

if __name__ == "__main__":
    main()
