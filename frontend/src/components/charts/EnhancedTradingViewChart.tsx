"use client";

import React, { useEffect, useRef, useState, useMemo } from "react";
import { createChart, ColorType, IChartApi, ISeriesApi, SeriesMarker } from "lightweight-charts";
import { Play, Pause, SkipForward, RotateCcw, LineChart, Layers, Eye, ShieldAlert, Target, PenTool } from "lucide-react";

export interface CandleDataPoint {
  time: string; // YYYY-MM-DD
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
}

export interface TradeMarker {
  time: string;
  type: "BUY" | "SELL";
  price: number;
  text?: string;
}

export interface PositionOverlay {
  entryPrice: number;
  stopLossPrice?: number;
  takeProfitPrice?: number;
  symbol: string;
  side: "LONG" | "SHORT";
}

interface EnhancedTradingViewChartProps {
  initialCandles?: CandleDataPoint[];
  markers?: TradeMarker[];
  positionOverlay?: PositionOverlay;
  height?: number;
}

// No invented price history, fills or open position: the chart draws only what
// the caller passes in, and renders an empty state when there is nothing to draw.
export function EnhancedTradingViewChart({
  initialCandles = [],
  markers = [],
  positionOverlay,
  height = 360,
}: EnhancedTradingViewChartProps) {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candlestickSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<"Histogram"> | null>(null);
  const smaSeriesRef = useRef<ISeriesApi<"Line"> | null>(null);

  // Indicators State
  const [showVolume, setShowVolume] = useState(true);
  const [showSMA, setShowSMA] = useState(true);
  const [showOverlays, setShowOverlays] = useState(true);

  // Replay Mode State
  const [isReplayActive, setIsReplayActive] = useState(false);
  const [replayIndex, setReplayIndex] = useState<number>(initialCandles.length);
  const [isPlaying, setIsPlaying] = useState(false);
  const [replaySpeed, setReplaySpeed] = useState(1000);

  // Active Candles based on replay
  const currentCandles = useMemo(() => {
    return isReplayActive ? initialCandles.slice(0, replayIndex) : initialCandles;
  }, [initialCandles, isReplayActive, replayIndex]);

  // Chart initialization & updating
  useEffect(() => {
    if (!chartContainerRef.current) return;

    const chart = createChart(chartContainerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: "#94a3b8",
        fontSize: 11,
      },
      grid: {
        vertLines: { color: "#1e293b" },
        horzLines: { color: "#1e293b" },
      },
      width: chartContainerRef.current.clientWidth,
      height: height,
      timeScale: {
        borderColor: "#1e293b",
        timeVisible: true,
      },
      rightPriceScale: {
        borderColor: "#1e293b",
      },
    });

    chartRef.current = chart;

    // Candlestick Series
    const candleSeries = chart.addCandlestickSeries({
      upColor: "#10b981",
      downColor: "#f43f5e",
      borderVisible: false,
      wickUpColor: "#10b981",
      wickDownColor: "#f43f5e",
    });
    candlestickSeriesRef.current = candleSeries;
    candleSeries.setData(currentCandles as any);

    // Volume Histogram
    if (showVolume) {
      const volSeries = chart.addHistogramSeries({
        color: "#38bdf8",
        priceFormat: { type: "volume" },
        priceScaleId: "volume",
      });
      chart.priceScale("volume").applyOptions({
        scaleMargins: { top: 0.8, bottom: 0 },
      });
      volSeries.setData(
        currentCandles.map((c) => ({
          time: c.time,
          value: c.volume ?? 0,
          color: c.close >= c.open ? "rgba(16, 185, 129, 0.4)" : "rgba(244, 63, 94, 0.4)",
        })) as any
      );
      volumeSeriesRef.current = volSeries;
    }

    // Simple Moving Average (SMA 20)
    if (showSMA && currentCandles.length >= 2) {
      const smaData = currentCandles.map((c, idx, arr) => {
        const slice = arr.slice(Math.max(0, idx - 4), idx + 1);
        const avg = slice.reduce((sum, item) => sum + item.close, 0) / slice.length;
        return { time: c.time, value: avg };
      });
      const smaSeries = chart.addLineSeries({
        color: "#eab308",
        lineWidth: 1,
      });
      smaSeries.setData(smaData as any);
      smaSeriesRef.current = smaSeries;
    }

    // Buy / Sell Markers
    if (markers && markers.length > 0) {
      const formattedMarkers: SeriesMarker<any>[] = markers
        .filter((m) => currentCandles.some((c) => c.time === m.time))
        .map((m) => ({
          time: m.time,
          position: m.type === "BUY" ? "belowBar" : "aboveBar",
          color: m.type === "BUY" ? "#10b981" : "#f43f5e",
          shape: m.type === "BUY" ? "arrowUp" : "arrowDown",
          text: m.text || `${m.type} @ ${m.price}`,
        }));
      candleSeries.setMarkers(formattedMarkers);
    }

    // Position Overlays (Entry Price line, SL, TP)
    if (showOverlays && positionOverlay) {
      candleSeries.createPriceLine({
        price: positionOverlay.entryPrice,
        color: "#06b6d4",
        lineWidth: 2,
        lineStyle: 0, // Solid
        axisLabelVisible: true,
        title: `ENTRY (${positionOverlay.side})`,
      });

      if (positionOverlay.stopLossPrice) {
        candleSeries.createPriceLine({
          price: positionOverlay.stopLossPrice,
          color: "#f43f5e",
          lineWidth: 1,
          lineStyle: 2, // Dashed
          axisLabelVisible: true,
          title: "STOP-LOSS",
        });
      }

      if (positionOverlay.takeProfitPrice) {
        candleSeries.createPriceLine({
          price: positionOverlay.takeProfitPrice,
          color: "#10b981",
          lineWidth: 1,
          lineStyle: 2, // Dashed
          axisLabelVisible: true,
          title: "TAKE-PROFIT",
        });
      }
    }

    chart.timeScale().fitContent();

    const handleResize = () => {
      if (chartContainerRef.current && chartRef.current) {
        chartRef.current.applyOptions({ width: chartContainerRef.current.clientWidth });
      }
    };
    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
      chart.remove();
    };
  }, [currentCandles, markers, positionOverlay, showVolume, showSMA, showOverlays, height]);

  // Replay timer loop
  useEffect(() => {
    let timer: NodeJS.Timeout | null = null;

    if (isPlaying && isReplayActive) {
      timer = setInterval(() => {
        setReplayIndex((prev) => {
          if (prev >= initialCandles.length) {
            setIsPlaying(false);
            return prev;
          }
          return prev + 1;
        });
      }, replaySpeed);
    }

    return () => {
      if (timer) clearInterval(timer);
    };
  }, [isPlaying, isReplayActive, initialCandles.length, replaySpeed]);

  const toggleReplay = () => {
    if (!isReplayActive) {
      setIsReplayActive(true);
      setReplayIndex(2);
    } else {
      setIsReplayActive(false);
      setIsPlaying(false);
      setReplayIndex(initialCandles.length);
    }
  };

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 shadow-xl">
      {/* Chart Control Toolbar */}
      <div className="flex flex-wrap items-center justify-between gap-3 mb-3 pb-3 border-b border-slate-800 text-xs font-mono">
        <div className="flex items-center gap-2">
          <LineChart className="w-4 h-4 text-emerald-400" />
          <span className="font-bold text-slate-200">
            {positionOverlay?.symbol ?? "No instrument selected"} — 1D
          </span>

          <div className="flex items-center gap-1 ml-2">
            <button
              onClick={() => setShowSMA(!showSMA)}
              className={`px-2 py-0.5 rounded text-[11px] font-semibold border ${
                showSMA ? "bg-amber-500/20 text-amber-300 border-amber-500/40" : "bg-slate-800 text-slate-500 border-slate-700"
              }`}
            >
              SMA 20
            </button>
            <button
              onClick={() => setShowVolume(!showVolume)}
              className={`px-2 py-0.5 rounded text-[11px] font-semibold border ${
                showVolume ? "bg-sky-500/20 text-sky-300 border-sky-500/40" : "bg-slate-800 text-slate-500 border-slate-700"
              }`}
            >
              Volume
            </button>
            <button
              onClick={() => setShowOverlays(!showOverlays)}
              className={`px-2 py-0.5 rounded text-[11px] font-semibold border ${
                showOverlays ? "bg-cyan-500/20 text-cyan-300 border-cyan-500/40" : "bg-slate-800 text-slate-500 border-slate-700"
              }`}
            >
              SL/TP Levels
            </button>
          </div>
        </div>

        {/* Replay Controls */}
        <div className="flex items-center gap-2 bg-slate-950 px-2.5 py-1 rounded-lg border border-slate-800">
          <button
            onClick={toggleReplay}
            className={`px-2 py-0.5 rounded text-[11px] font-medium flex items-center gap-1 transition ${
              isReplayActive ? "bg-purple-600 text-white" : "bg-slate-800 text-slate-300 hover:bg-slate-750"
            }`}
          >
            <RotateCcw className="w-3 h-3" />
            {isReplayActive ? "Exit Replay" : "Replay Mode"}
          </button>

          {isReplayActive && (
            <>
              <button
                onClick={() => setIsPlaying(!isPlaying)}
                className="p-1 text-slate-200 hover:text-emerald-400"
                title={isPlaying ? "Pause Replay" : "Play Replay"}
              >
                {isPlaying ? <Pause className="w-3.5 h-3.5" /> : <Play className="w-3.5 h-3.5 text-emerald-400" />}
              </button>

              <button
                onClick={() => setReplayIndex((prev) => Math.min(prev + 1, initialCandles.length))}
                disabled={replayIndex >= initialCandles.length}
                className="p-1 text-slate-200 hover:text-cyan-400 disabled:opacity-40"
                title="Step 1 Bar Forward"
              >
                <SkipForward className="w-3.5 h-3.5" />
              </button>

              <span className="text-[11px] text-slate-400 font-mono">
                Bar {replayIndex}/{initialCandles.length}
              </span>
            </>
          )}
        </div>
      </div>

      {/* Chart Canvas */}
      <div ref={chartContainerRef} className="w-full relative min-h-[300px]">
        {initialCandles.length === 0 && (
          <div className="absolute inset-0 flex flex-col items-center justify-center text-center gap-1 pointer-events-none">
            <LineChart className="w-6 h-6 text-slate-700" />
            <p className="text-sm text-slate-500 font-mono">No price data</p>
            <p className="text-[11px] text-slate-600">
              Select an instrument once market data has been synced.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
