import React, { useState, useEffect } from "react";
import { io } from "socket.io-client";
import "./Machine.css";
import { MachineTable } from "./MachineTable";

const API_BASE = process.env.REACT_APP_API_URL || "http://localhost:8000";
const socket = io(API_BASE, { transports: ["websocket"] });

export default function MachineList() {
  const [clients, setClients] = useState({});

  useEffect(() => {
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
      const clientData = clients[id];
      if (!clientData) return;
      const res = await fetch(`${API_BASE}/save/${id}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(clientData),
      });
      if (!res.ok) throw new Error(await res.text());
      // alert(`Client ${id} saved successfully!`);
    } catch (err) {
      alert("Save failed: " + err.message);
    }
  };

  const handleDelete = async (id) => {
    if (!window.confirm("Delete client?")) return;
    try {
      const res = await fetch(`${API_BASE}/clients/${id}`, { method: "DELETE" });
      if (!res.ok) throw new Error(await res.text());
      // alert(`Client ${id} deleted successfully!`);
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
      // alert(`Client ${machine_id} updated successfully!`);
    } catch (err) {
      alert("Update failed: " + err.message);
    }
  };

  return <MachineTable clients={clients} onSave={handleSave} onDelete={handleDelete} onUpdate={handleUpdate} />;
}
