export default function ActionLog({ entries }) {
  return (
    <div className="bg-gray-900 rounded-xl p-4 border border-gray-800">
      <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-3">
        Action Log
      </h2>
      <div className="space-y-1 max-h-64 overflow-y-auto font-mono text-xs">
        {entries.length === 0 && (
          <p className="text-gray-600 italic text-sm font-sans">
            No actions yet
          </p>
        )}
        {entries.map((entry, i) => (
          <div
            key={i}
            className="flex items-center gap-2 py-1 border-b border-gray-800/50"
          >
            <ActionBadge action={entry.action} />
            <span className="text-gray-400">
              {entry.command_type === "automated" && entry.robot_id
                ? `${entry.robot_id} `
                : ""}
            </span>
            <span className="text-gray-500 ml-auto text-[10px]">
              {entry.source || "voice"}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

const ACTION_COLORS = {
  FORWARD: "bg-green-900/60 text-green-300",
  LEFT: "bg-blue-900/60 text-blue-300",
  RIGHT: "bg-purple-900/60 text-purple-300",
  STOP: "bg-red-900/60 text-red-300",
  EMERGENCY_STOP: "bg-red-800 text-red-200",
  STOP_ALL: "bg-red-800 text-red-200",
  GRAB: "bg-yellow-900/60 text-yellow-300",
  RELEASE: "bg-yellow-900/60 text-yellow-300",
  NAVIGATE: "bg-cyan-900/60 text-cyan-300",
  TRANSPORT: "bg-orange-900/60 text-orange-300",
};

function ActionBadge({ action }) {
  const color = ACTION_COLORS[action] || "bg-gray-800 text-gray-300";
  return (
    <span className={`px-2 py-0.5 rounded text-[11px] font-medium ${color}`}>
      {action}
    </span>
  );
}
