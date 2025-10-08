# main.py
import asyncio
import socketio
import psutil
import platform
import socket
from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from pymongo import MongoClient
from datetime import datetime

origins = [
    "https://monitor.lcit.vn:8000", 
    "http://localhost:4001",       
    "http://127.0.0.1:3000",
    "http://192.168.251.32:3002",
    "http://localhost:3000"
]

sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins=origins
)

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

socket_app = socketio.ASGIApp(sio, app)


connection_string = "mongodb://root:UddlLaoCaiLcit%40841889@192.168.251.32:27017/?authSource=admin"
mongo_client = MongoClient(connection_string)
app_db = mongo_client["app_database"]
collection = app_db["MAY_CHU"]

def save_client_to_mongo_sync(client_data):
    machine_id = client_data.get("machine_id")
    if not machine_id:
        return
    collection.update_one(
        {"machine_id": machine_id},
        {"$set": client_data},
        upsert=True
    )

clients_data = {}

@sio.event
async def connect(sid, environ):
    print(f"Client connected: {sid}")
    await sio.emit("update", clients_data)

@sio.event
async def disconnect(sid):
    print(f"Client disconnected: {sid}")
    await sio.emit("update", clients_data)

@sio.event
async def system_update(sid, data):
    machine_id = data.get("machine_id")
    if not machine_id:
        return

    old_data = clients_data.get(machine_id, {})
    merged = {**old_data, **data}
    merged["last_update"] = datetime.now().isoformat()
    clients_data[machine_id] = merged

    await sio.emit("update", clients_data)
    save_client_to_mongo_sync(merged)

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

            data = {
                "machine_id": machine_id,
                "hostname": hostname,
                "os": platform.system() + " " + platform.release(),
                "ip": ip_address,
                "cpu_count": cpu_count,
                "cpu_percent": cpu_percent,
                "ram_used": ram.used / (1024**3),
                "ram_total": ram.total / (1024**3),
                "ram_percent": ram.percent,
                "disk_used": total_used / (1024**3),
                "disk_total": total_size / (1024**3),
                "disks": disks,
                "last_update": datetime.now().isoformat()
            }

            old_data = clients_data.get(machine_id, {})
            merged = {**old_data, **data}
            clients_data[machine_id] = merged
            save_client_to_mongo_sync(merged)
            await sio.emit("update", clients_data)
        except:
            pass
        await asyncio.sleep(interval)

if __name__ == "__main__":
    import uvicorn
    loop = asyncio.get_event_loop()
    loop.create_task(_local_reporter_task(5.0))
    print("Starting backend on 0.0.0.0:3000")
    uvicorn.run(socket_app, host="0.0.0.0", port=3000, reload=True)

