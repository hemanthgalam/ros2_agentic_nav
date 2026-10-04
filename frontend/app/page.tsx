"use client";

import { useState } from "react";

import ChatControl from "@/components/ChatControl";
import DatumConfigModal from "@/components/DatumConfigModal";
import MapViewer from "@/components/MapViewer";
import { useGeminiMission } from "@/hooks/useGeminiMission";
import { useRosBridge } from "@/hooks/useRosBridge";

export default function Home() {
  const { connected, map, odom, datum, trajectory } = useRosBridge();
  const mission = useGeminiMission();

  const [calibrating, setCalibrating] = useState(false);
  const [pickedPoint, setPickedPoint] = useState<{ lat: number; lon: number } | null>(null);

  return (
    <main className="flex h-screen w-screen">
      <div className="relative flex-1">
        <MapViewer
          map={map}
          odom={odom}
          datum={datum}
          trajectory={trajectory}
          calibrating={calibrating}
          onCalibratePick={(lat, lon) => setPickedPoint({ lat, lon })}
        />
        <DatumConfigModal
          datum={datum}
          calibrating={calibrating}
          pickedPoint={pickedPoint}
          onStartCalibrating={() => {
            setPickedPoint(null);
            setCalibrating(true);
          }}
          onCancel={() => {
            setCalibrating(false);
            setPickedPoint(null);
          }}
          onSaved={() => {
            setCalibrating(false);
            setPickedPoint(null);
          }}
        />
        <div className="absolute right-3 top-3 z-10 rounded bg-slate-900/80 px-3 py-2 text-xs font-medium shadow">
          rosbridge:{" "}
          <span className={connected ? "text-emerald-400" : "text-red-400"}>
            {connected ? "connected" : "disconnected"}
          </span>
        </div>
      </div>
      <aside className="w-96 border-l border-slate-800">
        <ChatControl
          messages={mission.messages}
          pendingAction={mission.pendingAction}
          sending={mission.sending}
          error={mission.error}
          onSend={mission.sendMessage}
          onConfirm={mission.confirmPending}
        />
      </aside>
    </main>
  );
}
