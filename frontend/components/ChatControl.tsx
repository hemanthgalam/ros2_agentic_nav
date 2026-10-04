"use client";

import { FormEvent, useState } from "react";

import type { PendingAction } from "@/hooks/useGeminiMission";
import type { ChatMessage } from "@/hooks/useGeminiMission";

interface ChatControlProps {
  messages: ChatMessage[];
  pendingAction: PendingAction | null;
  sending: boolean;
  error: string | null;
  onSend: (text: string) => void;
  onConfirm: (approve: boolean) => void;
}

function describeAction(action: PendingAction): string {
  switch (action.action_type) {
    case "navigate_to_gps":
      return `Navigate to (${action.lat?.toFixed(6)}, ${action.lon?.toFixed(6)})`;
    case "navigate_to_named_place":
      return action.lat != null
        ? `Navigate to "${action.place_name}" (${action.lat.toFixed(6)}, ${action.lon?.toFixed(6)})`
        : `Navigate to "${action.place_name}" (unknown place — cannot execute)`;
    case "stop_robot":
      return "Stop the robot / cancel current goal";
    default:
      return "Unknown action";
  }
}

export default function ChatControl({
  messages,
  pendingAction,
  sending,
  error,
  onSend,
  onConfirm,
}: ChatControlProps) {
  const [draft, setDraft] = useState("");

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!draft.trim() || sending) return;
    onSend(draft.trim());
    setDraft("");
  };

  return (
    <div className="flex h-full flex-col bg-panel text-sm text-slate-100">
      <div className="flex-1 space-y-3 overflow-y-auto p-4">
        {messages.length === 0 && (
          <p className="text-slate-400">
            Ask SpatialPilot to move the robot, e.g. &ldquo;go to the loading dock&rdquo; or
            &ldquo;navigate to 37.4276, -122.1698&rdquo;.
          </p>
        )}
        {messages.map((m, i) => (
          <div
            key={i}
            className={`rounded-lg px-3 py-2 ${
              m.role === "user" ? "ml-8 bg-accent/20 text-right" : "mr-8 bg-slate-800"
            }`}
          >
            {m.text}
          </div>
        ))}
        {error && <p className="rounded-lg bg-red-900/40 px-3 py-2 text-red-200">{error}</p>}
      </div>

      {pendingAction && (
        <div className="border-t border-slate-700 bg-amber-950/40 p-4">
          <p className="mb-1 font-semibold text-amber-300">Approval required</p>
          <p className="mb-3 text-slate-200">{describeAction(pendingAction)}</p>
          {pendingAction.rationale && (
            <p className="mb-3 text-xs text-slate-400">{pendingAction.rationale}</p>
          )}
          <div className="flex gap-2">
            <button
              onClick={() => onConfirm(true)}
              className="flex-1 rounded bg-emerald-600 px-3 py-2 font-medium hover:bg-emerald-500"
            >
              Approve
            </button>
            <button
              onClick={() => onConfirm(false)}
              className="flex-1 rounded bg-slate-700 px-3 py-2 font-medium hover:bg-slate-600"
            >
              Reject
            </button>
          </div>
        </div>
      )}

      <form onSubmit={submit} className="flex gap-2 border-t border-slate-700 p-3">
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Type a command..."
          className="flex-1 rounded bg-slate-800 px-3 py-2 outline-none focus:ring-1 focus:ring-accent"
        />
        <button
          type="submit"
          disabled={sending}
          className="rounded bg-accent px-4 py-2 font-medium text-slate-900 disabled:opacity-50"
        >
          {sending ? "..." : "Send"}
        </button>
      </form>
    </div>
  );
}
