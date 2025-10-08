# monitor.py
import argparse
import os
import psutil
import socketio
import platform
import time
import socket
import uuid
from datetime import datetime

sio = socketio.Client(reconnection=True)

def _get_default_api():
    return os.getenv("MONITOR_API_URL", "https://monitor.lcit.vn:4001")

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
    machine_id = hex(uuid.getnode())[2:]
    disks, total_used, total_size = get_disk_info()
    return {
        "machine_id": machine_id,
        "hostname": hostname,
        "os": platform.system() + " " + platform.release(),
        "ip": ip_address,
        "cpu_count": cpu_count,
        "disk_total": total_size,
        "disks": disks
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

def get_dynamic_info(static_info):
    cpu_percent = psutil.cpu_percent(interval=None)
    ram = psutil.virtual_memory()
    disks, total_used, _ = get_disk_info()
    return {
        "machine_id": static_info["machine_id"],
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
    print("Connected to server:", API_URL)
    try:
        sio.emit("system_update", {**static_info, **get_dynamic_info(static_info)}, namespace="/")
    except Exception as e:
        print("Emit failed on connect:", e)

@sio.event
def disconnect():
    print("Disconnected from server")

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
    global static_info
    static_info = get_static_info()

    _connect_with_backoff(API_URL)
    print("Starting system monitor... (Ctrl+C to stop)")

    try:
        while True:
            if not sio.connected:
                _connect_with_backoff(API_URL)
            dynamic_data = get_dynamic_info(static_info)
            try:
                sio.emit("system_update", dynamic_data, namespace="/")
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
