import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

const allowed = [
  /^health$/,
  /^session\/status$/,
  /^logs$/,
  /^scan$/,
  /^posts$/,
  /^account$/,
  /^jobs\/[A-Za-z0-9_-]+$/,
];

async function forward(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const { path } = await context.params;
  const route = path.join("/");
  if (!allowed.some((pattern) => pattern.test(route))) {
    return NextResponse.json({ error: "PHOBOS-Tweeter route is not exposed" }, { status: 404 });
  }
  const base = process.env.PHOBOS_TWITTER_INTERNAL_URL || "http://host.docker.internal:8791";
  const target = new URL(`/api/${route}${request.nextUrl.search}`, base);
  const init: RequestInit = { method: request.method, cache: "no-store", headers: { Accept: "application/json" } };
  const token = process.env.PHOBOS_TWITTER_API_TOKEN;
  if (token) init.headers = { ...init.headers, "X-DEIMOS-Token": token };
  if (!["GET", "HEAD"].includes(request.method)) {
    init.headers = { ...init.headers, "Content-Type": "application/json" };
    init.body = await request.text();
  }
  try {
    const response = await fetch(target, init);
    const body = await response.text();
    return new NextResponse(body, {
      status: response.status,
      headers: { "Content-Type": response.headers.get("Content-Type") || "application/json" },
    });
  } catch {
    return NextResponse.json({ error: "PHOBOS-Tweeter service is unavailable" }, { status: 503 });
  }
}

export const GET = forward;
export const POST = forward;
export const DELETE = forward;
