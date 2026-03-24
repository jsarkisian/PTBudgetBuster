import { useState } from "react";
import { ArrowLeft, Play, Clock, ChevronDown, ChevronUp, Plus, X } from "lucide-react";
import { createEngagement, startEngagement } from "../utils/api";

const DEFAULT_KEY_NAMES = ["subfinder", "shodan", "censys_id", "censys_secret", "virustotal", "securitytrails"];

export default function EngagementSetup({ navigate }) {
  const [name, setName] = useState("");
  const [targetScope, setTargetScope] = useState("");
  const [scheduledAt, setScheduledAt] = useState("");
  const [notes, setNotes] = useState("");
  const [apiKeysOpen, setApiKeysOpen] = useState(false);
  const [apiKeys, setApiKeys] = useState([]);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const addApiKey = (keyName = "") => {
    setApiKeys((prev) => [...prev, { key: keyName, value: "" }]);
  };

  const removeApiKey = (index) => {
    setApiKeys((prev) => prev.filter((_, i) => i !== index));
  };

  const updateApiKey = (index, field, value) => {
    setApiKeys((prev) =>
      prev.map((item, i) => (i === index ? { ...item, [field]: value } : item))
    );
  };

  const buildPayload = () => {
    const scope = targetScope
      .split("\n")
      .map((s) => s.trim())
      .filter(Boolean);

    const toolApiKeys = {};
    apiKeys.forEach(({ key, value }) => {
      if (key.trim() && value.trim()) toolApiKeys[key.trim()] = value.trim();
    });

    return {
      name: name.trim(),
      target_scope: scope,
      notes: notes.trim() || undefined,
      tool_api_keys: Object.keys(toolApiKeys).length > 0 ? toolApiKeys : undefined,
    };
  };

  const handleStartNow = async () => {
    if (!name.trim() || !targetScope.trim()) {
      setError("Name and target scope are required.");
      return;
    }
    setError("");
    setSubmitting(true);
    try {
      const payload = buildPayload();
      const eng = await createEngagement(payload);
      await startEngagement(eng.id);
      navigate("live", eng.id);
    } catch (err) {
      setError(err.message || "Failed to create engagement");
    } finally {
      setSubmitting(false);
    }
  };

  const handleSchedule = async () => {
    if (!name.trim() || !targetScope.trim()) {
      setError("Name and target scope are required.");
      return;
    }
    if (!scheduledAt) {
      setError("Scheduled time is required when scheduling.");
      return;
    }
    setError("");
    setSubmitting(true);
    try {
      const payload = buildPayload();
      payload.scheduled_at = new Date(scheduledAt).toISOString();
      await createEngagement(payload);
      navigate("dashboard");
    } catch (err) {
      setError(err.message || "Failed to schedule engagement");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="max-w-3xl mx-auto p-6">
      <button
        onClick={() => navigate("dashboard")}
        className="flex items-center gap-1.5 text-sm text-gray-400 hover:text-gray-200 mb-6 transition-colors"
      >
        <ArrowLeft className="w-4 h-4" />
        Back to Dashboard
      </button>

      <h2 className="text-xl font-bold text-gray-100 mb-6">New Engagement</h2>

      {error && (
        <div className="bg-red-900/30 border border-red-700 text-red-400 text-sm rounded px-4 py-3 mb-4">
          {error}
        </div>
      )}

      <div className="bg-gray-900 rounded-lg border border-gray-800 p-6 space-y-5">
        {/* Name */}
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-1">
            Engagement Name <span className="text-red-400">*</span>
          </label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Acme Corp External Assessment"
            className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-gray-100 focus:outline-none focus:border-blue-500 placeholder-gray-600"
          />
        </div>

        {/* Target Scope */}
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-1">
            Target Scope <span className="text-red-400">*</span>
          </label>
          <textarea
            value={targetScope}
            onChange={(e) => setTargetScope(e.target.value)}
            placeholder={"example.com\n10.0.0.0/24\napi.example.com"}
            rows={5}
            className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-gray-100 focus:outline-none focus:border-blue-500 placeholder-gray-600 font-mono text-sm"
          />
          <p className="text-xs text-gray-500 mt-1">One target per line (domains, IPs, CIDR ranges)</p>
        </div>

        {/* Schedule Time */}
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-1">
            Schedule Time <span className="text-gray-500">(optional)</span>
          </label>
          <input
            type="datetime-local"
            value={scheduledAt}
            onChange={(e) => setScheduledAt(e.target.value)}
            className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-gray-100 focus:outline-none focus:border-blue-500"
          />
        </div>

        {/* Tool API Keys */}
        <div>
          <button
            type="button"
            onClick={() => setApiKeysOpen(!apiKeysOpen)}
            className="flex items-center gap-2 text-sm font-medium text-gray-300 hover:text-gray-100 transition-colors"
          >
            {apiKeysOpen ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
            Tool API Keys
            {apiKeys.length > 0 && (
              <span className="text-xs bg-gray-700 px-2 py-0.5 rounded-full text-gray-300">
                {apiKeys.length}
              </span>
            )}
          </button>

          {apiKeysOpen && (
            <div className="mt-3 space-y-2">
              {apiKeys.map((item, i) => (
                <div key={i} className="flex items-center gap-2">
                  <input
                    type="text"
                    value={item.key}
                    onChange={(e) => updateApiKey(i, "key", e.target.value)}
                    placeholder="Key name"
                    className="w-1/3 bg-gray-800 border border-gray-700 rounded px-3 py-1.5 text-sm text-gray-100 focus:outline-none focus:border-blue-500 placeholder-gray-600"
                  />
                  <input
                    type="password"
                    value={item.value}
                    onChange={(e) => updateApiKey(i, "value", e.target.value)}
                    placeholder="API key value"
                    className="flex-1 bg-gray-800 border border-gray-700 rounded px-3 py-1.5 text-sm text-gray-100 focus:outline-none focus:border-blue-500 placeholder-gray-600 font-mono"
                  />
                  <button
                    onClick={() => removeApiKey(i)}
                    className="p-1.5 text-gray-500 hover:text-red-400 transition-colors"
                  >
                    <X className="w-4 h-4" />
                  </button>
                </div>
              ))}

              <div className="flex items-center gap-2 flex-wrap">
                <button
                  onClick={() => addApiKey("")}
                  className="flex items-center gap-1 text-xs text-blue-400 hover:text-blue-300 transition-colors"
                >
                  <Plus className="w-3 h-3" />
                  Add custom key
                </button>
                <span className="text-gray-600 text-xs">|</span>
                {DEFAULT_KEY_NAMES.filter((k) => !apiKeys.some((a) => a.key === k)).map((k) => (
                  <button
                    key={k}
                    onClick={() => addApiKey(k)}
                    className="text-xs bg-gray-800 hover:bg-gray-700 text-gray-400 hover:text-gray-200 px-2 py-0.5 rounded transition-colors"
                  >
                    + {k}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Notes */}
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-1">
            Notes <span className="text-gray-500">(optional)</span>
          </label>
          <textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="Additional context, rules of engagement, etc."
            rows={3}
            className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-gray-100 focus:outline-none focus:border-blue-500 placeholder-gray-600 text-sm"
          />
        </div>
      </div>

      {/* Actions */}
      <div className="flex items-center gap-3 mt-6">
        <button
          onClick={handleStartNow}
          disabled={submitting}
          className="flex items-center gap-2 bg-blue-600 hover:bg-blue-500 disabled:bg-blue-800 disabled:text-gray-400 text-white px-5 py-2.5 rounded-lg font-medium transition-colors"
        >
          <Play className="w-4 h-4" />
          {submitting ? "Creating..." : "Start Now"}
        </button>
        <button
          onClick={handleSchedule}
          disabled={submitting}
          className="flex items-center gap-2 bg-gray-700 hover:bg-gray-600 disabled:bg-gray-800 disabled:text-gray-500 text-gray-200 px-5 py-2.5 rounded-lg font-medium transition-colors"
        >
          <Clock className="w-4 h-4" />
          Schedule
        </button>
      </div>
    </div>
  );
}
