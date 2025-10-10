# main.py
import asyncio
import socketio
import psutil
import platform
import socket
import uuid
from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from pymongo import MongoClient
from datetime import datetime

# Danh sách origins được phép kết nối
origins = [
    "https://monitor.lcit.vn:8000",
    "http://localhost:4001",
    "http://127.0.0.1:3000",
    "http://192.168.10.43:4001",
    "http://192.168.251.32:3002",
    "http://localhost:3000"
]

# Cấu hình Socket.IO
sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins=origins)
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)
socket_app = socketio.ASGIApp(sio, app)

# Kết nối MongoDB
connection_string = "mongodb+srv://lammhieuu_db_user:scm123456@server.2bf1k73.mongodb.net/?retryWrites=true&w=majority&appName=Server"
mongo_client = MongoClient(connection_string)
app_db = mongo_client["app_database"]
collection = app_db["MAY_CHU"]

# Lưu dữ liệu client vào MongoDB
def save_client_to_mongo_sync(client_data):
    machine_id = client_data.get("machine_id")
    if not machine_id:
        return
    return collection.update_one({"machine_id": machine_id}, {"$set": client_data}, upsert=True)

# Dữ liệu clients đang kết nối
clients_data = {}

# Socket.IO events
@sio.event
async def connect(sid, environ):
    await sio.emit("update", clients_data)

@sio.event
async def disconnect(sid):
    await sio.emit("update", clients_data)

@sio.event
async def system_update(sid, data):
    machine_id = data.get("machine_id")
    if not machine_id:
        return
    # Merge dữ liệu mới vào data cũ
    old_data = clients_data.get(machine_id, {})
    merged = {**old_data, **data}
    if "platform" not in merged:
        merged["platform"] = "-"
    merged["last_update"] = datetime.now().isoformat()
    clients_data[machine_id] = merged
    await sio.emit("update", clients_data)
    save_client_to_mongo_sync(merged)

# FastAPI endpoints
@app.get("/clients")
async def get_clients():
    return clients_data

@app.get("/clients/{client_id}")
async def get_client(client_id: str):
    if client_id not in clients_data:
        raise HTTPException(404, "client not found")
    return clients_data[client_id]

@app.delete("/clients/{client_id}")
async def delete_client(client_id: str):
    if client_id not in clients_data:
        raise HTTPException(404, "client not found")
    clients_data.pop(client_id)
    collection.delete_one({"machine_id": client_id})
    await sio.emit("stop_monitor", {"machine_id": client_id})
    await sio.emit("update", clients_data)
    return {"result": "deleted", "id": client_id}

@app.post("/save/{client_id}")
async def save_client_api(client_id: str, payload: dict = Body(...)):
    if not payload:
        raise HTTPException(400, "No client data sent")
    if "last_update" not in payload:
        payload["last_update"] = datetime.now().isoformat()
    old_data = clients_data.get(client_id, {})
    merged = {**old_data, **payload}
    if "platform" not in merged:
        merged["platform"] = "-"
    clients_data[client_id] = merged
    save_client_to_mongo_sync(merged)
    await sio.emit("update", clients_data)
    return {"result": "saved", "id": client_id}

@app.put("/update/{client_id}")
async def update_client(client_id: str, payload: dict = Body(...)):
    if not payload:
        raise HTTPException(400, "No client data sent")
    if "last_update" not in payload:
        payload["last_update"] = datetime.now().isoformat()
    old_data = clients_data.get(client_id, {})
    merged = {**old_data, **payload}
    if "platform" not in merged:
        merged["platform"] = "-"
    clients_data[client_id] = merged
    save_client_to_mongo_sync(merged)
    await sio.emit("update", clients_data)
    return {"result": "updated", "id": client_id}

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/")
async def root():
    return {"service": "system-monitor-backend", "clients": len(clients_data)}

# Task báo cáo hệ thống local
async def _local_reporter_task(interval: float = 5.0):
    while True:
        try:
            hostname = platform.node()
            cpu_count = psutil.cpu_count(logical=True)
            ip_address = socket.gethostbyname(socket.gethostname())
            machine_id = hex(uuid.getnode())[2:]
            cpu_percent = psutil.cpu_percent(interval=None)
            ram = psutil.virtual_memory()
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
                except:
                    continue

            # Chỉ cập nhật các trường động
            dynamic_data = {
                "cpu_percent": cpu_percent,
                "ram_used": ram.used / (1024**3),
                "ram_total": ram.total / (1024**3),
                "ram_percent": ram.percent,
                "disk_used": total_used / (1024**3),
                "disk_total": total_size / (1024**3),
                "disks": disks,
                "last_update": datetime.now().isoformat()
            }

            # Lấy dữ liệu cũ từ MongoDB nếu chưa có trong clients_data
            old_data = clients_data.get(machine_id)
            if not old_data:
                old_data = collection.find_one({"machine_id": machine_id}) or {}
                old_data.setdefault("machine_id", machine_id)
                old_data.setdefault("hostname", hostname)
                old_data.setdefault("os", platform.system() + " " + platform.release())
                old_data.setdefault("ip", ip_address)
                old_data.setdefault("cpu_count", cpu_count)
                old_data.setdefault("platform", "-")

            merged = {**old_data, **dynamic_data}
            clients_data[machine_id] = merged

            save_client_to_mongo_sync(merged)
            await sio.emit("update", clients_data)
        except Exception as e:
            print("Reporter error:", e)
        await asyncio.sleep(interval)

# Chạy server
if __name__ == "__main__":
    import uvicorn
    loop = asyncio.get_event_loop()
    loop.create_task(_local_reporter_task(5.0))
    uvicorn.run(socket_app, host="0.0.0.0", port=3000, reload=True)
