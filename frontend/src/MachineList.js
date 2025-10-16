import React, { useState, useEffect } from "react";
import { io } from "socket.io-client";
import "./Machine.css";
import { MachineTable } from "./MachineTable";

const API_BASE = "https://monitor.lcit.vn:4001";
const socket = io(API_BASE, { transports: ["websocket"] });

export default function MachineList() {
  const [clients, setClients] = useState({});
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // 🔹 Lấy dữ liệu ban đầu qua API
    const fetchInitialData = async () => {
      try {
        const res = await fetch(`${API_BASE}/clients`);
        if (!res.ok) throw new Error("Failed to fetch clients");
        const data = await res.json();
        setClients(data);
      } catch (err) {
        console.error("Error fetching clients:", err);
      } finally {
        setLoading(false);
      }
    };

    fetchInitialData();

    socket.on("update", (data) => setClients(data));
    socket.on("connect", () => console.log("Connected to backend"));
    socket.on("disconnect", () => console.log("Disconnected from backend"));

    return () => {
      socket.off("update");
      socket.off("connect");
      socket.off("disconnect");
    };
  }, []);

  const handleSave = async (id) => {
    try {
      const clientData = { ...clients[id] };
      if (!clientData) return;
      const res = await fetch(`${API_BASE}/save/${id}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(clientData),
      });
      if (!res.ok) throw new Error(await res.text());
    } catch (err) {
      alert("Save failed: " + err.message);
    }
  };

  const handleDelete = async (id) => {
    if (!window.confirm("Delete client?")) return;
    try {
      const res = await fetch(`${API_BASE}/clients/${id}`, { method: "DELETE" });
      if (!res.ok) throw new Error(await res.text());
    } catch (err) {
      alert("Delete failed: " + err.message);
    }
  };

  const handleUpdate = async (machine_id, newData) => {
    try {
      const res = await fetch(`${API_BASE}/update/${machine_id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(newData),
      });
      if (!res.ok) throw new Error(await res.text());
    } catch (err) {
      alert("Update failed: " + err.message);
    }
  };

  if (loading) {
    return (
      <div className="loader-fullscreen">
        <div className="loader-container">
          <div className="neon-spinner">
            <svg viewBox="0 0 150 150">
              <circle className="spinner-bg" cx="75" cy="75" r="70" />
              <circle className="spinner" cx="75" cy="75" r="70" />
              <circle className="spinner-light" cx="75" cy="75" r="70" />
            </svg>
          </div>
          <div className="loader-text">Loading...</div>
        </div>
      </div>
    );
  }

  return (
    <MachineTable
      clients={clients}
      onSave={handleSave}
      onDelete={handleDelete}
      onUpdate={handleUpdate}
    />
  );
}
