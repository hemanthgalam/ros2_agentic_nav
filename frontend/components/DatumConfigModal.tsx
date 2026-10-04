"use client";

import { useState } from "react";

import type { DatumMsg } from "@/hooks/useRosBridge";

interface DatumConfigModalProps {
  datum: DatumMsg | null;
  calibrating: boolean;
  pickedPoint: { lat: number; lon: number } | null;
  onStartCalibrating: () => void;
  onCancel: () => void;
  onSaved: () => void;
}

export default function DatumConfigModal({
  datum,
  calibrating,
  pickedPoint,
  onStartCalibrating,
  onCancel,
  onSaved,
}: DatumConfigModalProps) {
  const [headingOffset, setHeadingOffset] = useState("0");
  const [saving, setSaving] = useState(false);

  const save = async () => {
    if (!pickedPoint) return;
    setSaving(true);
    try {
      await fetch("/api/datum", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          lat0: pickedPoint.lat,
          lon0: pickedPoint.lon,
          alt0: 0,
          heading_offset_deg: parseFloat(headingOffset) || 0,
        }),
      });
      onSaved();
    } finally {
      setSaving(false);
    }
  };

  if (!calibrating) {
    return (
      <button
        onClick={onStartCalibrating}
        className="absolute left-3 top-3 z-10 rounded bg-slate-900/80 px-3 py-2 text-xs font-medium text-slate-100 shadow hover:bg-slate-800"
      >
        {datum
          ? `Datum: ${datum.lat0.toFixed(5)}, ${datum.lon0.toFixed(5)} — Recalibrate`
          : "Calibrate datum"}
      </button>
    );
  }

  return (
    <div className="absolute left-3 top-3 z-10 w-72 rounded bg-slate-900/95 p-4 text-xs text-slate-100 shadow-lg">
      <p className="mb-2 font-semibold">Calibrate datum</p>
      {!pickedPoint ? (
        <p className="text-slate-300">
          Click the point on the satellite map that corresponds to the robot&apos;s map-frame
          origin (0, 0).
        </p>
      ) : (
        <>
          <p className="mb-2 text-slate-300">
            Picked: {pickedPoint.lat.toFixed(6)}, {pickedPoint.lon.toFixed(6)}
          </p>
          <label className="mb-1 block text-slate-400">
            Heading offset (deg, clockwise from map +Y to true north)
          </label>
          <input
            type="number"
            value={headingOffset}
            onChange={(e) => setHeadingOffset(e.target.value)}
            className="mb-3 w-full rounded bg-slate-800 px-2 py-1 outline-none"
          />
          <div className="flex gap-2">
            <button
              onClick={save}
              disabled={saving}
              className="flex-1 rounded bg-accent px-2 py-1.5 font-medium text-slate-900 disabled:opacity-50"
            >
              {saving ? "Saving..." : "Save"}
            </button>
          </div>
        </>
      )}
      <button
        onClick={onCancel}
        className="mt-2 w-full rounded bg-slate-700 px-2 py-1.5 font-medium hover:bg-slate-600"
      >
        Cancel
      </button>
    </div>
  );
}
