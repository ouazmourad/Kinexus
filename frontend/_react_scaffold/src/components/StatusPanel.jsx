export default function StatusPanel({ connected, simRunning, ttsEnabled }) {
  return (
    <div className="bg-gray-900 rounded-xl p-4 border border-gray-800">
      <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-3">
        System Status
      </h2>
      <div className="flex gap-4">
        <StatusDot label="Backend" active={connected} />
        <StatusDot label="Simulation" active={simRunning} />
        <StatusDot label="TTS" active={ttsEnabled} />
      </div>
    </div>
  );
}

function StatusDot({ label, active }) {
  return (
    <div className="flex items-center gap-2">
      <span
        className={`h-2.5 w-2.5 rounded-full ${
          active ? "bg-green-400 shadow-[0_0_6px_rgba(74,222,128,0.6)]" : "bg-gray-600"
        }`}
      />
      <span className="text-sm text-gray-300">{label}</span>
    </div>
  );
}
