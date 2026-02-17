export default function ControlPad({ onAction }) {
  return (
    <div className="bg-gray-900 rounded-xl p-4 border border-gray-800">
      <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-3">
        Manual Control
      </h2>
      <div className="grid grid-cols-3 gap-2 w-fit mx-auto">
        <div />
        <DPadButton label="FWD" action="FORWARD" onAction={onAction} />
        <div />
        <DPadButton label="LEFT" action="LEFT" onAction={onAction} />
        <DPadButton label="STOP" action="STOP" onAction={onAction} variant="danger" />
        <DPadButton label="RIGHT" action="RIGHT" onAction={onAction} />
      </div>
    </div>
  );
}

function DPadButton({ label, action, onAction, variant }) {
  const base =
    variant === "danger"
      ? "bg-red-900/60 hover:bg-red-800 text-red-300 border-red-800"
      : "bg-gray-800 hover:bg-gray-700 text-gray-300 border-gray-700";

  return (
    <button
      onClick={() => onAction(action)}
      className={`w-16 h-12 rounded-lg border text-xs font-semibold transition-colors ${base}`}
    >
      {label}
    </button>
  );
}
