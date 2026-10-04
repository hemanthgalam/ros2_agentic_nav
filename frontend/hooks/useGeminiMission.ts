"use client";

import { useCallback, useState } from "react";

export interface ChatMessage {
  role: "user" | "model";
  text: string;
}

export interface PendingAction {
  action_id: string;
  action_type: "navigate_to_gps" | "navigate_to_named_place" | "stop_robot";
  lat: number | null;
  lon: number | null;
  place_name: string | null;
  rationale: string;
}

interface MissionState {
  messages: ChatMessage[];
  pendingAction: PendingAction | null;
  sending: boolean;
  error: string | null;
  sendMessage: (text: string) => Promise<void>;
  confirmPending: (approve: boolean) => Promise<void>;
}

export function useGeminiMission(): MissionState {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [pendingAction, setPendingAction] = useState<PendingAction | null>(null);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const sendMessage = useCallback(
    async (text: string) => {
      setSending(true);
      setError(null);
      const nextHistory = [...messages, { role: "user" as const, text }];
      setMessages(nextHistory);

      try {
        const res = await fetch("/api/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ message: text, history: messages }),
        });
        if (!res.ok) throw new Error(`Backend returned ${res.status}`);
        const data = await res.json();
        setMessages([...nextHistory, { role: "model", text: data.reply }]);
        setPendingAction(data.pending_action ?? null);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to reach the backend");
      } finally {
        setSending(false);
      }
    },
    [messages],
  );

  const confirmPending = useCallback(
    async (approve: boolean) => {
      if (!pendingAction) return;
      setError(null);
      try {
        const res = await fetch("/api/actions/confirm", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ action_id: pendingAction.action_id, approve }),
        });
        const data = await res.json();
        setMessages((prev) => [
          ...prev,
          {
            role: "model",
            text: data.detail ?? (approve ? "Action approved." : "Action rejected."),
          },
        ]);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to confirm action");
      } finally {
        setPendingAction(null);
      }
    },
    [pendingAction],
  );

  return { messages, pendingAction, sending, error, sendMessage, confirmPending };
}
