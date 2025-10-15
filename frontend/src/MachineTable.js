// MachineTable.js
import React, { useState } from "react";
import "./Machine.css";

export function CircularProgress({ percent, size = 50, strokeWidth = 6 }) {
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (percent / 100) * circumference;

  let color = "#4caf50";
  let className = "circular-progress";
  if (percent >= 80) {
    color = "#f44336";
    className += " blink-light";
  } else if (percent >= 50) {
    color = "#ff9800";
  }

  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className={className}>
      <circle
        stroke="#e6e6e6"
        fill="transparent"
        strokeWidth={strokeWidth}
        r={radius}
        cx={size / 2}
        cy={size / 2}
      />
      <circle
        stroke={color}
        fill="transparent"
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        r={radius}
        cx={size / 2}
        cy={size / 2}
        strokeDasharray={circumference}
        strokeDashoffset={offset}
        transform={`rotate(-90 ${size / 2} ${size / 2})`}
      />
      <text
        x="50%"
        y="50%"
        dominantBaseline="middle"
        textAnchor="middle"
        fontSize={size * 0.3}
        fontWeight="bold"
        fill="#000"
        style={{ pointerEvents: "none" }}
      >
        {percent.toFixed(0)}%
      </text>
    </svg>
  );
}

export function MachineTable({ clients, onDelete, onSave, onUpdate }) {
  const [editId, setEditId] = useState(null);
  const [editData, setEditData] = useState({});
  const defaultPlatforms = ["VNPT Cloud", "Viettel Cloud", "TTCNTT LC"];

  if (!clients || Object.keys(clients).length === 0) {
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
    <div>
      <table className="machine-table">
        <thead>
          <tr>
            <th>ID</th>
            <th>Tên máy chủ</th>
            <th>HDH</th>
            <th>IP</th>
            <th>Nền tảng</th>
            <th>CPU (Core)</th>
            <th>RAM</th>
            <th>DISK (Tổng)</th>
            <th>%CPU</th>
            <th>%RAM</th>
            <th>%DISK</th>
            <th>Last Update</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {Object.entries(clients).map(([id, info]) => {
            const isEditing = editId === id;
            return (
              <tr key={id} className="machine-row">
                <td>{id}</td>
                <td>
                  {isEditing ? (
                    <input
                      value={editData.hostname || ""}
                      onChange={(e) =>
                        setEditData({ ...editData, hostname: e.target.value })
                      }
                      onKeyDown={(e) => e.key === "Enter" && onUpdate(id, editData)}
                    />
                  ) : (
                    info.hostname
                  )}
                </td>
                <td>{info.os}</td>
                <td>
                  {isEditing ? (
                    <input
                      value={editData.ip || ""}
                      onChange={(e) =>
                        setEditData({ ...editData, ip: e.target.value })
                      }
                      onKeyDown={(e) => e.key === "Enter" && onUpdate(id, editData)}
                    />
                  ) : (
                    info.ip
                  )}
                </td>
                <td>
                  {isEditing ? (
                    <>
                      <select
                        value={defaultPlatforms.includes(editData.platform) ? editData.platform : ""}
                        onChange={(e) => {
                          const value = e.target.value;
                          if (value === "other") {
                            setEditData({ ...editData, platform: "" });
                          } else {
                            setEditData({ ...editData, platform: value });
                          }
                        }}
                      >
                        <option value="">-- Chọn nền tảng --</option>
                        {defaultPlatforms.map((p) => (
                          <option key={p} value={p}>{p}</option>
                        ))}
                        <option value="other">Khác...</option>
                      </select>
                      {!defaultPlatforms.includes(editData.platform) && (
                        <input
                          placeholder="Nhập nền tảng mới"
                          value={editData.platform || ""}
                          onChange={(e) =>
                            setEditData({ ...editData, platform: e.target.value })
                          }
                          onKeyDown={(e) =>
                            e.key === "Enter" && onUpdate(id, editData)
                          }
                        />
                      )}
                    </>
                  ) : (
                    info.platform || "-"
                  )}
                </td>
                <td>{info.cpu_count || 0}</td>
                <td>{Number(info.ram_total || 0).toFixed(1)} GB</td>
                <td>
                  {Number(info.disk_used || 0).toFixed(1)} / {Number(info.disk_total || 0).toFixed(1)} GB
                </td>
                <td><CircularProgress percent={Number(info.cpu_percent || 0)} /></td>
                <td><CircularProgress percent={Number(info.ram_percent || 0)} /></td>
                <td className="disk-progress-column">
                  {(info.disks || []).map((d) => (
                    <div key={d.mount} className="disk-progress-item">
                      <span>{d.mount}: {Number(d.used || 0).toFixed(1)} / {Number(d.total || 0).toFixed(1)}</span>
                      <CircularProgress percent={Number(d.percent || 0)} size={50} strokeWidth={6} />
                    </div>
                  ))}
                </td>
                <td>{info.last_update ? new Date(info.last_update).toLocaleString() : "-"}</td>
                <td className="action-buttons">
                  {isEditing ? (
                    <>
                      <button className="btn success" onClick={() => { onUpdate(id, editData); setEditId(null); }}>Save</button>
                      <button className="btn" onClick={() => setEditId(null)}>Cancel</button>
                    </>
                  ) : (
                    <>
                      <button className="btn" onClick={() => {
                        setEditId(id);
                        setEditData({
                          hostname: info.hostname,
                          ip: info.ip,
                          platform: info.platform || "",
                        });
                      }}>Edit</button>
                      {typeof onSave === "function" && <button className="btn primary" onClick={() => onSave(id)}>Save</button>}
                      {typeof onDelete === "function" && <button className="btn danger" onClick={() => onDelete(id)}>Delete</button>}
                    </>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
