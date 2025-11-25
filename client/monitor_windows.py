import argparse
import os
import psutil
import socketio
import platform
import time
import socket
import uuid
import requests
import tkinter as tk
from tkinter import ttk
from datetime import datetime
import sys
import subprocess
import ctypes

# ==================== SINGLE INSTANCE ====================
kernel32 = ctypes.windll.kernel32
mutex = kernel32.CreateMutexW(None, False, "Global\\MonitorWindowsMutex")
if kernel32.GetLastError() == 183:
    current_pid = os.getpid()
    for proc in psutil.process_iter(['pid', 'name', 'exe']):
        try:
            if proc.info['pid'] != current_pid and proc.info['name'] and proc.info['exe']:
                name, exe = proc.info['name'].lower(), proc.info['exe'].lower()
                if 'monitor_windows' in name or 'monitor_windows.exe' in exe:
                    proc.kill()
        except: pass
    time.sleep(1)

# ==================== CONFIG ====================
parser = argparse.ArgumentParser(description="Lightweight system monitor client")
parser.add_argument("--api", "-a", default=os.getenv("MONITOR_API_URL", "https://monitor.lcit.vn:4001"))
parser.add_argument("--interval", "-i", type=float, default=.0)
args = parser.parse_args()

API_URL = args.api
SEND_INTERVAL = max(0.5, args.interval)
sio = socketio.Client(reconnection=True)

# ==================== AUTO START ====================
STARTUP_FOLDER = os.path.join(os.getenv('APPDATA'), r'Microsoft\Windows\Start Menu\Programs\Startup')
SHORTCUT_PATH = os.path.join(STARTUP_FOLDER, "MonitorWindows.lnk")
DISABLED_PATH = SHORTCUT_PATH + ".disabled"

def is_autostart_enabled():
    return not os.path.exists(DISABLED_PATH) and os.path.exists(SHORTCUT_PATH)

