import React, { useState, useCallback, useEffect } from 'react';
import { api } from './utils/api';
import { useWebSocket } from './hooks/useWebSocket';
import Header from './components/Header';
import SessionSidebar from './components/SessionSidebar';
import ChatPanel from './components/ChatPanel';
import OutputPanel from './components/OutputPanel';
import ToolPanel from './components/ToolPanel';
import FindingsPanel from './components/FindingsPanel';
import AutoPanel from './components/AutoPanel';
import NewSessionModal from './components/NewSessionModal';

export default function App() {
  const [sessions, setSessions] = useState([]);
  const [activeSession, setActiveSession] = useState(null);
  const [activeTab, setActiveTab] = useState('chat'); // chat | tools | findings | auto
  const [messages, setMessages] = useState([]);
  const [outputs, setOutputs] = useState([]);
  const [findings, setFindings] = useState([]);
  const [tools, setTools] = useState({});
  const [pendingApproval, setPendingApproval] = useState(null);
  const [showNewSession, setShowNewSession] = useState(false);
  const [health, setHealth] = useState(null);
  const [chatLoading, setChatLoading] = useState(false);
  const [toolLoading, setToolLoading] = useState(false);

  // WebSocket handler
  const handleWsMessage = useCallback((event) => {
    switch (event.type) {
      case 'chat_message':
        setMessages(prev => [...prev, {
          role: event.role,
          content: event.content,
          toolCalls: event.tool_calls,
          timestamp: event.timestamp,
        }]);
        break;

      case 'tool_start':
        setOutputs(prev => [...prev, {
          id: event.task_id,
          type: 'start',
          tool: event.tool,
          parameters: event.parameters,
          source: event.source || 'manual',
          timestamp: event.timestamp,
        }]);
        break;

      case 'tool_result':
        setOutputs(prev => [...prev, {
          id: event.task_id,
          type: 'result',
          tool: event.tool,
          result: event.result,
          source: event.source || 'manual',
          timestamp: event.timestamp,
        }]);
        break;

      case 'new_finding':
        setFindings(prev => [...prev, event.finding]);
        break;

      case 'auto_step_pending':
        setPendingApproval({
          stepId: event.step_id,
          stepNumber: event.step_number,
          description: event.description,
          toolCalls: event.tool_calls,
        });
        break;

      case 'auto_step_decision':
        setPendingApproval(null);
        break;

      case 'auto_mode_changed':
      case 'auto_status':
        setOutputs(prev => [...prev, {
          id: `auto-${Date.now()}`,
          type: 'auto_status',
          message: event.message || (event.enabled ? 'Autonomous mode enabled' : 'Autonomous mode disabled'),
          timestamp: event.timestamp,
        }]);
        break;
    }
  }, []);

  const { connected } = useWebSocket(activeSession?.id, handleWsMessage);

  // Load sessions and tools on mount
  useEffect(() => {
    api.health().then(setHealth).catch(() => {});
    api.listSessions().then(setSessions).catch(() => {});
    api.listTools().then(data => setTools(data.tools || {})).catch(() => {});
  }, []);

  // Load session details when active session changes
  useEffect(() => {
    if (activeSession) {
      api.getSession(activeSession.id).then(data => {
        setFindings(data.findings || []);
      }).catch(() => {});
    }
  }, [activeSession?.id]);

  const handleCreateSession = async (data) => {
    const session = await api.createSession(data);
    setSessions(prev => [...prev, session]);
    setActiveSession(session);
    setMessages([]);
    setOutputs([]);
    setFindings([]);
    setPendingApproval(null);
    setShowNewSession(false);
  };

  const handleSelectSession = (session) => {
    setActiveSession(session);
    setMessages([]);
    setOutputs([]);
    setFindings(session.findings || []);
    setPendingApproval(null);
  };

  const handleDeleteSession = async (id) => {
    await api.deleteSession(id);
    setSessions(prev => prev.filter(s => s.id !== id));
    if (activeSession?.id === id) {
      setActiveSession(null);
      setMessages([]);
      setOutputs([]);
      setFindings([]);
    }
  };

  const handleSendChat = async (message) => {
    if (!activeSession) return;
    setChatLoading(true);
    try {
      // Optimistic add
      setMessages(prev => [...prev, { role: 'user', content: message, timestamp: new Date().toISOString() }]);
      const response = await api.chat({ message, session_id: activeSession.id });
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: response.content,
        toolCalls: response.tool_calls,
        timestamp: new Date().toISOString(),
      }]);
    } catch (err) {
      setMessages(prev => [...prev, {
        role: 'error',
        content: `Error: ${err.message}`,
        timestamp: new Date().toISOString(),
      }]);
    } finally {
      setChatLoading(false);
    }
  };

  const handleExecuteTool = async (tool, parameters) => {
    if (!activeSession) return;
    setToolLoading(true);
    try {
      const result = await api.executeTool({
        session_id: activeSession.id,
        tool,
        parameters,
      });
      return result;
    } finally {
      setToolLoading(false);
    }
  };

  const handleExecuteBash = async (command) => {
    if (!activeSession) return;
    setToolLoading(true);
    try {
      return await api.executeBash({ session_id: activeSession.id, command });
    } finally {
      setToolLoading(false);
    }
  };

  const handleApprove = async (stepId, approved) => {
    if (!activeSession) return;
    await api.approveStep({
      session_id: activeSession.id,
      step_id: stepId,
      approved,
    });
    setPendingApproval(null);
  };

  const handleStartAuto = async (objective, maxSteps) => {
    if (!activeSession) return;
    await api.startAutonomous({
      session_id: activeSession.id,
      enabled: true,
      objective,
      max_steps: maxSteps,
    });
  };

  const handleStopAuto = async () => {
    if (!activeSession) return;
    await api.stopAutonomous({ session_id: activeSession.id });
  };

  return (
    <div className="h-screen flex flex-col bg-dark-950">
      <Header health={health} connected={connected} session={activeSession} />

      <div className="flex-1 flex overflow-hidden">
        {/* Sidebar */}
        <SessionSidebar
          sessions={sessions}
          activeSession={activeSession}
          onSelect={handleSelectSession}
          onDelete={handleDeleteSession}
          onNew={() => setShowNewSession(true)}
        />

        {/* Main content */}
        {activeSession ? (
          <div className="flex-1 flex flex-col overflow-hidden">
            {/* Tabs */}
            <div className="flex border-b border-dark-600 bg-dark-900">
              {[
                { id: 'chat', label: 'AI Chat' },
                { id: 'tools', label: 'Tools' },
                { id: 'findings', label: `Findings (${findings.length})` },
                { id: 'auto', label: 'Autonomous' },
              ].map(tab => (
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

            {/* Tab content + output split */}
            <div className="flex-1 flex overflow-hidden">
              {/* Left: active panel */}
              <div className="flex-1 overflow-hidden">
                {activeTab === 'chat' && (
                  <ChatPanel
                    messages={messages}
                    onSend={handleSendChat}
                    loading={chatLoading}
                    session={activeSession}
                  />
                )}
                {activeTab === 'tools' && (
                  <ToolPanel
                    tools={tools}
                    onExecute={handleExecuteTool}
                    onBash={handleExecuteBash}
                    loading={toolLoading}
                  />
                )}
                {activeTab === 'findings' && (
                  <FindingsPanel findings={findings} />
                )}
                {activeTab === 'auto' && (
                  <AutoPanel
                    session={activeSession}
                    pendingApproval={pendingApproval}
                    onStart={handleStartAuto}
                    onStop={handleStopAuto}
                    onApprove={handleApprove}
                  />
                )}
              </div>

              {/* Right: output panel */}
              <div className="w-[45%] border-l border-dark-600">
                <OutputPanel outputs={outputs} onClear={() => setOutputs([])} />
              </div>
            </div>
          </div>
        ) : (
          <div className="flex-1 flex items-center justify-center text-gray-500">
            <div className="text-center">
              <div className="text-6xl mb-4">🛡️</div>
              <h2 className="text-xl font-semibold text-gray-300 mb-2">PentestMCP</h2>
              <p className="mb-4">Create or select an engagement to begin testing</p>
              <button onClick={() => setShowNewSession(true)} className="btn-primary">
                New Engagement
              </button>
            </div>
          </div>
        )}
      </div>

      {showNewSession && (
        <NewSessionModal
          onClose={() => setShowNewSession(false)}
          onCreate={handleCreateSession}
        />
      )}
    </div>
  );
}
