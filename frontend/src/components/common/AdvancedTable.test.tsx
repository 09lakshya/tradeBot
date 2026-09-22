import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { AdvancedTable, ColumnDef } from "@/components/common/AdvancedTable";

interface TestRow {
  id: string;
  symbol: string;
  price: number;
}

const mockData: TestRow[] = [
  { id: "1", symbol: "RELIANCE", price: 2850 },
  { id: "2", symbol: "TCS", price: 4120 },
  { id: "3", symbol: "INFY", price: 1820 },
];

const mockColumns: ColumnDef<TestRow>[] = [
  { key: "symbol", header: "Symbol", accessor: (r) => r.symbol },
  { key: "price", header: "Price", accessor: (r) => r.price },
];

describe("AdvancedTable Component", () => {
  it("renders table headers and rows correctly", () => {
    render(
      <AdvancedTable
        data={mockData}
        columns={mockColumns}
        keyExtractor={(r) => r.id}
        title="Test Instruments"
      />
    );

    expect(screen.getByText("Test Instruments")).toBeInTheDocument();
    expect(screen.getByText("RELIANCE")).toBeInTheDocument();
    expect(screen.getByText("TCS")).toBeInTheDocument();
    expect(screen.getByText("INFY")).toBeInTheDocument();
  });

  it("filters rows based on search input query", () => {
    render(
      <AdvancedTable
        data={mockData}
        columns={mockColumns}
        keyExtractor={(r) => r.id}
      />
    );

    const searchInput = screen.getByPlaceholderText("Search table...");
    fireEvent.change(searchInput, { target: { value: "TCS" } });

    expect(screen.getByText("TCS")).toBeInTheDocument();
    expect(screen.queryByText("RELIANCE")).not.toBeInTheDocument();
  });
});