def create_shortcut_powershell(target, shortcut):
    ps_script = f"""
$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut('{shortcut.replace("'", "''")}')
$Shortcut.TargetPath = '{target.replace("'", "''")}'
$Shortcut.WorkingDirectory = '{os.path.dirname(target).replace("'", "''")}'
$Shortcut.Description = 'Monitor Windows System'
$Shortcut.Save()
"""
    try:
        result = subprocess.run(['powershell', '-Command', ps_script], 
                              capture_output=True, 
                              creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        return result.returncode == 0
    except:
        return False

def enable_autostart():
    try:
        os.makedirs(STARTUP_FOLDER, exist_ok=True)
        if os.path.exists(DISABLED_PATH):
            os.rename(DISABLED_PATH, SHORTCUT_PATH)
            return True
        if os.path.exists(SHORTCUT_PATH):
            return True
        return create_shortcut_powershell(sys.executable, SHORTCUT_PATH)
    except:
        return False

def disable_autostart():
    try:
        if os.path.exists(SHORTCUT_PATH):
            if os.path.exists(DISABLED_PATH):
                os.remove(DISABLED_PATH)
            os.rename(SHORTCUT_PATH, DISABLED_PATH)
        return True
    except:
        return False

def remove_autostart():
    try:
        for path in [SHORTCUT_PATH, DISABLED_PATH]:
            if os.path.exists(path):
                os.remove(path)
        return True
    except:
        return False

# ==================== SYSTEM INFO ====================
def get_all_ip_addresses():
    ip_list, interface_count = [], {}
    try:
        for interface, addrs in psutil.net_if_addrs().items():
            for addr in addrs:
                if addr.family == socket.AF_INET and addr.address != "127.0.0.1":
                    interface_count[interface] = interface_count.get(interface, 0) + 1
                    display = f"{interface} #{interface_count[interface]}" if interface_count[interface] > 1 else interface
                    ip_list.append({"interface": display, "ip": addr.address})
        return ip_list or [{"interface": "lo", "ip": "127.0.0.1"}]
    except:
        return [{"interface": "unknown", "ip": "127.0.0.1"}]

def get_listening_ports():
    ports = []
    try:
        for conn in psutil.net_connections(kind='inet'):
            if conn.status == 'LISTEN' and conn.laddr:
                try:
                    proc_name = "-"
                    if conn.pid:
                        try:
                            proc_name = psutil.Process(conn.pid).name()
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            proc_name = "Unknown"
                    ports.append({
                        "protocol": "TCP" if conn.type == socket.SOCK_STREAM else "UDP",
                        "address": conn.laddr.ip,
                        "port": conn.laddr.port,
                        "pid": conn.pid or 0,
                        "process": proc_name
                    })
                except:
                    continue
        ports.sort(key=lambda x: x['port'])
    except:
        pass
    return ports

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

def get_static_info():
    ip_addresses = get_all_ip_addresses()
    disks, _, total_size = get_disk_info()
    return {
        "machine_id": hex(uuid.getnode())[2:],
        "os": f"{platform.system()} {platform.release()}",
        "ip": ip_addresses[0]["ip"],
        "ip_addresses": ip_addresses,
        "cpu_count": psutil.cpu_count(logical=True),
        "disk_total": total_size,
        "disks": disks,
        "platform": "-",
        "hostname": "-"
    }

def get_dynamic_info():
    ram = psutil.virtual_memory()
    disks, total_used, _ = get_disk_info()
    ip_addresses = get_all_ip_addresses()
    return {
        "cpu_percent": psutil.cpu_percent(interval=None),
        "ram_used": ram.used / (1024**3),
        "ram_total": ram.total / (1024**3),
        "ram_percent": ram.percent,
        "disk_used": total_used,
        "disks": disks,
        "ip": ip_addresses[0]["ip"],
        "ip_addresses": ip_addresses,
        "listening_ports": get_listening_ports(),
        "last_update": datetime.now().isoformat()
    }

# ==================== SOCKET EVENTS ====================
@sio.event
def connect():
    pass

@sio.event
def disconnect():
    pass

@sio.on("stop_monitor")
def stop_monitor(data):
    if data.get("machine_id") == static_info["machine_id"]:
        remove_autostart()
        global running
        running = False
        try:
            sio.disconnect()
        except:
            pass

# ==================== SERVER COMMUNICATION ====================
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
        return (True, res.json()) if res.status_code == 200 else (False, None)
    except:
        return False, None

def update_info_to_server(machine_id, platform_value, hostname_value):
    try:
        res = requests.put(f"{API_URL}/update/{machine_id}",
                          json={"platform": platform_value, "hostname": hostname_value},
                          timeout=5)
        if res.status_code == 200:
            print(f"Đã cập nhật - Nền tảng: {platform_value} | Hostname: {hostname_value}")
            return True
        print(f"Lỗi cập nhật: {res.status_code}")
    except Exception as e:
        print(f"Lỗi kết nối khi cập nhật: {e}")
    return False

# ==================== UI DIALOG ====================
def show_input_dialog(current_hostname_system):
    result = {"platform": None, "hostname": None}
    cancelled = [False]
    
    def on_selection_change(event):
        state = 'normal' if platform_combo.get() == "Khác" else 'disabled'
        platform_entry.config(state=state)
        if state == 'normal':
            platform_entry.focus()
        else:
            platform_entry.delete(0, tk.END)
    
    def on_save():
        selected = platform_combo.get()
        platform_value = platform_entry.get().strip() if selected == "Khác" else selected
        hostname_value = hostname_entry.get().strip()
        
        if not platform_value:
            error_label.config(text="Vui lòng chọn/nhập nền tảng!")
            return
        if not hostname_value:
            error_label.config(text="Vui lòng nhập tên máy chủ!")
            return
        
        result["platform"] = platform_value
        result["hostname"] = hostname_value
        dialog.destroy()
    
    def on_cancel():
        cancelled[0] = True
        dialog.destroy()
    
    dialog = tk.Tk()
    dialog.title("Cấu hình hệ thống")
    dialog.geometry("450x450")
    dialog.resizable(False, False)
    dialog.configure(bg="#f8f9fa")
    dialog.protocol("WM_DELETE_WINDOW", on_cancel)
    
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except:
        pass
    
    dialog.attributes('-topmost', True)
    dialog.lift()
    dialog.focus_force()
    
    x = (dialog.winfo_screenwidth() - 450) // 2
    y = (dialog.winfo_screenheight() - 450) // 2
    dialog.geometry(f"450x450+{x}+{y}")
    
    main_frame = tk.Frame(dialog, bg="#f8f9fa", padx=35, pady=30)
    main_frame.pack(fill=tk.BOTH, expand=True)
    
    tk.Label(main_frame, text="📋 Nhập Thông Tin Hệ Thống",
             font=("Segoe UI", 16, "bold"), bg="#f8f9fa", fg="#1a1a1a").pack(pady=(0, 5))
    
    tk.Label(main_frame, text="Chọn nền tảng:",
             font=("Segoe UI", 10, "bold"), bg="#f8f9fa", fg="#1a1a1a").pack(anchor=tk.W, pady=(0, 8))
    
    style = ttk.Style()
    style.theme_use('clam')
    style.configure('Custom.TCombobox', fieldbackground='white', background='white',
                   bordercolor='#ced4da', arrowcolor='#495057', relief='solid', borderwidth=1)
    
    platform_combo = ttk.Combobox(main_frame, values=["Viettel Cloud", "VNTP Cloud", "TTCNTT LC", "Khác"],
                                 font=("Segoe UI", 10), state='readonly', style='Custom.TCombobox', height=10)
    platform_combo.pack(fill=tk.X, ipady=6)
    platform_combo.set("Viettel Cloud")
    platform_combo.bind('<<ComboboxSelected>>', on_selection_change)
    
    platform_entry = tk.Entry(main_frame, font=("Segoe UI", 10), relief=tk.SOLID, borderwidth=1,
                             state='disabled', disabledbackground='#e9ecef', disabledforeground='#6c757d',
                             highlightthickness=0, bd=1)
    platform_entry.pack(fill=tk.X, ipady=6, pady=(10, 0))
    
    tk.Label(main_frame, text="Nhập tên máy chủ:",
             font=("Segoe UI", 10, "bold"), bg="#f8f9fa", fg="#1a1a1a").pack(anchor=tk.W, pady=(20, 8))
    
    hostname_entry = tk.Entry(main_frame, font=("Segoe UI", 10), relief=tk.SOLID,
                             borderwidth=1, highlightthickness=0, bd=1)
    hostname_entry.pack(fill=tk.X, ipady=6)
    hostname_entry.insert(0, current_hostname_system)
    
    error_label = tk.Label(main_frame, text="", font=("Segoe UI", 9),
                          bg="#f8f9fa", fg="#dc3545")
    error_label.pack(pady=(8, 10))
    
    button_frame = tk.Frame(main_frame, bg="#f8f9fa")
    button_frame.pack(pady=(15, 0))
    
    btn_style = {"font": ("Segoe UI", 10, "bold"), "relief": tk.FLAT, "cursor": "hand2",
                "padx": 30, "pady": 10, "borderwidth": 0, "highlightthickness": 0}
    
    tk.Button(button_frame, text="💾 Lưu", bg="#28a745", fg="white",
             activebackground="#218838", activeforeground="white",
             command=on_save, **btn_style).pack(side=tk.LEFT, padx=5)
    
    tk.Button(button_frame, text="✖ Hủy", bg="#dc3545", fg="white",
             activebackground="#c82333", activeforeground="white",
             command=on_cancel, **{**btn_style, "padx": 25}).pack(side=tk.LEFT, padx=5)
    
    dialog.bind('<Return>', lambda e: on_save())
    dialog.bind('<Escape>', lambda e: on_cancel())
    dialog.mainloop()
    
    if cancelled[0]:
        print("\nNgười dùng đã hủy. Dừng chương trình...")
        sys.exit(0)
    
    return result

# ==================== MAIN ====================
def main():
    global static_info, running
    static_info = get_static_info()
    running = True

    print(f"Machine ID: {static_info['machine_id']}")
    
    current_hostname = platform.node()
    exists, machine_data = check_machine_exists(static_info["machine_id"])
    need_input = False
    
    if not exists:
        print("Máy mới, yêu cầu nhập thông tin...")
        need_input = True
    elif machine_data:
        plat = machine_data.get("platform", "-")
        host = machine_data.get("hostname", "-")
        print(f"Nền tảng hiện tại: {plat}\nHostname hiện tại: {host}")
        
        if not plat or plat == "-" or not host or host == "-":
            print("Máy chưa có đầy đủ thông tin, yêu cầu nhập...")
            need_input = True
        else:
            static_info["platform"] = plat
            static_info["hostname"] = host
    
    if need_input:
        user_input = show_input_dialog(current_hostname)
        static_info["platform"] = user_input["platform"]
        static_info["hostname"] = user_input["hostname"]
        if exists:
            update_info_to_server(static_info["machine_id"], 
                                user_input["platform"], user_input["hostname"])
    
    enable_autostart()
    print(f"Hostname: {static_info['hostname']}\nPlatform: {static_info['platform']}")

    _connect_with_backoff(API_URL)
    print("Starting system monitor... (Ctrl+C to stop)")

    try:
        while running:
            if not sio.connected:
                _connect_with_backoff(API_URL)

            dynamic_data = get_dynamic_info()
            dynamic_data["machine_id"] = static_info["machine_id"]
            exists, _ = check_machine_exists(static_info["machine_id"])
            data_to_send = dynamic_data if exists else {**static_info, **dynamic_data}

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