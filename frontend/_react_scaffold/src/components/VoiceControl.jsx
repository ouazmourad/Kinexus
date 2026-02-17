import { useCallback, useState } from "react";
import useVoiceRecognition from "../hooks/useVoiceRecognition";

export default function VoiceControl({ onTranscript }) {
  const [transcripts, setTranscripts] = useState([]);

  const handleTranscript = useCallback(
    (text, confidence) => {
      setTranscripts((prev) => [
        { text, confidence, time: new Date().toLocaleTimeString() },
        ...prev.slice(0, 49),
      ]);
      onTranscript?.(text, confidence);
    },
    [onTranscript]
  );

  const { listening, supported, toggle } = useVoiceRecognition({
    onTranscript: handleTranscript,
  });

  return (
    <div className="bg-gray-900 rounded-xl p-4 border border-gray-800">
      <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-3">
        Voice Control
      </h2>

      <div className="flex items-center gap-4 mb-4">
        <button
          onClick={toggle}
          disabled={!supported}
          className={`relative flex items-center justify-center w-14 h-14 rounded-full transition-all ${
            listening
              ? "bg-red-600 hover:bg-red-700 mic-pulse"
              : "bg-brain-600 hover:bg-brain-700"
          } ${!supported ? "opacity-40 cursor-not-allowed" : "cursor-pointer"}`}
        >
          <MicIcon className="w-6 h-6 text-white" />
        </button>

        <div className="text-sm">
          {!supported ? (
            <span className="text-yellow-400">
              Speech recognition not supported in this browser
            </span>
          ) : listening ? (
            <span className="text-red-400">Listening...</span>
          ) : (
            <span className="text-gray-400">Click to start voice control</span>
          )}
        </div>
      </div>

      <div className="space-y-1 max-h-48 overflow-y-auto">
        {transcripts.length === 0 && (
          <p className="text-gray-600 text-sm italic">No transcripts yet</p>
        )}
        {transcripts.map((t, i) => (
          <div
            key={i}
            className="flex items-start gap-2 text-sm py-1 border-b border-gray-800/50"
          >
            <span className="text-gray-600 text-xs mt-0.5 shrink-0">
              {t.time}
            </span>
            <span className="text-gray-200">{t.text}</span>
            <span className="text-gray-600 text-xs mt-0.5 ml-auto shrink-0">
              {(t.confidence * 100).toFixed(0)}%
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function MicIcon({ className }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 1a3 3 0 00-3 3v8a3 3 0 006 0V4a3 3 0 00-3-3z" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M19 10v2a7 7 0 01-14 0v-2M12 19v4M8 23h8" />
    </svg>
  );
}
