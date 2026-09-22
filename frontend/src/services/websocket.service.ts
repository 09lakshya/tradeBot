export type ConnectionStatus = "CONNECTING" | "OPEN" | "CLOSING" | "CLOSED";

export type ConnectionQuality = "EXCELLENT" | "GOOD" | "POOR" | "OFFLINE";

export interface WebSocketMessage {
  type: string;
  topic?: string;
  payload?: any;
  timestamp?: number;
}

export type MessageHandler = (message: WebSocketMessage) => void;

class WebSocketService {
  private socket: WebSocket | null = null;
  private url: string = "";
  private reconnectAttempts: number = 0;
  private maxReconnectAttempts: number = 10;
  private baseReconnectDelay: number = 1000;
  private pingIntervalMs: number = 15000;
  private pingTimer: NodeJS.Timeout | null = null;
  private pongTimeoutTimer: NodeJS.Timeout | null = null;
  private listeners: Map<string, Set<MessageHandler>> = new Map();
  private statusListeners: Set<(status: ConnectionStatus) => void> = new Set();
  private qualityListeners: Set<(quality: ConnectionQuality, latency: number) => void> = new Set();
  
  private status: ConnectionStatus = "CLOSED";
  private quality: ConnectionQuality = "OFFLINE";
  private lastPingTime: number = 0;
  private currentLatency: number = 0;
  private isExplicitDisconnect: boolean = false;

  public connect(url?: string): void {
    if (typeof window === "undefined") return;

    if (url) {
      this.url = url;
    } else if (!this.url) {
      const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      const host = process.env.NEXT_PUBLIC_WS_HOST || window.location.host || "localhost:8000";
      this.url = `${protocol}//${host}/ws`;
    }

    if (this.socket && (this.socket.readyState === WebSocket.OPEN || this.socket.readyState === WebSocket.CONNECTING)) {
      return;
    }

    this.isExplicitDisconnect = false;
    this.updateStatus("CONNECTING");

    try {
      this.socket = new WebSocket(this.url);
      
      this.socket.onopen = this.handleOpen.bind(this);
      this.socket.onmessage = this.handleMessage.bind(this);
      this.socket.onerror = this.handleError.bind(this);
      this.socket.onclose = this.handleClose.bind(this);
    } catch (err) {
      console.warn("[WebSocketService] Failed to establish WebSocket connection, falling back:", err);
      this.updateStatus("CLOSED");
      this.updateQuality("OFFLINE", 0);
      this.scheduleReconnect();
    }
  }

  public disconnect(): void {
    this.isExplicitDisconnect = true;
    this.clearHeartbeatTimers();
    if (this.socket) {
      this.socket.close();
      this.socket = null;
    }
    this.updateStatus("CLOSED");
    this.updateQuality("OFFLINE", 0);
  }

  public subscribe(topic: string, handler: MessageHandler): () => void {
    if (!this.listeners.has(topic)) {
      this.listeners.set(topic, new Set());
    }
    this.listeners.get(topic)!.add(handler);

    if (this.status === "OPEN") {
      this.send({ type: "SUBSCRIBE", topic });
    }

    return () => {
      const topicListeners = this.listeners.get(topic);
      if (topicListeners) {
        topicListeners.delete(handler);
        if (topicListeners.size === 0) {
          this.listeners.delete(topic);
          if (this.status === "OPEN") {
            this.send({ type: "UNSUBSCRIBE", topic });
          }
        }
      }
    };
  }

  public onStatusChange(callback: (status: ConnectionStatus) => void): () => void {
    this.statusListeners.add(callback);
    callback(this.status);
    return () => {
      this.statusListeners.delete(callback);
    };
  }

  public onQualityChange(callback: (quality: ConnectionQuality, latency: number) => void): () => void {
    this.qualityListeners.add(callback);
    callback(this.quality, this.currentLatency);
    return () => {
      this.qualityListeners.delete(callback);
    };
  }

