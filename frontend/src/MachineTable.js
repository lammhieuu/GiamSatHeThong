// MachineTable.js
import React, { useState, useMemo, useRef, useEffect } from "react";
import "./Machine.css";

const API_BASE = "https://monitor.lcit.vn:4001";

export function CircularProgress({ percent, size = 50, strokeWidth = 6 }) {
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (percent / 100) * circumference;

  let color = "#4caf50";
  if (percent >= 80) color = "#f44336";
  else if (percent >= 50) color = "#ffa726";

  return (
    <svg
      width={size}
      height={size}
      viewBox={`0 0 ${size} ${size}`}
      className="circular-progress"
    >
      <circle
        stroke="#2a2a2a"
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
        fontSize={size * 0.28}
        fontWeight="600"
        fill="#ffffff"
      >
        {percent.toFixed(0)}%
      </text>
    </svg>
  );
}

function FilterPopup({ field, type, options, onClose, onApply, currentValue, position }) {
  const ref = useRef();

  useEffect(() => {
    const handleClickOutside = (e) => {
      if (ref.current && !ref.current.contains(e.target)) onClose();
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [onClose]);

  return (
    <div
      ref={ref}
      className="filter-popup"
      style={{
        top: position.top + 30,
        left: position.left,
      }}
    >
      {type === "select" ? (
        <select
          value={currentValue || ""}
          onChange={(e) => {
            onApply(e.target.value);
            onClose();
          }}
        >
          {options.map((opt) => (
            <option key={opt} value={opt === "Mặc định" ? "" : opt}>
              {opt}
            </option>
          ))}
        </select>
      ) : (
        <input
          type="text"
          placeholder={`Nhập ${field}`}
          autoFocus
          value={currentValue || ""}
          onChange={(e) => onApply(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && onClose()}
        />
      )}
    </div>
  );
}

// Component hiển thị popup các cổng đang lắng nghe
function PortsPopup({ machineId, hostname, onClose }) {
  const [ports, setPorts] = useState([]);
  const [loading, setLoading] = useState(true);
  const popupRef = useRef();

  useEffect(() => {
    const fetchPorts = async () => {
      try {
        const res = await fetch(`${API_BASE}/clients/${machineId}/ports`);
        if (!res.ok) throw new Error("Failed to fetch ports");
        const data = await res.json();
        setPorts(data.listening_ports || []);
      } catch (err) {
        console.error("Error fetching ports:", err);
      } finally {
        setLoading(false);
      }
    };

    fetchPorts();

    const handleEscape = (e) => {
      if (e.key === "Escape") onClose();
    };

    document.addEventListener("keydown", handleEscape);
    return () => document.removeEventListener("keydown", handleEscape);
  }, [machineId, onClose]);

  return (
    <div className="ports-popup-backdrop" onClick={onClose}>
      <div ref={popupRef} className="ports-popup" onClick={(e) => e.stopPropagation()}>
        <div className="ports-popup-header">
          <h3>Các cổng đang lắng nghe - {hostname || machineId}</h3>
          <button className="close-btn" onClick={onClose}>×</button>
        </div>
        
        {loading ? (
          <div className="ports-loading">Đang tải...</div>
        ) : ports.length === 0 ? (
          <div className="no-ports">Không có cổng nào đang lắng nghe</div>
        ) : (
          <div className="ports-table-wrapper">
            <table className="ports-table">
              <thead>
                <tr>
                  <th>Protocol</th>
                  <th>Address</th>
                  <th>Port</th>
                  <th>PID</th>
                  <th>Process</th>
                </tr>
              </thead>
              <tbody>
                {ports.map((port, idx) => (
                  <tr key={idx}>
                    <td>{port.protocol}</td>
                    <td>{port.address}</td>
                    <td className="port-number">{port.port}</td>
                    <td>{port.pid || "-"}</td>
                    <td className="process-name">{port.process}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

// Component hiển thị danh sách IP
function IPAddressList({ ipAddresses }) {
  if (!ipAddresses || ipAddresses.length === 0) return <span>-</span>;
  
  if (ipAddresses.length === 1) {
    return <span>{ipAddresses[0].ip}</span>;
  }
  
  return (
    <div className="ip-address-list">
      {ipAddresses.map((item, idx) => (
        <div key={idx} className="ip-address-item">
          <span className="interface-name">{item.interface}:</span>
          <span className="ip-value">{item.ip}</span>
        </div>
      ))}
    </div>
  );
}

export function MachineTable({ clients, onDelete, onSave, onUpdate }) {
  const [editId, setEditId] = useState(null);
  const [editData, setEditData] = useState({});
  const [filters, setFilters] = useState({});
  const [sortConfig, setSortConfig] = useState({ key: null, direction: "none" });
  const [popup, setPopup] = useState(null);
  const [portsPopup, setPortsPopup] = useState(null);

  const defaultPlatforms = ["Mặc định", "VNPT Cloud", "Viettel Cloud", "TTCNTT LC", "Khác"];

  const getSortIcon = (key) => {
    if (sortConfig.key !== key) return "⇅";
    if (sortConfig.direction === "asc") return "↑";
    if (sortConfig.direction === "desc") return "↓";
    return "⇅";
  };

  const handleSort = (key) => {
    setSortConfig((prev) => {
      if (prev.key !== key) return { key, direction: "asc" };
      if (prev.direction === "asc") return { key, direction: "desc" };
      if (prev.direction === "desc") return { key: null, direction: "none" };
      return { key, direction: "asc" };
    });
  };

  const handleFilterPopup = (field, type, event) => {
    event.stopPropagation();
    const rect = event.target.getBoundingClientRect();
    setPopup({
      field,
      type,
      position: {
        top: rect.bottom + window.scrollY,
        left: rect.left + window.scrollX,
      },
    });
  };

  const handleRowClick = (machineId, hostname) => {
    if (editId !== machineId) {
      setPortsPopup({ machineId, hostname });
    }
  };

  const filteredClients = useMemo(() => {
    let result = Object.entries(clients);
    const predefinedPlatforms = ["VNPT Cloud", "Viettel Cloud", "TTCNTT LC"];
    
    for (const [key, value] of Object.entries(filters)) {
      if (!value || value.trim() === "") continue;
      
      result = result.filter(([_, info]) => {
        const infoValue = info[key];
        
        // Xử lý đặc biệt cho filter platform = "Khác"
        if (key === "platform" && value === "Khác") {
          const platform = infoValue?.toString().trim() || "";
          // Hiển thị các nền tảng KHÔNG PHẢI là 3 nền tảng có sẵn
          return platform !== "" && 
                 platform !== "-" && 
                 !predefinedPlatforms.includes(platform);
        }
        
        // Filter bình thường cho các trường khác
        if (infoValue === null || infoValue === undefined) return false;
        const val = infoValue.toString().toLowerCase().trim();
        const filterVal = value.toString().toLowerCase().trim();
        return val.includes(filterVal);
      });
    }
    return result;
  }, [clients, filters]);

  const sortedClients = useMemo(() => {
    let sorted = [...filteredClients];
    const { key, direction } = sortConfig;
    if (direction === "none" || !key) return sorted;

    sorted.sort(([_, a], [__, b]) => {
      const order = direction === "asc" ? 1 : -1;
      switch (key) {
        case "cpu_count":
          return (a.cpu_count || 0) > (b.cpu_count || 0) ? order : -order;
        case "ram_total":
          return (a.ram_total || 0) > (b.ram_total || 0) ? order : -order;
        case "disk_total":
          const diskA = a.disk_total || a.disk_used || 0;
          const diskB = b.disk_total || b.disk_used || 0;
          if (diskA === diskB) return (a.cpu_count || 0) - (b.cpu_count || 0);
          return diskA > diskB ? order : -order;
        case "last_update":
          const timeA = new Date(a.last_update || 0).getTime();
          const timeB = new Date(b.last_update || 0).getTime();
          return timeA > timeB ? order : -order;
        default:
          return 0;
      }
    });
    return sorted;
  }, [filteredClients, sortConfig]);

  if (!clients || Object.keys(clients).length === 0)
    return <div className="no-clients">Không có dữ liệu máy chủ</div>;

  return (
    <div style={{ position: "relative" }}>
      {popup && (
        <FilterPopup
          field={popup.field}
          type={popup.type}
          options={defaultPlatforms}
          position={popup.position}
          currentValue={filters[popup.field] || ""}
          onApply={(value) => setFilters({ ...filters, [popup.field]: value })}
          onClose={() => setPopup(null)}
        />
      )}

      {portsPopup && (
        <PortsPopup
          machineId={portsPopup.machineId}
          hostname={portsPopup.hostname}
          onClose={() => setPortsPopup(null)}
        />
      )}

      <table className="machine-table">
        <thead>
          <tr>
            <th onClick={(e) => handleFilterPopup("machine_id", "text", e)}>ID</th>
            <th onClick={(e) => handleFilterPopup("hostname", "text", e)}>Tên máy chủ</th>
            <th onClick={(e) => handleFilterPopup("os", "text", e)}>Hệ điều hành</th>
            <th onClick={(e) => handleFilterPopup("ip", "text", e)}>Địa chỉ IP</th>
            <th onClick={(e) => handleFilterPopup("platform", "select", e)}>Nền tảng</th>
            <th onClick={() => handleSort("cpu_count")}>CPU (Core) {getSortIcon("cpu_count")}</th>
            <th onClick={() => handleSort("ram_total")}>RAM {getSortIcon("ram_total")}</th>
            <th onClick={() => handleSort("disk_total")}>DISK (Tổng) {getSortIcon("disk_total")}</th>
            <th>%CPU</th>
            <th>%RAM</th>
            <th>%DISK</th>
            <th onClick={() => handleSort("last_update")}>
              Last Update {getSortIcon("last_update")}
            </th>
            <th></th>
          </tr>
        </thead>

        <tbody>
          {sortedClients.map(([id, info]) => {
            const isEditing = editId === id;
            return (
              <tr 
                key={id} 
                className="machine-row"
                onClick={() => handleRowClick(id, info.hostname)}
                style={{ cursor: isEditing ? 'default' : 'pointer' }}
              >
                <td>{id}</td>
                <td>
                  {isEditing ? (
                    <input
                      value={editData.hostname || ""}
                      onChange={(e) =>
                        setEditData({ ...editData, hostname: e.target.value })
                      }
                      onClick={(e) => e.stopPropagation()}
                      onKeyDown={(e) => e.key === "Enter" && onUpdate(id, editData)}
                    />
                  ) : (
                    info.hostname || "-"
                  )}
                </td>
                <td>{info.os || "-"}</td>
                <td>
                  {isEditing ? (
                    <input
                      value={editData.ip || ""}
                      onChange={(e) =>
                        setEditData({ ...editData, ip: e.target.value })
                      }
                      onClick={(e) => e.stopPropagation()}
                      onKeyDown={(e) => e.key === "Enter" && onUpdate(id, editData)}
                    />
                  ) : (
                    <IPAddressList ipAddresses={info.ip_addresses} />
                  )}
                </td>
                <td>
                  {isEditing ? (
                    <>
                      <select
                        value={editData.platform === "Khác" ? "Khác" : (editData.platform || "")}
                        onChange={(e) => {
                          const value = e.target.value;
                          setEditData({ 
                            ...editData, 
                            platform: value,
                            customPlatform: value === "Khác" ? (editData.customPlatform || "") : ""
                          });
                        }}
                        onClick={(e) => e.stopPropagation()}
                        style={{ width: "100%", marginBottom: editData.platform === "Khác" ? "8px" : "0" }}
                      >
                        <option value="">-- Chọn nền tảng --</option>
                        <option value="VNPT Cloud">VNPT Cloud</option>
                        <option value="Viettel Cloud">Viettel Cloud</option>
                        <option value="TTCNTT LC">TTCNTT LC</option>
                        <option value="Khác">Khác</option>
                      </select>
                      {editData.platform === "Khác" && (
                        <input
                          type="text"
                          placeholder="Nhập nền tảng khác..."
                          value={editData.customPlatform || ""}
                          onChange={(e) =>
                            setEditData({ ...editData, customPlatform: e.target.value })
                          }
                          onClick={(e) => e.stopPropagation()}
                          onKeyDown={(e) => e.key === "Enter" && onUpdate(id, editData)}
                          style={{ width: "100%", marginTop: "4px" }}
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
                  {Number(info.disk_used || 0).toFixed(1)} /{" "}
                  {Number(info.disk_total || 0).toFixed(1)} GB
                </td>
                <td className="realtime-value">
                  <CircularProgress percent={Number(info.cpu_percent || 0)} />
                </td>
                <td className="realtime-value">
                  <CircularProgress percent={Number(info.ram_percent || 0)} />
                </td>
                <td className="disk-progress-column realtime-value">
                  {(info.disks || []).map((d) => (
                    <div key={d.mount} className="disk-progress-item">
                      <span>
                        {d.mount}: {Number(d.used || 0).toFixed(1)} /{" "}
                        {Number(d.total || 0).toFixed(1)}
                      </span>
                      <CircularProgress
                        percent={Number(d.percent || 0)}
                        size={50}
                        strokeWidth={6}
                      />
                    </div>
                  ))}
                </td>
                <td className="realtime-value">
                  {info.last_update
                    ? new Date(info.last_update).toLocaleString()
                    : "-"}
                </td>
                <td className="action-buttons" onClick={(e) => e.stopPropagation()}>
                  {isEditing ? (
                    <>
                      <button
                        className="btn btn-save"
                        onClick={() => {
                          const dataToSave = { ...editData };
                          if (dataToSave.platform === "Khác" && dataToSave.customPlatform) {
                            dataToSave.platform = dataToSave.customPlatform;
                          }
                          delete dataToSave.customPlatform;
                          onUpdate(id, dataToSave);
                          setEditId(null);
                        }}
                      >
                        Save
                      </button>
                      <button className="btn btn-cancel" onClick={() => setEditId(null)}>
                        Cancel
                      </button>
                    </>
                  ) : (
                    <>
                      <button
                        className="btn btn-edit"
                        onClick={() => {
                          setEditId(id);
                          const platformOptions = ["VNPT Cloud", "Viettel Cloud", "TTCNTT LC"];
                          const isCustomPlatform = info.platform && !platformOptions.includes(info.platform);
                          setEditData({
                            hostname: info.hostname,
                            ip: info.ip,
                            platform: isCustomPlatform ? "Khác" : (info.platform || ""),
                            customPlatform: isCustomPlatform ? info.platform : "",
                          });
                        }}
                      >
                        Edit
                      </button>
                      {typeof onSave === "function" && (
                        <button className="btn btn-save" onClick={() => onSave(id)}>
                          Save
                        </button>
                      )}
                      {typeof onDelete === "function" && (
                        <button
                          className="btn btn-delete"
                          onClick={() => onDelete(id)}
                        >
                          Delete
                        </button>
                      )}
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