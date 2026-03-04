"use client";

import { useEffect, useRef, useCallback } from "react";
import { useAuthStore } from "@/stores/auth-store";

interface UseWebSocketOptions {
  /** WebSocket endpoint path (e.g. "/api/ws" or "/api/chat/ws/chat") */
  endpoint: string;
  /** Handler called for each parsed JSON message */
  onMessage: (data: Record<string, unknown>) => void;
  /** Maximum reconnection attempts (default: 5) */
  maxReconnects?: number;
}

interface UseWebSocketReturn {
  /** Send a JSON-serializable message */
  send: (data: unknown) => void;
  /** Whether the WebSocket is currently connected */
  isConnected: boolean;
}

/**
 * Generic WebSocket hook with auto-connect, reconnection with exponential
 * backoff, and JSON message parsing.
 *
 * Extracts the shared connection lifecycle from domain-specific hooks
 * (chat, databricks, config-apis, context-engine).
 */
export function useWebSocket({
  endpoint,
  onMessage,
  maxReconnects = 5,
}: UseWebSocketOptions): UseWebSocketReturn {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectRef = useRef<ReturnType<typeof setTimeout>>();
  const reconnectAttempts = useRef(0);

  const { token } = useAuthStore();

  // Stable ref for the message handler to avoid reconnects when callbacks change
  const onMessageRef = useRef(onMessage);
  onMessageRef.current = onMessage;

  const connect = useCallback(() => {
    if (!token) return;

    const wsBase = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000";
    const url = `${wsBase}${endpoint}`;

    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      reconnectAttempts.current = 0;
      // Send auth token as first message (avoids token in URL/logs)
      ws.send(JSON.stringify({ type: "auth", token }));
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        onMessageRef.current(data);
      } catch {
        // Ignore non-JSON messages
      }
    };

    ws.onclose = () => {
      wsRef.current = null;
      if (reconnectAttempts.current < maxReconnects) {
        reconnectAttempts.current++;
        const delay = Math.min(1000 * 2 ** reconnectAttempts.current, 30000);
        reconnectRef.current = setTimeout(connect, delay);
      }
    };

    ws.onerror = () => {
      ws.close();
    };
  }, [token, endpoint, maxReconnects]);

  // Auto-connect on mount, clean up on unmount
  useEffect(() => {
    connect();
    return () => {
      clearTimeout(reconnectRef.current);
      if (wsRef.current) {
        wsRef.current.onclose = null; // Prevent reconnect on unmount
        wsRef.current.close();
      }
    };
  }, [connect]);

  const send = useCallback((data: unknown) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(data));
    }
  }, []);

  const isConnected = wsRef.current?.readyState === WebSocket.OPEN;

  return { send, isConnected };
}
