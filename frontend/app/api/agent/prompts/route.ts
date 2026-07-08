import { NextRequest, NextResponse } from "next/server";

const BACKEND_HOST = process.env.NEXT_PUBLIC_BACKEND_HOST || "localhost";
const BACKEND_PORT = process.env.NEXT_PUBLIC_BACKEND_PORT || "8080";
const BACKEND_BASE = (
  process.env.BACKEND_BASE_URL ||
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  `http://${BACKEND_HOST}:${BACKEND_PORT}`
).replace(/\/+$/, "");

/** Proxy /api/agent/prompts to the Go backend. */
export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const backendUrl = `${BACKEND_BASE}/agent/prompts?${searchParams.toString()}`;
  const userID = request.headers.get("X-User-Id") || "";

  try {
    const res = await fetch(backendUrl, {
      cache: "no-store",
      headers: userID ? { "X-User-Id": userID } : {},
    });
    const body = await res.text();
    return new NextResponse(body, {
      status: res.status,
      headers: { "Content-Type": res.headers.get("content-type") || "application/json" },
    });
  } catch {
    return NextResponse.json(
      { error: "无法连接后端，请确认 BACKEND_BASE_URL / NEXT_PUBLIC_API_BASE_URL 已配置且后端可访问" },
      { status: 502 }
    );
  }
}

export async function PUT(request: NextRequest) {
  const backendUrl = `${BACKEND_BASE}/agent/prompts`;
  const userID = request.headers.get("X-User-Id") || "";

  try {
    const body = await request.text();
    const res = await fetch(backendUrl, {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
        ...(userID ? { "X-User-Id": userID } : {}),
      },
      body,
    });
    const resBody = await res.text();
    return new NextResponse(resBody, {
      status: res.status,
      headers: { "Content-Type": res.headers.get("content-type") || "application/json" },
    });
  } catch {
    return NextResponse.json(
      { error: "无法连接后端，请确认 BACKEND_BASE_URL / NEXT_PUBLIC_API_BASE_URL 已配置且后端可访问" },
      { status: 502 }
    );
  }
}

