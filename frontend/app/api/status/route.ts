import { NextResponse } from "next/server";

import { BACKEND_URL } from "@/lib/backend";

export async function GET() {
  const res = await fetch(`${BACKEND_URL}/api/status`, { cache: "no-store" });
  const data = await res.json();
  return NextResponse.json(data, { status: res.status });
}
