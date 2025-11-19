#monitor.py
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
import tkinter as tk
from tkinter import messagebox, simpledialog

sio = socketio.Client(reconnection=True)

# --- Cấu hình backend API ---
def _get_default_api():
    return os.getenv("MONITOR_API_URL", "https://monitor.lcit.vn:4001")

parser = argparse.ArgumentParser(description="Lightweight system monitor client")
parser.add_argument("--api", "-a", help="Backend API URL", default=_get_default_api())
parser.add_argument("--interval", "-i", type=float, help="Send interval in seconds", default=2.0)
args = parser.parse_args()

API_URL = args.api
SEND_INTERVAL = max(0.5, float(args.interval))

# --- Lấy tất cả IP addresses ---
def get_all_ip_addresses():
    ip_list = []
    interface_count = {}  # Đếm số lần xuất hiện của mỗi interface
    
    try:
        for interface, addrs in psutil.net_if_addrs().items():
            for addr in addrs:
                if addr.family == socket.AF_INET:
                    ip = addr.address
                    if ip != "127.0.0.1":
                        # Đếm số lần interface xuất hiện
                        interface_count[interface] = interface_count.get(interface, 0) + 1
                        
                        # Nếu interface xuất hiện lần thứ 2 trở đi, thêm suffix
                        if interface_count[interface] > 1:
                            display_name = f"{interface} #{interface_count[interface]}"
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

# --- Lấy thông tin các cổng đang lắng nghe ---
def get_listening_ports():
    ports_info = []
    try:
        connections = psutil.net_connections(kind='inet')
        for conn in connections:
            # Chỉ lấy các cổng đang LISTEN
            if conn.status == 'LISTEN':
                try:
                    # Lấy thông tin process
                    process_name = "-"
                    if conn.pid:
                        try:
                            proc = psutil.Process(conn.pid)
                            process_name = proc.name()
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            process_name = "Unknown"
                    
                    # Xác định protocol
                    protocol = "TCP" if conn.type == socket.SOCK_STREAM else "UDP"
                    
                    # Lấy địa chỉ và port
                    address = conn.laddr.ip if conn.laddr else "-"
                    port = conn.laddr.port if conn.laddr else 0
                    
                    ports_info.append({
                        "protocol": protocol,
                        "address": address,
                        "port": port,
                        "pid": conn.pid or 0,
                        "process": process_name
                    })
                except Exception as e:
                    continue
        
        # Sắp xếp theo port
        ports_info.sort(key=lambda x: x['port'])
        
    except Exception as e:
        print(f"Error getting listening ports: {e}")
    
    return ports_info

