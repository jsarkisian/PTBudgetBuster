import { useState, useEffect } from "react";
import Login from "./components/Login";
import Dashboard from "./components/Dashboard";
import EngagementSetup from "./components/EngagementSetup";
import EngagementLive from "./components/EngagementLive";
import ExploitApproval from "./components/ExploitApproval";
import FindingsReport from "./components/FindingsReport";
import AdminPanel from "./components/AdminPanel";
import { getMe } from "./utils/api";

export default function App() {
  const [user, setUser] = useState(null);
  const [view, setView] = useState("dashboard");
  const [selectedEngagement, setSelectedEngagement] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem("token");
    if (token) {
      getMe().then(setUser).catch(() => localStorage.removeItem("token")).finally(() => setLoading(false));
    } else {
      setLoading(false);
    }
  }, []);

  if (loading) return <div className="min-h-screen bg-gray-950 flex items-center justify-center text-gray-400">Loading...</div>;
  if (!user) return <Login onLogin={setUser} />;

  const navigate = (v, engId = null) => {
    setView(v);
    if (engId !== null) setSelectedEngagement(engId);
  };

  const handleLogout = () => {
    localStorage.removeItem("token");
    setUser(null);
    setView("dashboard");
  };

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100">
      <header className="bg-gray-900 border-b border-gray-800 px-6 py-3 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <h1 className="text-lg font-bold cursor-pointer" onClick={() => navigate("dashboard")}>
            PTBudgetBuster
          </h1>
          {user.role === "admin" && (
            <button onClick={() => navigate("admin")} className="text-sm text-gray-400 hover:text-gray-200">
              Users
            </button>
          )}
        </div>
        <div className="flex items-center gap-3 text-sm text-gray-400">
          <span>{user.display_name || user.username}</span>
          <button onClick={handleLogout} className="hover:text-gray-200">Logout</button>
        </div>
      </header>
      <main>
        {view === "dashboard" && <Dashboard user={user} navigate={navigate} />}
        {view === "setup" && <EngagementSetup navigate={navigate} />}
        {view === "live" && <EngagementLive engagementId={selectedEngagement} navigate={navigate} />}
        {view === "approval" && <ExploitApproval engagementId={selectedEngagement} navigate={navigate} />}
        {view === "findings" && <FindingsReport engagementId={selectedEngagement} navigate={navigate} />}
        {view === "admin" && <AdminPanel navigate={navigate} />}
      </main>
    </div>
  );
}
