import { useState, useCallback } from "react";
import useWebSocket from "./hooks/useWebSocket";
import StatusPanel from "./components/StatusPanel";
import VoiceControl from "./components/VoiceControl";
import ActionLog from "./components/ActionLog";
import ControlPad from "./components/ControlPad";

export default function App() {
  const { connected, lastMessage, sendTranscript, sendAction } = useWebSocket();
  const [actionLog, setActionLog] = useState([]);
  const [status, setStatus] = useState({ simRunning: false, ttsEnabled: false });

  // Process incoming WebSocket messages
  const prevMsgRef = { current: null };
  if (lastMessage && lastMessage !== prevMsgRef.current) {
    prevMsgRef.current = lastMessage;

    if (lastMessage.type === "voice_command_parsed") {
      setActionLog((prev) => [
        {
          action: lastMessage.action,
          command_type: lastMessage.command_type,
          robot_id: lastMessage.robot_id,
          target: lastMessage.target,
          source: "voice",
        },
        ...prev.slice(0, 99),
      ]);
    } else if (lastMessage.type === "action_executed") {
      setActionLog((prev) => [
        { action: lastMessage.action, source: "manual" },
        ...prev.slice(0, 99),
      ]);
    }
  }

  const handleTranscript = useCallback(
    (text, confidence) => {
      sendTranscript(text, confidence);
    },
    [sendTranscript]
  );

  const handleAction = useCallback(
    (action) => {
      sendAction(action);
      setActionLog((prev) => [
        { action, source: "manual" },
        ...prev.slice(0, 99),
      ]);
    },
    [sendAction]
  );

  // Fetch status periodically
  useState(() => {
    const fetchStatus = async () => {
      try {
        const res = await fetch("/api/status");
        if (res.ok) {
          const data = await res.json();
          setStatus({
            simRunning: data.simulation?.running ?? false,
            ttsEnabled: data.voice?.tts_enabled ?? false,
          });
        }
      } catch {}
    };
    fetchStatus();
    const interval = setInterval(fetchStatus, 5000);
    return () => clearInterval(interval);
  });

  return (
    <div className="min-h-screen bg-gray-950 p-4 md:p-8">
      {/* Header */}
      <header className="mb-6">
        <h1 className="text-2xl font-bold text-white tracking-tight">
          ThoughtLink
        </h1>
        <p className="text-sm text-gray-500">
          Brain-to-Robot Control Dashboard
        </p>
      </header>

      {/* Status bar */}
      <div className="mb-6">
        <StatusPanel
          connected={connected}
          simRunning={status.simRunning}
          ttsEnabled={status.ttsEnabled}
        />
      </div>

      {/* Main grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left column — voice + controls */}
        <div className="lg:col-span-2 space-y-6">
          <VoiceControl onTranscript={handleTranscript} />
          <ControlPad onAction={handleAction} />
        </div>

        {/* Right column — action log */}
        <div>
          <ActionLog entries={actionLog} />
        </div>
      </div>
    </div>
  );
}