# --- Lấy thông tin tĩnh ---
def get_static_info():
    hostname = platform.node()
    cpu_count = psutil.cpu_count(logical=True)
    ip_addresses = get_all_ip_addresses()
    primary_ip = ip_addresses[0]["ip"] if ip_addresses else "127.0.0.1"
    disks, total_used, total_size = get_disk_info()
    
    return {
        "machine_id": hex(uuid.getnode())[2:],
        "hostname": hostname,
        "os": platform.system() + " " + platform.release(),
        "ip": primary_ip,
        "ip_addresses": ip_addresses,
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
    ip_addresses = get_all_ip_addresses()
    primary_ip = ip_addresses[0]["ip"] if ip_addresses else "127.0.0.1"
    
    # Lấy thông tin các cổng đang lắng nghe
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
    """Kiểm tra xem máy đã tồn tại trong database chưa"""
    try:
        res = requests.get(f"{API_URL}/clients/{machine_id}", timeout=2)
        if res.status_code == 200:
            data = res.json()
            return True, data
        return False, None
    except:
        return False, None

def show_platform_input_dialog(hostname):
    """Hiển thị popup đẹp để nhập thông tin nền tảng"""
    result = [None]  # Dùng list để lưu kết quả
    cancelled = [False]  # Flag để biết người dùng có ấn Hủy không
    
    def on_selection_change(event):
        selected = combo.get()
        if selected == "Khác":
            entry.config(state='normal')
            entry.focus()
        else:
            entry.delete(0, tk.END)
            entry.config(state='disabled')
    
    def on_save():
        selected = combo.get()
        if selected == "Khác":
            value = entry.get().strip()
            if value:
                result[0] = value
                dialog.destroy()
            else:
                error_label.config(text="⚠ Vui lòng nhập nền tảng!")
        elif selected:
            result[0] = selected
            dialog.destroy()
        else:
            error_label.config(text="⚠ Vui lòng chọn nền tảng!")
    
    def on_cancel():
        """Hủy và dừng chương trình"""
        cancelled[0] = True
        result[0] = None
        dialog.destroy()
    
    def on_close():
        """Xử lý khi đóng cửa sổ bằng nút X"""
        on_cancel()
    
    # Tạo cửa sổ dialog
    dialog = tk.Tk()
    dialog.title("Cấu hình hệ thống")
    dialog.geometry("450x380")
    dialog.resizable(False, False)
    dialog.configure(bg="#f8f9fa")
    dialog.protocol("WM_DELETE_WINDOW", on_close)
    
    # Tăng DPI awareness để hiển thị sắc nét hơn
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except:
        pass
    
    # Đưa cửa sổ lên phía trước và giữa màn hình
    dialog.attributes('-topmost', True)
    dialog.lift()
    dialog.focus_force()
    
    # Căn giữa màn hình
    dialog.update_idletasks()
    x = (dialog.winfo_screenwidth() // 2) - (450 // 2)
    y = (dialog.winfo_screenheight() // 2) - (380 // 2)
    dialog.geometry(f"450x380+{x}+{y}")
    
    # Frame chính với padding
    main_frame = tk.Frame(dialog, bg="#f8f9fa", padx=35, pady=30)
    main_frame.pack(fill=tk.BOTH, expand=True)
    
    # Tiêu đề
    title_label = tk.Label(
        main_frame,
        text="📋 Nhập Thông Tin Nền Tảng",
        font=("Segoe UI", 16, "bold"),
        bg="#f8f9fa",
        fg="#1a1a1a"
    )
    title_label.pack(pady=(0, 5))
    
    # Thông tin máy
    info_label = tk.Label(
        main_frame,
        text=f"Máy: {hostname}",
        font=("Segoe UI", 10),
        bg="#f8f9fa",
        fg="#6c757d"
    )
    info_label.pack(pady=(0, 20))
    
    # Label cho selectbox
    label = tk.Label(
        main_frame,
        text="Chọn nền tảng:",
        font=("Segoe UI", 10, "bold"),
        bg="#f8f9fa",
        fg="#1a1a1a"
    )
    label.pack(anchor=tk.W, pady=(0, 8))
    
    # Import ttk cho Combobox
    from tkinter import ttk
    
    # Tạo style cho combobox
    style = ttk.Style()
    style.theme_use('clam')
    style.configure(
        'Custom.TCombobox',
        fieldbackground='white',
        background='white',
        bordercolor='#ced4da',
        arrowcolor='#495057',
        relief='solid',
        borderwidth=1
    )
    
    # Selectbox (Combobox)
    platforms = ["Viettel Cloud", "VNTP Cloud", "TTCNTT LC", "Khác"]
    combo = ttk.Combobox(
        main_frame,
        values=platforms,
        font=("Segoe UI", 10),
        state='readonly',
        style='Custom.TCombobox',
        height=10
    )
    combo.pack(fill=tk.X, ipady=6)
    combo.set("Viettel Cloud")  # Giá trị mặc định
    combo.bind('<<ComboboxSelected>>', on_selection_change)
    
    # Entry cho trường hợp chọn "Khác" (ban đầu ẩn/disabled)
    entry = tk.Entry(
        main_frame,
        font=("Segoe UI", 10),
        relief=tk.SOLID,
        borderwidth=1,
        state='disabled',
        disabledbackground='#e9ecef',
        disabledforeground='#6c757d',
        highlightthickness=0,
        bd=1
    )
    entry.pack(fill=tk.X, ipady=6, pady=(10, 0))
    
    # Label lỗi (ẩn mặc định)
    error_label = tk.Label(
        main_frame,
        text="",
        font=("Segoe UI", 9),
        bg="#f8f9fa",
        fg="#dc3545"
    )
    error_label.pack(pady=(8, 10))
    
    # Frame chứa các nút
    button_frame = tk.Frame(main_frame, bg="#f8f9fa")
    button_frame.pack(pady=(15, 0))
    
    # Nút Lưu
    save_btn = tk.Button(
        button_frame,
        text="💾 Lưu",
        font=("Segoe UI", 10, "bold"),
        bg="#28a745",
        fg="white",
        activebackground="#218838",
        activeforeground="white",
        relief=tk.FLAT,
        cursor="hand2",
        padx=30,
        pady=10,
        command=on_save,
        borderwidth=0,
        highlightthickness=0
    )
    save_btn.pack(side=tk.LEFT, padx=5)
    
    # Nút Hủy
    cancel_btn = tk.Button(
        button_frame,
        text="✖ Hủy (Thoát)",
        font=("Segoe UI", 10, "bold"),
        bg="#dc3545",
        fg="white",
        activebackground="#c82333",
        activeforeground="white",
        relief=tk.FLAT,
        cursor="hand2",
        padx=25,
        pady=10,
        command=on_cancel,
        borderwidth=0,
        highlightthickness=0
    )
    cancel_btn.pack(side=tk.LEFT, padx=5)
    
    # Bind Enter key
    dialog.bind('<Return>', lambda e: on_save())
    dialog.bind('<Escape>', lambda e: on_cancel())
    
    # Chạy dialog
    dialog.mainloop()
    
    # Kiểm tra xem người dùng có ấn Hủy không
    if cancelled[0]:
        print("\n❌ Người dùng đã hủy. Dừng chương trình...")
        import sys
        sys.exit(0)
    
    return result[0] if result[0] else "-"

def update_platform_to_server(machine_id, platform_value):
    """Cập nhật thông tin nền tảng lên server"""
    try:
        payload = {"platform": platform_value}
        res = requests.put(
            f"{API_URL}/update/{machine_id}",
            json=payload,
            timeout=5
        )
        if res.status_code == 200:
            print(f"✓ Đã cập nhật nền tảng: {platform_value}")
            return True
        else:
            print(f"✗ Lỗi cập nhật nền tảng: {res.status_code}")
            return False
    except Exception as e:
        print(f"✗ Lỗi kết nối khi cập nhật nền tảng: {e}")
        return False

def main():
    global static_info, running
    static_info = get_static_info()
    running = True

    print(f"Machine ID: {static_info['machine_id']}")
    print(f"Hostname: {static_info['hostname']}")
    
    # Kiểm tra xem máy đã tồn tại và có nền tảng chưa
    exists, machine_data = check_machine_exists(static_info["machine_id"])
    
    need_platform_input = False
    
    if not exists:
        # Máy mới → cần nhập nền tảng
        print("⚠ Máy mới, yêu cầu nhập thông tin nền tảng...")
        need_platform_input = True
    elif machine_data:
        current_platform = machine_data.get("platform", "-")
        print(f"Nền tảng hiện tại: {current_platform}")
        
        # Nếu nền tảng là "-" hoặc rỗng → cần nhập nền tảng
        if current_platform == "-" or not current_platform:
            print("⚠ Máy chưa có thông tin nền tảng, yêu cầu nhập...")
            need_platform_input = True
        else:
            static_info["platform"] = current_platform
    
    # Hiển thị pop-up nếu cần
    if need_platform_input:
        platform_value = show_platform_input_dialog(static_info['hostname'])
        static_info["platform"] = platform_value
        
        # Cập nhật lên server nếu máy đã tồn tại
        if exists:
            update_platform_to_server(static_info["machine_id"], platform_value)

    _connect_with_backoff(API_URL)
    print("Starting system monitor... (Ctrl+C to stop)")

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
        print("Stopping monitor...")
        try:
            sio.disconnect()
        except:
            pass

if __name__ == "__main__":
    main()