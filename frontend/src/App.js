import React, { useState } from "react";
import MachineList from "./MachineList";
import Login from "./Login";

function App() {
  const [user, setUser] = useState(null);
  if (!user) {
    return <Login onLogin={(tk) => setUser(tk)} />;
  }
  return <MachineList />;
}

export default App;
