"use client";

import { useEffect, useRef, useCallback } from "react";
import { useAuthStore } from "@/stores/auth-store";

interface UseWebSocketOptions {
  /** WebSocket endpoint path (e.g. "/api/ws" or "/api/chat/ws/chat") */
  endpoint: string;
  /** Handler called for each parsed JSON message */
  onMessage: (data: Record<string, unknown>) => void;
  /** Called after a successful reconnection (not on initial connect) */
  onReconnect?: () => void;
  /** Called when the server rejects auth (code 4001) — retrying won't help */
  onAuthFailure?: () => void;
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
  onReconnect,
  onAuthFailure,
  maxReconnects = 5,
}: UseWebSocketOptions): UseWebSocketReturn {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectRef = useRef<ReturnType<typeof setTimeout>>();
  const reconnectAttempts = useRef(0);
  const pingRef = useRef<ReturnType<typeof setInterval>>();

  const { token } = useAuthStore();

  // Stable refs for callbacks to avoid reconnects when they change
  const onMessageRef = useRef(onMessage);
  onMessageRef.current = onMessage;
  const onReconnectRef = useRef(onReconnect);
  onReconnectRef.current = onReconnect;
  const onAuthFailureRef = useRef(onAuthFailure);
  onAuthFailureRef.current = onAuthFailure;

  const connect = useCallback(() => {
    if (!token) return;

    const wsBase = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000";
    const url = `${wsBase}${endpoint}`;

    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      // Don't reset reconnectAttempts here — auth hasn't happened yet.
      // Counter resets only after receiving a server message (proving auth passed).
      ws.send(JSON.stringify({ type: "auth", token }));

      // Start heartbeat ping every 30s to keep connection alive
      clearInterval(pingRef.current);
      pingRef.current = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: "ping" }));
        }
      }, 30_000);
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        // Server sent a real message — connection is authenticated & healthy
        const wasReconnect = reconnectAttempts.current > 0;
        reconnectAttempts.current = 0;
        // Notify callers after a successful reconnection so they can
        // reconcile state that may have been missed while disconnected.
        if (wasReconnect) {
          onReconnectRef.current?.();
        }
        onMessageRef.current(data);
      } catch {
        // Ignore non-JSON messages
      }
    };

    ws.onclose = (event) => {
      wsRef.current = null;
      clearInterval(pingRef.current);

      // 4001 = auth failure (expired/invalid token) — retrying won't help.
      // Notify callers so they can clear in-progress state.
      if (event.code === 4001) {
        onAuthFailureRef.current?.();
        return;
      }

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
      clearInterval(pingRef.current);
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
