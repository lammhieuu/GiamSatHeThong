#main.py
import asyncio
import socketio
import psutil
from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from pymongo import MongoClient
from datetime import datetime

# --- Cấu hình CORS ---
origins = [
    "https://monitor.lcit.vn:4001",
    "https://monitor.lcit.vn:8000",
    "https://monitor.lcit.vn",
    "http://localhost:4001",
    "http://127.0.0.1:3000",
    "http://192.168.10.43:4001",
    "http://192.168.251.32:3002",
    "http://localhost:3000"
]
#
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

connection_string = "mongodb://root:UddlLaoCaiLcit%40841889@192.168.251.32:27017/?authSource=admin"
mongo_client = MongoClient(connection_string)
app_db = mongo_client["app_database"]
collection = app_db["MAY_CHU"]

def make_serializable(clients):
    result = {}
    for k, v in clients.items():
        v_copy = v.copy()
        if "_id" in v_copy:
            v_copy["_id"] = str(v_copy["_id"])
        result[k] = v_copy
    return result

@sio.event
async def connect(sid, environ, auth=None):
    all_clients = {doc["machine_id"]: doc for doc in collection.find()}
    await sio.emit("update", make_serializable(all_clients), to=sid)

@sio.event
async def disconnect(sid):
    all_clients = {doc["machine_id"]: doc for doc in collection.find()}
    await sio.emit("update", make_serializable(all_clients))

@sio.event
async def system_update(sid, data):
    machine_id = data.get("machine_id")
    if not machine_id:
        return

    db_doc = collection.find_one({"machine_id": machine_id})
    if db_doc:
        dynamic_fields = ["cpu_percent", "ram_used", "ram_total", "ram_percent", "disk_used", "disks", "last_update"]
        update_data = {field: data[field] for field in dynamic_fields if field in data}
        collection.update_one({"machine_id": machine_id}, {"$set": update_data})
    else:
        data.setdefault("platform", "-")
        data.setdefault("last_update", datetime.now().isoformat())
        collection.insert_one(data)

    all_clients = {doc["machine_id"]: doc for doc in collection.find()}
    await sio.emit("update", make_serializable(all_clients))

# --- API ---
@app.get("/clients")
async def get_clients():
    all_clients = {doc["machine_id"]: doc for doc in collection.find({}, {"_id": 0})}
    return all_clients

@app.get("/clients/{client_id}")
async def get_client(client_id: str):
    doc = collection.find_one({"machine_id": client_id})
    if not doc:
        raise HTTPException(404, "client not found")
    if "_id" in doc:
        doc["_id"] = str(doc["_id"])
    return doc

@app.delete("/clients/{client_id}")
async def delete_client(client_id: str):
    doc = collection.find_one({"machine_id": client_id})
    if not doc:
        raise HTTPException(404, "client not found")
    collection.delete_one({"machine_id": client_id})
    await sio.emit("stop_monitor", {"machine_id": client_id})
    all_clients = {d["machine_id"]: d for d in collection.find()}
    await sio.emit("update", make_serializable(all_clients))
    return {"result": "deleted", "id": client_id}

@app.post("/save/{client_id}")
async def save_client_api(client_id: str, payload: dict = Body(...)):
    if not payload:
        raise HTTPException(400, "No client data sent")
    payload.setdefault("last_update", datetime.now().isoformat())
    payload.setdefault("platform", "-")
    collection.update_one({"machine_id": client_id}, {"$set": payload}, upsert=True)
    all_clients = {d["machine_id"]: d for d in collection.find()}
    await sio.emit("update", make_serializable(all_clients))
    return {"result": "saved", "id": client_id}

@app.put("/update/{client_id}")
async def update_client(client_id: str, payload: dict = Body(...)):
    if not payload:
        raise HTTPException(400, "No client data sent")
    payload.setdefault("last_update", datetime.now().isoformat())
    payload.setdefault("platform", "-")
    collection.update_one({"machine_id": client_id}, {"$set": payload}, upsert=True)
    all_clients = {d["machine_id"]: d for d in collection.find()}
    await sio.emit("update", make_serializable(all_clients))
    return {"result": "updated", "id": client_id}

@app.post("/refresh_clients")
async def refresh_clients():
    all_clients = {d["machine_id"]: d for d in collection.find()}
    await sio.emit("update", make_serializable(all_clients))
    return {"status": "refreshed"}

@app.post("/login")
async def login(payload: dict = Body(...)):
    tk = payload.get("tk")
    mk = payload.get("mk")
    if not tk or not mk:
        raise HTTPException(400, "Missing credentials")

    DEFAULT_USERNAME = "admin"
    DEFAULT_PASSWORD = "123456"

    if tk != DEFAULT_USERNAME or mk != DEFAULT_PASSWORD:
        raise HTTPException(401, "Invalid username or password")

    return {"status": "ok", "tk": tk}

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/")
async def root():
    total = collection.count_documents({})
    return {"service": "system-monitor-backend", "clients": total}

async def _local_reporter_task(interval: float = 5.0):
    while True:
        try:
            for doc in collection.find():
                machine_id = doc["machine_id"]
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
                collection.update_one({"machine_id": machine_id}, {"$set": dynamic_data})
            all_clients = {d["machine_id"]: d for d in collection.find()}
            await sio.emit("update", make_serializable(all_clients))
        except Exception as e:
            print("Reporter error:", e)
        await asyncio.sleep(interval)

if __name__ == "__main__":
    import uvicorn
    loop = asyncio.get_event_loop()
    loop.create_task(_local_reporter_task(5.0))
    uvicorn.run(socket_app, host="0.0.0.0", port=4001, reload=True)
