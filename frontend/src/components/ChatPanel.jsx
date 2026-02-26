import React, { useState, useRef, useEffect } from 'react';

export default function ChatPanel({ messages, onSend, loading, session, onCancel, streamingMessage }) {
  const [input, setInput] = useState('');
  const messagesEnd = useRef(null);

  useEffect(() => {
    messagesEnd.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, streamingMessage]);

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!input.trim() || loading) return;
    onSend(input.trim());
    setInput('');
  };

  return (
    <div className="h-full flex flex-col">
      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {/* Welcome message */}
        {messages.length === 0 && (
          <div className="text-center py-8">
            <div className="text-4xl mb-3">🤖</div>
            <h3 className="text-lg font-semibold text-gray-300 mb-2">AI Pentest Assistant</h3>
            <p className="text-sm text-gray-500 max-w-md mx-auto mb-4">
              I can help you plan and execute your penetration test. I have access to security
              tools and can analyze results. Tell me about your targets or ask me to start reconnaissance.
            </p>
            <div className="flex flex-wrap gap-2 justify-center">
              {[
                `Enumerate subdomains for ${session?.target_scope?.[0] || 'example.com'}`,
                'What tools are available?',
                'Help me plan a full external pentest',
                'Scan for common vulnerabilities',
              ].map(suggestion => (
                <button
                  key={suggestion}
                  onClick={() => onSend(suggestion)}
                  className="text-xs px-3 py-1.5 bg-dark-700 hover:bg-dark-600 text-gray-300 rounded-full transition-colors"
                >
                  {suggestion}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg, i) => (
          <MessageBubble key={i} message={msg} />
        ))}

        {/* Streaming message from WebSocket */}
        {streamingMessage && streamingMessage.content && (
          <div className="flex justify-start">
            <div className="max-w-[85%] rounded-lg px-4 py-3 text-sm leading-relaxed bg-dark-800 text-gray-200 border border-dark-600">
              <div className="text-xs font-medium mb-1 text-accent-cyan">AI Assistant</div>
              <div className="whitespace-pre-wrap">
                {streamingMessage.content}
                {streamingMessage.streaming && (
                  <span className="inline-block w-2 h-4 bg-accent-cyan/70 ml-0.5 animate-pulse" />
                )}
              </div>
            </div>
          </div>
        )}

        {loading && !streamingMessage?.content && (
          <div className="flex items-center gap-3 text-gray-400 text-sm">
            <div className="flex gap-1">
              <span className="w-2 h-2 bg-accent-blue rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
              <span className="w-2 h-2 bg-accent-blue rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
              <span className="w-2 h-2 bg-accent-blue rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
            </div>
            Thinking...
            <button
              onClick={onCancel}
              className="ml-2 px-3 py-1 text-xs bg-red-600 hover:bg-red-500 text-white rounded transition-colors"
            >
              ■ Stop
            </button>
          </div>
        )}

        {loading && streamingMessage?.content && (
          <div className="flex items-center gap-2 text-gray-500 text-xs">
            <button
              onClick={onCancel}
              className="px-3 py-1 text-xs bg-red-600 hover:bg-red-500 text-white rounded transition-colors"
            >
              ■ Stop
            </button>
          </div>
        )}
        <div ref={messagesEnd} />
      </div>

      {/* Input */}
      <form onSubmit={handleSubmit} className="p-3 border-t border-dark-600 bg-dark-900">
        <div className="flex gap-2 mb-1.5">
          <span className="text-xs text-gray-500">
            Wrap sensitive values to keep them from Claude:{' '}
            <code className="bg-dark-700 text-accent-cyan px-1 rounded">[[password123]]</code>
          </span>
        </div>
        <div className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask the AI or give a command..."
            className="input flex-1"
            disabled={loading}
          />
          {loading ? (
            <button
              type="button"
              onClick={onCancel}
              className="px-4 py-2 text-sm bg-red-600 hover:bg-red-500 text-white rounded transition-colors"
            >
              ■ Stop
            </button>
          ) : (
            <button
              type="submit"
              disabled={!input.trim()}
              className="btn-primary px-4"
            >
              Send
            </button>
          )}
        </div>
      </form>
    </div>
  );
}

function MessageBubble({ message }) {
  const isUser = message.role === 'user';
  const isError = message.role === 'error';

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-[85%] rounded-lg px-4 py-3 text-sm leading-relaxed ${
          isUser
            ? 'bg-accent-blue/20 text-gray-100 border border-accent-blue/30'
            : isError
            ? 'bg-red-500/10 text-red-400 border border-red-500/20'
            : 'bg-dark-800 text-gray-200 border border-dark-600'
        }`}
      >
        {/* Role indicator */}
        <div className={`text-xs font-medium mb-1 ${
          isUser ? 'text-accent-blue' : isError ? 'text-red-400' : 'text-accent-cyan'
        }`}>
          {isUser ? 'You' : isError ? 'Error' : 'AI Assistant'}
        </div>

        {/* Content */}
        <div className="whitespace-pre-wrap">{message.content}</div>

        {/* Tool calls */}
        {message.toolCalls?.length > 0 && (
          <div className="mt-2 pt-2 border-t border-dark-600 space-y-1">
            <div className="text-xs text-gray-400 font-medium">Tools executed:</div>
            {message.toolCalls.map((tc, i) => (
              <div key={i} className="text-xs bg-dark-700 rounded px-2 py-1">
                <span className="text-accent-green font-mono">{tc.tool}</span>
                {tc.input?.tool && (
                  <span className="text-gray-400 ml-1">→ {tc.input.tool}</span>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