  public send(message: WebSocketMessage): boolean {
    if (this.socket && this.socket.readyState === WebSocket.OPEN) {
      this.socket.send(JSON.stringify(message));
      return true;
    }
    return false;
  }

  public getStatus(): ConnectionStatus {
    return this.status;
  }

  public getQuality(): ConnectionQuality {
    return this.quality;
  }

  public getLatency(): number {
    return this.currentLatency;
  }

  private handleOpen(): void {
    this.reconnectAttempts = 0;
    this.updateStatus("OPEN");
    this.startHeartbeat();

    this.listeners.forEach((_, topic) => {
      this.send({ type: "SUBSCRIBE", topic });
    });
  }

  private handleMessage(event: MessageEvent): void {
    try {
      const data: WebSocketMessage = JSON.parse(event.data);

      if (data.type === "PONG") {
        this.handlePong();
        return;
      }

      if (data.topic && this.listeners.has(data.topic)) {
        this.listeners.get(data.topic)!.forEach((handler) => handler(data));
      }

      if (this.listeners.has("*")) {
        this.listeners.get("*")!.forEach((handler) => handler(data));
      }
    } catch (err) {
      console.error("[WebSocketService] Failed to parse message:", err);
    }
  }

  private handleError(error: Event): void {
    console.warn("[WebSocketService] Socket error encountered:", error);
  }

  private handleClose(event: CloseEvent): void {
    this.clearHeartbeatTimers();
    this.updateStatus("CLOSED");
    this.updateQuality("OFFLINE", 0);

    if (!this.isExplicitDisconnect) {
      this.scheduleReconnect();
    }
  }

  private scheduleReconnect(): void {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.warn("[WebSocketService] Max reconnect attempts reached. Falling back to HTTP polling.");
      return;
    }

    const delay = Math.min(
      this.baseReconnectDelay * Math.pow(2, this.reconnectAttempts) + Math.random() * 500,
      30000
    );
    this.reconnectAttempts++;

    setTimeout(() => {
      if (!this.isExplicitDisconnect) {
        this.connect();
      }
    }, delay);
  }

  private startHeartbeat(): void {
    this.clearHeartbeatTimers();
    this.pingTimer = setInterval(() => {
      if (this.socket && this.socket.readyState === WebSocket.OPEN) {
        this.lastPingTime = performance.now();
        this.send({ type: "PING", timestamp: Date.now() });

        this.pongTimeoutTimer = setTimeout(() => {
          console.warn("[WebSocketService] Pong timeout reached.");
          this.updateQuality("POOR", 999);
        }, 5000);
      }
    }, this.pingIntervalMs);
  }

  private handlePong(): void {
    if (this.pongTimeoutTimer) {
      clearTimeout(this.pongTimeoutTimer);
      this.pongTimeoutTimer = null;
    }
    const latency = Math.round(performance.now() - this.lastPingTime);
    this.currentLatency = latency;

    let quality: ConnectionQuality = "EXCELLENT";
    if (latency > 300) {
      quality = "POOR";
    } else if (latency > 100) {
      quality = "GOOD";
    }

    this.updateQuality(quality, latency);
  }

  private clearHeartbeatTimers(): void {
    if (this.pingTimer) {
      clearInterval(this.pingTimer);
      this.pingTimer = null;
    }
    if (this.pongTimeoutTimer) {
      clearTimeout(this.pongTimeoutTimer);
      this.pongTimeoutTimer = null;
    }
  }

  private updateStatus(newStatus: ConnectionStatus): void {
    this.status = newStatus;
    this.statusListeners.forEach((cb) => cb(newStatus));
  }

  private updateQuality(newQuality: ConnectionQuality, latency: number): void {
    this.quality = newQuality;
    this.qualityListeners.forEach((cb) => cb(newQuality, latency));
  }
}

export const wsService = new WebSocketService();
