"use client";

import { useEffect, useRef, useState } from "react";
import type { ServiceState, StreamEvent } from "@/lib/types";

export function useServiceSocket(url: string, source: "go" | "python") {
  const [status, setStatus] = useState<ServiceState>("connecting");
  const [events, setEvents] = useState<StreamEvent[]>([]);
  const retry = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    let socket: WebSocket | null = null;
    let disposed = false;

    const connect = () => {
      if (disposed) return;
      setStatus("connecting");
      socket = new WebSocket(url);
      socket.onopen = () => setStatus("online");
      socket.onmessage = (message) => {
        try {
          const parsed = JSON.parse(message.data) as StreamEvent;
          setEvents((current) => [{ ...parsed, source: parsed.source ?? source }, ...current].slice(0, 250));
        } catch {
          setEvents((current) => [{
            type: "log",
            source,
            message: String(message.data),
            timestamp: new Date().toISOString(),
          }, ...current].slice(0, 250));
        }
      };
      socket.onerror = () => socket?.close();
      socket.onclose = () => {
        setStatus("offline");
        if (!disposed) retry.current = setTimeout(connect, 3500);
      };
    };

    connect();
    return () => {
      disposed = true;
      if (retry.current) clearTimeout(retry.current);
      socket?.close();
    };
  }, [source, url]);

  return { status, events };
}
