// Login.js
import React, { useState } from "react";
import "./Machine.css"; 

const API_BASE = "https://monitor.lcit.vn:4001";

export default function Login({ onLogin }) {
  const [tk, setTk] = useState("");
  const [mk, setMk] = useState("");
  const [error, setError] = useState("");

  const handleSubmit = async (e) => {
    e.preventDefault();
    try {
      const res = await fetch(`${API_BASE}/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tk, mk }),
      });
      if (!res.ok) {
        const text = await res.text();
        throw new Error(text);
      }
      const data = await res.json();
      setError("");
      onLogin(data.tk); // thông báo đăng nhập thành công cho App.js
    } catch (err) {
      setError("Sai tài khoản hoặc mật khẩu");
    }
  };

  return (
    <div className="login-container">
      <h2>Đăng nhập</h2>
      <form onSubmit={handleSubmit}>
        <input
          type="text"
          placeholder="Tài khoản"
          value={tk}
          onChange={(e) => setTk(e.target.value)}
        />
        <input
          type="password"
          placeholder="Mật khẩu"
          value={mk}
          onChange={(e) => setMk(e.target.value)}
        />
        <button type="submit">Đăng nhập</button>
      </form>
      {error && <p style={{ color: "red" }}>{error}</p>}
    </div>
  );
}
