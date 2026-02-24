type MessageHandler = (data: WebSocketMessage) => void;

export interface WebSocketMessage {
  type: string;
  [key: string]: unknown;
}

export class WSClient {
  private ws: WebSocket | null = null;
  private handlers: Map<string, Set<MessageHandler>> = new Map();
  private reconnectAttempts = 0;
  private maxReconnects = 5;
  private url: string;

  constructor(url?: string) {
    const wsBase = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000";
    this.url = url || `${wsBase}/ws`;
  }

  connect(token?: string): void {
    const url = token ? `${this.url}?token=${token}` : this.url;
    this.ws = new WebSocket(url);

    this.ws.onopen = () => {
      this.reconnectAttempts = 0;
      this.emit({ type: "connected" });
    };

    this.ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data) as WebSocketMessage;
        this.emit(data);
      } catch {
        // ignore non-JSON messages
      }
    };

    this.ws.onclose = () => {
      this.emit({ type: "disconnected" });
      if (this.reconnectAttempts < this.maxReconnects) {
        this.reconnectAttempts++;
        const delay = Math.min(1000 * 2 ** this.reconnectAttempts, 30000);
        setTimeout(() => this.connect(token), delay);
      }
    };

    this.ws.onerror = () => {
      this.ws?.close();
    };
  }

  disconnect(): void {
    this.maxReconnects = 0;
    this.ws?.close();
    this.ws = null;
  }

  on(type: string, handler: MessageHandler): () => void {
    if (!this.handlers.has(type)) {
      this.handlers.set(type, new Set());
    }
    this.handlers.get(type)!.add(handler);
    return () => this.handlers.get(type)?.delete(handler);
  }

  private emit(data: WebSocketMessage): void {
    // Call type-specific handlers
    this.handlers.get(data.type)?.forEach((h) => h(data));
    // Call wildcard handlers
    this.handlers.get("*")?.forEach((h) => h(data));
  }

  send(data: unknown): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(data));
    }
  }
}

export const wsClient = new WSClient();
