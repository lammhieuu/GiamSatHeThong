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
import sys

sio = socketio.Client(reconnection=True)

def _get_default_api():
    return os.getenv("MONITOR_API_URL", "https://monitor.lcit.vn:4001")

parser = argparse.ArgumentParser(description="Lightweight system monitor client")
parser.add_argument("--api", "-a", help="Backend API URL", default=_get_default_api())
parser.add_argument("--interval", "-i", type=float, help="Send interval in seconds", default=2.0)
parser.add_argument("--hostname", "-H", required=True, help="Tên máy chủ (bắt buộc)")
parser.add_argument("--platform", "-p", required=True, help="Nền tảng (bắt buộc)")
args = parser.parse_args()

API_URL = args.api
SEND_INTERVAL = max(0.5, float(args.interval))
HOSTNAME = args.hostname.strip()
PLATFORM = args.platform.strip()

# Validate inputs
if not HOSTNAME:
    print("Lỗi: Tên máy chủ không được để trống!")
    sys.exit(1)

if not PLATFORM:
    print("Lỗi: Nền tảng không được để trống!")
    sys.exit(1)

def get_all_ip_addresses():
    ip_list = []
    
    try:
        net_if_addrs = psutil.net_if_addrs()
        
        for interface, addrs in net_if_addrs.items():
            ipv4_count = 0
            
            for addr in addrs:
                if addr.family == socket.AF_INET:
                    ip = addr.address
                    
                    if ip and ip != "0.0.0.0":
                        ipv4_count += 1
                        
                        if ipv4_count > 1:
                            display_name = f"{interface} #{ipv4_count}"
                        else:
                            display_name = interface
                        
                        ip_list.append({
                            "interface": display_name,
                            "ip": ip
                        })
        
        if not ip_list:
            ip_list.append({
                "interface": "lo",
                "ip": "127.0.0.1"
            })
            
    except Exception as e:
        print(f"Error getting IP addresses: {e}")
        ip_list.append({
            "interface": "unknown",
            "ip": "127.0.0.1"
        })
    
    return ip_list

def get_listening_ports():
    ports_info = []
    try:
        connections = psutil.net_connections(kind='inet')
        for conn in connections:
            if conn.status == 'LISTEN':
                try:
                    process_name = "-"
                    if conn.pid:
                        try:
                            proc = psutil.Process(conn.pid)
                            process_name = proc.name()
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            process_name = "Unknown"
                    
                    protocol = "TCP" if conn.type == socket.SOCK_STREAM else "UDP"
                    address = conn.laddr.ip if conn.laddr else "-"
                    port = conn.laddr.port if conn.laddr else 0
                    
                    ports_info.append({
                        "protocol": protocol,
                        "address": address,
                        "port": port,
                        "pid": conn.pid or 0,
                        "process": process_name
                    })
                except Exception:
                    continue
        
        ports_info.sort(key=lambda x: x['port'])
        
    except Exception as e:
        print(f"Error getting listening ports: {e}")
    
    return ports_info

def get_static_info():
    cpu_count = psutil.cpu_count(logical=True)
    ip_addresses = get_all_ip_addresses()
    primary_ip = ip_addresses[0]["ip"] if ip_addresses else "127.0.0.1"
    disks, total_used, total_size = get_disk_info()
    
    return {
        "machine_id": hex(uuid.getnode())[2:],
        "os": platform.system() + " " + platform.release(),
        "ip": primary_ip,
        "ip_addresses": ip_addresses,
        "cpu_count": cpu_count,
        "disk_total": total_size,
        "disks": disks,
        "hostname": HOSTNAME,
        "platform": PLATFORM
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
    ip_addresses = get_all_ip_addresses()
    primary_ip = ip_addresses[0]["ip"] if ip_addresses else "127.0.0.1"
    listening_ports = get_listening_ports()
    
    return {
        "cpu_percent": cpu_percent,
        "ram_used": ram.used / (1024**3),
        "ram_total": ram.total / (1024**3),
        "ram_percent": ram.percent,
        "disk_used": total_used,
        "disks": disks,
        "ip": primary_ip,
        "ip_addresses": ip_addresses,
        "listening_ports": listening_ports,
        "last_update": datetime.now().isoformat()
    }

@sio.event
def connect():
    pass

@sio.event
def disconnect():
    pass

@sio.on("stop_monitor")
def stop_monitor(data):
    machine_id = data.get("machine_id")
    if machine_id == static_info["machine_id"]:
        global running
        running = False
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

def check_machine_exists(machine_id):
    try:
        res = requests.get(f"{API_URL}/clients/{machine_id}", timeout=2)
        if res.status_code == 200:
            data = res.json()
            return True, data
        return False, None
    except:
        return False, None

def update_machine_info_to_server(machine_id, hostname, platform_value):
    try:
        payload = {
            "hostname": hostname,
            "platform": platform_value
        }
        res = requests.put(
            f"{API_URL}/update/{machine_id}",
            json=payload,
            timeout=5
        )
        if res.status_code == 200:
            print(f"✓ Đã cập nhật thông tin lên server")
            return True
        else:
            print(f"✗ Lỗi cập nhật thông tin: {res.status_code}")
            return False
    except Exception as e:
        print(f"✗ Lỗi kết nối khi cập nhật thông tin: {e}")
        return False

def main():
    global static_info, running
    static_info = get_static_info()
    running = True

    print(f"Machine ID: {static_info['machine_id']}")
    print(f"Hostname:   {HOSTNAME}")
    print(f"Platform:   {PLATFORM}")

    exists, machine_data = check_machine_exists(static_info["machine_id"])
    
    if exists:
        update_machine_info_to_server(static_info["machine_id"], HOSTNAME, PLATFORM)

    _connect_with_backoff(API_URL)
    
    print("\nStarting system monitor... (Ctrl+C to stop)\n")

    try:
        while running:
            if not sio.connected:
                _connect_with_backoff(API_URL)

            dynamic_data = get_dynamic_info()
            dynamic_data["machine_id"] = static_info["machine_id"]

            exists, _ = check_machine_exists(static_info["machine_id"])

            if exists:
                data_to_send = dynamic_data
            else:
                data_to_send = {**static_info, **dynamic_data}

            try:
                sio.emit("system_update", data_to_send, namespace="/")
            except Exception as e:
                print("Emit failed:", e)

            time.sleep(SEND_INTERVAL)

    except KeyboardInterrupt:
        print("\nStopping monitor...")
        try:
            sio.disconnect()
        except:
            pass

if __name__ == "__main__":
    main()