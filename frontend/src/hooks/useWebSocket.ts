"use client";

import { useEffect, useState, useCallback } from "react";
import { wsService, ConnectionStatus, ConnectionQuality, WebSocketMessage, MessageHandler } from "@/services/websocket.service";

export interface UseWebSocketReturn {
  status: ConnectionStatus;
  quality: ConnectionQuality;
  latency: number;
  isConnected: boolean;
  isFallback: boolean;
  subscribe: (topic: string, handler: MessageHandler) => () => void;
  send: (message: WebSocketMessage) => boolean;
  reconnect: () => void;
}

export function useWebSocket(url?: string): UseWebSocketReturn {
  const [status, setStatus] = useState<ConnectionStatus>("CLOSED");
  const [quality, setQuality] = useState<ConnectionQuality>("OFFLINE");
  const [latency, setLatency] = useState<number>(0);

  useEffect(() => {
    wsService.connect(url);

    const unsubStatus = wsService.onStatusChange((s) => setStatus(s));
    const unsubQuality = wsService.onQualityChange((q, l) => {
      setQuality(q);
      setLatency(l);
    });

    return () => {
      unsubStatus();
      unsubQuality();
    };
  }, [url]);

  const subscribe = useCallback((topic: string, handler: MessageHandler) => {
    return wsService.subscribe(topic, handler);
  }, []);

  const send = useCallback((message: WebSocketMessage) => {
    return wsService.send(message);
  }, []);

  const reconnect = useCallback(() => {
    wsService.disconnect();
    wsService.connect(url);
  }, [url]);

  const isConnected = status === "OPEN";
  const isFallback = status === "CLOSED" || quality === "OFFLINE";

  return {
    status,
    quality,
    latency,
    isConnected,
    isFallback,
    subscribe,
    send,
    reconnect,
  };
}
