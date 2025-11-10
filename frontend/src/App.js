import React, { useState, useEffect } from "react";
import MachineList from "./MachineList";
import Login from "./Login";

function App() {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  // Kiểm tra session khi component mount
  useEffect(() => {
    const savedUser = sessionStorage.getItem("user");
    if (savedUser) {
      try {
        const userData = JSON.parse(savedUser);
        setUser(userData);
      } catch (err) {
        console.error("Error parsing user data:", err);
        sessionStorage.removeItem("user");
      }
    }
    setLoading(false);
  }, []);

  const handleLogin = (tk) => {
    const userData = { tk, loginTime: new Date().toISOString() };
    setUser(userData);
    // Lưu vào sessionStorage
    sessionStorage.setItem("user", JSON.stringify(userData));
  };

  const handleLogout = () => {
    setUser(null);
    sessionStorage.removeItem("user");
  };

  if (loading) {
    return (
      <div style={{ 
        display: "flex", 
        justifyContent: "center", 
        alignItems: "center", 
        height: "100vh",
        color: "#00ffff"
      }}>
        Loading...
      </div>
    );
  }

  if (!user) {
    return <Login onLogin={handleLogin} />;
  }

  return <MachineList user={user} onLogout={handleLogout} />;
}

export default App;