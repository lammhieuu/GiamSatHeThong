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

origins = [
    "https://monitor.lcit.vn:4001",
    "https://monitor.lcit.vn:8000",
    "http://localhost:4001",
    "http://127.0.0.1:3000",
    "http://192.168.10.43:4001",
    "http://192.168.251.32:3002",
    "http://localhost:3000"
]

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

connection_string = "mongodb+srv://lammhieuu_db_user:scm123456@server.2bf1k73.mongodb.net/?retryWrites=true&w=majority&appName=Server"
mongo_client = MongoClient(connection_string)
app_db = mongo_client["app_database"]
collection = app_db["MAY_CHU"]

def save_client_to_mongo_sync(client_data):
    machine_id = client_data.get("machine_id")
    if not machine_id:
        return
    return collection.update_one({"machine_id": machine_id}, {"$set": client_data}, upsert=True)

def load_clients_from_db():
    clients = {}
    for doc in collection.find():
        machine_id = doc.get("machine_id")
        if machine_id:
            doc.setdefault("platform", "-")
            doc.setdefault("last_update", datetime.now().isoformat())
            clients[machine_id] = doc
    return clients

clients_data = load_clients_from_db()

def make_serializable(data):
    result = {}
    for k, v in data.items():
        v_copy = v.copy()
        if "_id" in v_copy:
            v_copy["_id"] = str(v_copy["_id"])
        result[k] = v_copy
    return result

@sio.event
async def connect(sid, environ, auth=None):
    await sio.emit("update", make_serializable(clients_data))

@sio.event
async def disconnect(sid):
    await sio.emit("update", make_serializable(clients_data))

@sio.event
async def system_update(sid, data):
    machine_id = data.get("machine_id")
    if not machine_id:
        return

    db_doc = collection.find_one({"machine_id": machine_id})
    if db_doc:
        dynamic_fields = ["cpu_percent", "ram_used", "ram_total", "ram_percent", "disk_used", "disks", "last_update"]
        for field in dynamic_fields:
            if field in data:
                db_doc[field] = data[field]
        clients_data[machine_id] = db_doc
        save_client_to_mongo_sync(db_doc)
    else:
        data.setdefault("platform", "-")
        data.setdefault("last_update", datetime.now().isoformat())
        clients_data[machine_id] = data
        save_client_to_mongo_sync(data)

    await sio.emit("update", make_serializable(clients_data))

@app.get("/clients")
async def get_clients():
    return make_serializable(clients_data)

@app.get("/clients/{client_id}")
async def get_client(client_id: str):
    if client_id not in clients_data:
        raise HTTPException(404, "client not found")
    item = clients_data[client_id].copy()
    if "_id" in item:
        item["_id"] = str(item["_id"])
    return item

@app.delete("/clients/{client_id}")
async def delete_client(client_id: str):
    if client_id not in clients_data:
        raise HTTPException(404, "client not found")
    clients_data.pop(client_id)
    collection.delete_one({"machine_id": client_id})
    await sio.emit("stop_monitor", {"machine_id": client_id})
    await sio.emit("update", make_serializable(clients_data))
    return {"result": "deleted", "id": client_id}

@app.post("/save/{client_id}")
async def save_client_api(client_id: str, payload: dict = Body(...)):
    if not payload:
        raise HTTPException(400, "No client data sent")
    if "last_update" not in payload:
        payload["last_update"] = datetime.now().isoformat()
    old_data = clients_data.get(client_id, {})
    merged = {**old_data, **payload}
    merged.setdefault("platform", "-")
    clients_data[client_id] = merged
    save_client_to_mongo_sync(merged)
    await sio.emit("update", make_serializable(clients_data))
    return {"result": "saved", "id": client_id}

@app.put("/update/{client_id}")
async def update_client(client_id: str, payload: dict = Body(...)):
    if not payload:
        raise HTTPException(400, "No client data sent")
    if "last_update" not in payload:
        payload["last_update"] = datetime.now().isoformat()
    old_data = clients_data.get(client_id, {})
    merged = {**old_data, **payload}
    merged.setdefault("platform", "-")
    clients_data[client_id] = merged
    save_client_to_mongo_sync(merged)
    await sio.emit("update", make_serializable(clients_data))
    return {"result": "updated", "id": client_id}

@app.post("/refresh_clients")
async def refresh_clients():
    global clients_data
    clients_data = load_clients_from_db()
    await sio.emit("update", make_serializable(clients_data))
    return {"status": "refreshed"}

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/")
async def root():
    return {"service": "system-monitor-backend", "clients": len(clients_data)}

async def _local_reporter_task(interval: float = 5.0):
    while True:
        try:
            if not clients_data:
                await asyncio.sleep(interval)
                continue
            for machine_id in list(clients_data.keys()):
                client = clients_data[machine_id]
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
                dynamic_data = {
                    "cpu_percent": cpu_percent,
                    "ram_used": ram.used / (1024**3),
                    "ram_total": ram.total / (1024**3),
                    "ram_percent": ram.percent,
                    "disk_used": total_used / (1024**3),
                    "disks": disks,
                    "last_update": datetime.now().isoformat()
                }
                for field in dynamic_data:
                    client[field] = dynamic_data[field]
                clients_data[machine_id] = client
                save_client_to_mongo_sync(client)
            await sio.emit("update", make_serializable(clients_data))
        except Exception as e:
            print("Reporter error:", e)
        await asyncio.sleep(interval)

if __name__ == "__main__":
    import uvicorn
    loop = asyncio.get_event_loop()
    loop.create_task(_local_reporter_task(5.0))
    uvicorn.run(socket_app, host="0.0.0.0", port=4001, reload=True)
