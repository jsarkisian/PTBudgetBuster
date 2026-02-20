import React, { useState, useCallback, useEffect, useRef } from 'react';
import { api, isAuthenticated, setToken } from './utils/api';
import { useWebSocket } from './hooks/useWebSocket';
import Header from './components/Header';
import SessionSidebar from './components/SessionSidebar';
import ChatPanel from './components/ChatPanel';
import OutputPanel from './components/OutputPanel';
import ToolPanel from './components/ToolPanel';
import FindingsPanel from './components/FindingsPanel';
import AutoPanel from './components/AutoPanel';
import AdminPanel from './components/AdminPanel';
import SettingsPanel from './components/SettingsPanel';
import ToolsAdmin from './components/ToolsAdmin';
import NewSessionModal from './components/NewSessionModal';
import EditSessionModal from './components/EditSessionModal';
import LoginScreen from './components/LoginScreen';
import HomePage from './components/HomePage';
import ClientsPanel from './components/ClientsPanel';
import ScreenshotGallery from './components/ScreenshotGallery';
import FileManager from './components/FileManager';
import SchedulerPanel from './components/SchedulerPanel';
import PresenceBar from './components/PresenceBar';
import ActivityLogPanel from './components/ActivityLogPanel';

export default function App() {
  const [currentUser, setCurrentUser] = useState(null);
  const [authChecked, setAuthChecked] = useState(false);
  const [sessions, setSessions] = useState([]);
  const [activeSession, setActiveSession] = useState(null);
  const [activeTab, setActiveTab] = useState(() => sessionStorage.getItem('activeTab') || 'chat');
  const [restoredSessionId, setRestoredSessionId] = useState(() => sessionStorage.getItem('activeSessionId') || null);
  const [messages, setMessages] = useState([]);
  const [outputs, setOutputs] = useState([]);
  const [findings, setFindings] = useState([]);
  const [tools, setTools] = useState({});
  const [pendingApproval, setPendingApproval] = useState(null);
  const [showNewSession, setShowNewSession] = useState(false);
  const [editingSession, setEditingSession] = useState(null);
  const [health, setHealth] = useState(null);
  const [logoUrl, setLogoUrl] = useState(null);
  const [chatLoading, setChatLoading] = useState(false);
  const [toolLoading, setToolLoading] = useState(false);
  const chatAbortRef = React.useRef(null);
  const [clients, setClients] = useState([]);
  const [onlineUsers, setOnlineUsers] = useState([]);

  // Resizable output pane — persisted across sessions
  const [outputWidth, setOutputWidth] = useState(() => {
    const saved = localStorage.getItem('outputPaneWidth');
    return saved ? parseFloat(saved) : 45;
  });
  const splitContainerRef = useRef(null);
  const dragState = useRef({ dragging: false, startX: 0, startWidth: 0 });

  useEffect(() => {
    const onMove = (e) => {
      if (!dragState.current.dragging || !splitContainerRef.current) return;
      const containerWidth = splitContainerRef.current.offsetWidth;
      const delta = dragState.current.startX - e.clientX; // drag left → wider output
      const newPct = dragState.current.startWidth + (delta / containerWidth) * 100;
      const clamped = Math.min(75, Math.max(20, newPct));
      setOutputWidth(clamped);
      localStorage.setItem('outputPaneWidth', clamped);
    };
    const onUp = () => {
      dragState.current.dragging = false;
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
    return () => {
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup', onUp);
    };
  }, []);

  const handleDividerMouseDown = (e) => {
    dragState.current = { dragging: true, startX: e.clientX, startWidth: outputWidth };
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
    e.preventDefault();
  };

  // ALL HOOKS MUST BE ABOVE ANY EARLY RETURNS

  const handleWsMessage = useCallback((event) => {
    switch (event.type) {
      case 'tool_start':
        setOutputs(prev => [...prev, {
          id: event.task_id, type: 'start', tool: event.tool,
          parameters: event.parameters, source: event.source || 'manual',
          timestamp: event.timestamp,
        }]);
        break;
      case 'tool_result':
        setOutputs(prev => [...prev, {
          id: event.task_id, type: 'result', tool: event.tool,
          result: event.result, source: event.source || 'manual',
          timestamp: event.timestamp,
        }]);
        break;
      case 'new_finding':
        setFindings(prev => [...prev, event.finding]);
        break;
      case 'auto_step_pending':
        setPendingApproval({
          stepId: event.step_id, stepNumber: event.step_number,
          description: event.description, toolCalls: event.tool_calls,
        });
        break;
      case 'auto_step_decision':
        setPendingApproval(null);
        break;
      case 'auto_mode_changed':
      case 'auto_status':
        setOutputs(prev => [...prev, {
          id: `auto-${Date.now()}`, type: 'auto_status',
          message: event.message || (event.enabled ? 'Autonomous mode enabled' : 'Autonomous mode disabled'),
          timestamp: event.timestamp,
        }]);
        break;
      case 'presence_update':
        setOnlineUsers(event.users || []);
        break;
    }
  }, []);

  const { connected } = useWebSocket(activeSession?.id, handleWsMessage);

  // Check auth on mount
  useEffect(() => {
    if (isAuthenticated()) {
      api.getMe()
        .then(user => { setCurrentUser(user); setAuthChecked(true); })
        .catch(() => { setToken(null); setAuthChecked(true); });
    } else {
      setAuthChecked(true);
    }
  }, []);

  // Persist activeTab and activeSession to sessionStorage
  useEffect(() => { sessionStorage.setItem('activeTab', activeTab); }, [activeTab]);
  useEffect(() => { sessionStorage.setItem('activeSessionId', activeSession?.id || ''); }, [activeSession?.id]);

  // Load data after auth
  useEffect(() => {
    if (!currentUser) return;
    api.health().then(setHealth).catch(() => {});
    api.listSessions().then(data => {
      setSessions(data);
      if (restoredSessionId) {
        const match = data.find(s => s.id === restoredSessionId);
        if (match) setActiveSession(match);
        setRestoredSessionId(null);
      }
    }).catch(() => {});
    api.listTools().then(data => setTools(data.tools || {})).catch(() => {});
    api.getLogo().then(data => setLogoUrl(data.logo || null)).catch(() => {});
    api.listClients().then(setClients).catch(() => {});
  }, [currentUser]);

  // Load session details when active session changes
  useEffect(() => {
    if (!activeSession) return;
    api.getSession(activeSession.id).then(data => {
      setFindings(data.findings || []);
      if (data.messages && data.messages.length > 0) {
        setMessages(data.messages.map(m => ({
          role: m.role, content: m.content, timestamp: m.timestamp,
        })));
      }
      if (data.events && data.events.length > 0) {
        const restored = [];
        data.events.forEach(evt => {
          if (evt.type === 'tool_exec' || evt.type === 'bash_exec') {
            restored.push({
              id: evt.data.task_id, type: 'start',
              tool: evt.data.tool || 'bash',
              parameters: evt.data.parameters || { command: evt.data.command },
              source: evt.data.source || 'manual', timestamp: evt.timestamp,
            });
          } else if (evt.type === 'tool_result' || evt.type === 'bash_result') {
            restored.push({
              id: evt.data.task_id, type: 'result',
              tool: evt.data.tool || 'bash',
              result: { status: evt.data.status, output: evt.data.output || '', error: evt.data.error || '' },
              source: evt.data.source || 'manual', timestamp: evt.timestamp,
            });
          }
        });
        setOutputs(restored);
      }
    }).catch(() => {});
  }, [activeSession?.id]);

  // NOW safe to do early returns
  if (!authChecked) {
    return <div className="h-screen flex items-center justify-center bg-dark-950 text-gray-500">Loading...</div>;
  }
  if (!currentUser) {
    return <LoginScreen onLogin={(user) => { setAuthChecked(true); setCurrentUser(user); }} />;
  }

  const handleCreateSession = async (data) => {
    const session = await api.createSession(data);
    setSessions(prev => [...prev, session]);
    setActiveSession(session);
    setMessages([]); setOutputs([]); setFindings([]);
    setPendingApproval(null); setShowNewSession(false);
  };

  const handleSelectSession = (session) => {
    if (activeSession?.id === session.id) return;
    setActiveSession(session);
    setMessages([]); setOutputs([]); setFindings([]);
    setPendingApproval(null);
  };

  const handleDeleteSession = async (id) => {
    await api.deleteSession(id);
    setSessions(prev => prev.filter(s => s.id !== id));
    if (activeSession?.id === id) {
      setActiveSession(null); setMessages([]); setOutputs([]); setFindings([]);
    }
  };

  const handleEditSession = async (data) => {
    const updated = await api.updateSession(editingSession.id, data);
    setSessions(prev => prev.map(s => s.id === updated.id ? updated : s));
    if (activeSession?.id === updated.id) setActiveSession(updated);
    setEditingSession(null);
  };

  const handleSendChat = async (message) => {
    if (!activeSession) return;
    const abortController = new AbortController();
    chatAbortRef.current = abortController;
    setChatLoading(true);
    setMessages(prev => [...prev, { role: 'user', content: message, timestamp: new Date().toISOString() }]);
    try {
      const response = await api.chat({ message, session_id: activeSession.id }, abortController.signal);
      setMessages(prev => [...prev, {
        role: 'assistant', content: response.content,
        toolCalls: response.tool_calls, timestamp: new Date().toISOString(),
      }]);
    } catch (err) {
      if (err.name === 'AbortError') {
        setMessages(prev => [...prev, { role: 'error', content: 'Request cancelled.', timestamp: new Date().toISOString() }]);
      } else {
        setMessages(prev => [...prev, { role: 'error', content: `Error: ${err.message}`, timestamp: new Date().toISOString() }]);
      }
    } finally {
      chatAbortRef.current = null;
      setChatLoading(false);
    }
  };
  const handleCancelChat = () => {
    if (chatAbortRef.current) {
      chatAbortRef.current.abort();
    }
  };

  const handleExecuteTool = async (tool, parameters) => {
    if (!activeSession) return;
    try {
      await api.executeTool({ session_id: activeSession.id, tool, parameters });
    } catch (err) {
      setOutputs(prev => [...prev, {
        id: `err-${Date.now()}`, type: 'result', tool,
        result: { status: 'error', output: '', error: err.message },
        timestamp: new Date().toISOString(),
      }]);
    }
  };

  const handleExecuteBash = async (command) => {
    if (!activeSession) return;
    try {
      await api.executeBash({ session_id: activeSession.id, command });
    } catch (err) {
      setOutputs(prev => [...prev, {
        id: `err-${Date.now()}`, type: 'result', tool: 'bash',
        result: { status: 'error', output: '', error: err.message },
        timestamp: new Date().toISOString(),
      }]);
    }
  };

  const handleLogout = () => {
    setToken(null); setCurrentUser(null); setActiveSession(null);
    setMessages([]); setOutputs([]);
  };

  const tabs = [
    { id: 'chat', label: 'AI Chat' },
    { id: 'tools', label: 'Tools' },
    { id: 'findings', label: `Findings (${findings.length})` },
    { id: 'auto', label: 'Autonomous' },
    { id: 'scheduler', label: 'Scheduler' },
    { id: 'activitylog', label: 'Activity Log' },
    { id: 'clients', label: 'Clients' },
    { id: 'screenshots', label: 'Screenshots' },
    { id: 'files', label: 'Files' },
    { id: 'admin', label: currentUser.role === 'admin' ? 'Users' : 'Account' },
    { id: 'tooladmin', label: 'Tool Mgmt' },
    ...(currentUser.role === 'admin' ? [{ id: 'settings', label: 'Settings' }] : []),
  ];

  return (
    <div className="h-screen flex flex-col bg-dark-950">
      <Header health={health} connected={connected} session={activeSession} currentUser={currentUser} onLogout={handleLogout} logoUrl={logoUrl} onLogoClick={() => setActiveSession(null)} />
      <div className="flex-1 flex overflow-hidden">
        <SessionSidebar
          sessions={sessions} activeSession={activeSession}
          onSelect={handleSelectSession} onDelete={handleDeleteSession}
          onNew={() => setShowNewSession(true)}
          onEdit={(session) => setEditingSession(session)}
        />
        {activeSession || activeTab === 'admin' || activeTab === 'tooladmin' || activeTab === 'settings' || activeTab === 'clients' || activeTab === 'screenshots' || activeTab === 'files' ? (
          <div className="flex-1 flex flex-col overflow-hidden">
            <div className="flex border-b border-dark-600 bg-dark-900 overflow-x-auto">
              {tabs.map(tab => (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`px-5 py-2.5 text-sm font-medium transition-colors border-b-2 ${
                    activeTab === tab.id
                      ? 'border-accent-blue text-accent-blue'
                      : 'border-transparent text-gray-400 hover:text-gray-200'
                  }`}
                >
                  {tab.label}
                </button>
              ))}
            </div>
            <PresenceBar users={onlineUsers} />
            <div className="flex-1 flex overflow-hidden" ref={splitContainerRef}>
              <div className="overflow-hidden" style={{ flex: '1 1 0', minWidth: 0 }}>
                {activeTab === 'chat' && activeSession && (
                  <ChatPanel messages={messages} onSend={handleSendChat} loading={chatLoading} session={activeSession} onCancel={handleCancelChat} />
                )}
                {activeTab === 'tools' && activeSession && (
                  <ToolPanel tools={tools} onExecute={handleExecuteTool} onBash={handleExecuteBash} loading={toolLoading} />
                )}
                {activeTab === 'findings' && activeSession && (
                  <FindingsPanel findings={findings} />
                )}
                {activeTab === 'auto' && activeSession && (
                  <AutoPanel session={activeSession} pendingApproval={pendingApproval}
                    onStart={async (obj, steps) => { await api.startAutonomous({ session_id: activeSession.id, enabled: true, objective: obj, max_steps: steps }); }}
                    onStop={async () => { await api.stopAutonomous({ session_id: activeSession.id }); }}
                    onApprove={async (stepId, approved) => { await api.approveStep({ session_id: activeSession.id, step_id: stepId, approved }); setPendingApproval(null); }}
                  />
                )}
                {activeTab === 'scheduler' && activeSession && (
                  <SchedulerPanel session={activeSession} tools={tools} />
                )}
                {activeTab === 'activitylog' && activeSession && (
                  <ActivityLogPanel session={activeSession} />
                )}
                {activeTab === 'clients' && (
                  <ClientsPanel onClientsChange={setClients} />
                )}
                {activeTab === 'screenshots' && (
                  <ScreenshotGallery />
                )}
                {activeTab === 'files' && (
                  <FileManager />
                )}
                {activeTab === 'admin' && (
                  <AdminPanel currentUser={currentUser} />
                )}
                {activeTab === 'tooladmin' && (
                  <ToolsAdmin />
                )}
                {activeTab === 'settings' && (
                  <SettingsPanel logoUrl={logoUrl} onLogoChange={setLogoUrl} />
                )}
                {!activeSession && !['admin','tooladmin','settings','clients','screenshots','files'].includes(activeTab) && (
                  <div className="flex-1 flex items-center justify-center text-gray-500 h-full">
                    <p className="text-sm">Select an engagement to view this tab</p>
                  </div>
                )}
              </div>
              {!['admin','tooladmin','settings','clients','screenshots','files'].includes(activeTab) && (
                <>
                  <div
                    onMouseDown={handleDividerMouseDown}
                    className="w-1 shrink-0 bg-dark-600 hover:bg-accent-blue/60 active:bg-accent-blue cursor-col-resize transition-colors"
                    title="Drag to resize"
                  />
                  <div className="shrink-0 overflow-hidden" style={{ width: `${outputWidth}%` }}>
                    <OutputPanel outputs={outputs} onClear={() => setOutputs([])} />
                  </div>
                </>
              )}
            </div>
          </div>
        ) : (
          <HomePage
            sessions={sessions}
            currentUser={currentUser}
            logoUrl={logoUrl}
            onNewSession={() => setShowNewSession(true)}
            onSelectSession={handleSelectSession}
            onGoToAdmin={() => { setActiveSession(null); setActiveTab('admin'); }}
            onGoToSettings={() => { setActiveSession(null); setActiveTab('settings'); }}
          />
        )}
      </div>
      {showNewSession && (
        <NewSessionModal onClose={() => setShowNewSession(false)} onCreate={handleCreateSession} clients={clients} />
      )}
      {editingSession && (
        <EditSessionModal session={editingSession} onClose={() => setEditingSession(null)} onSave={handleEditSession} />
      )}
    </div>
  );
}
