"use client";

import React, { useEffect, useRef } from "react";
import { createChart, ColorType, IChartApi, ISeriesApi } from "lightweight-charts";

interface EquityDataPoint {
  time: string; // YYYY-MM-DD
  value: number;
}

interface TradingViewEquityChartProps {
  data: EquityDataPoint[];
  benchmarkData?: EquityDataPoint[];
  height?: number;
}

export function TradingViewEquityChart({
  data,
  benchmarkData,
  height = 300,
}: TradingViewEquityChartProps) {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);

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

    // Primary Area Series for Equity Curve
    const areaSeries = chart.addAreaSeries({
      lineColor: "#10b981",
      topColor: "rgba(16, 185, 129, 0.35)",
      bottomColor: "rgba(16, 185, 129, 0.0)",
      lineWidth: 2,
      priceFormat: {
        type: "price",
        precision: 2,
        minMove: 0.01,
      },
    });

    if (data && data.length > 0) {
      areaSeries.setData(data as any);
    }

    // Benchmark line if provided
    if (benchmarkData && benchmarkData.length > 0) {
      const benchmarkSeries = chart.addLineSeries({
        color: "#06b6d4",
        lineWidth: 1,
        lineStyle: 2, // Dashed
      });
      benchmarkSeries.setData(benchmarkData as any);
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
  }, [data, benchmarkData, height]);

  return (
    <div className="w-full relative">
      <div ref={chartContainerRef} className="w-full" />
    </div>
  );
}
