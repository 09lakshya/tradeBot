async function getHealth(): Promise<string> {
  const base = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
  try {
    const res = await fetch(`${base}/health`, { cache: "no-store" });
    const data = await res.json();
    return data.status ?? "unknown";
  } catch {
    return "unreachable";
  }
}

export default async function Home() {
  const apiStatus = await getHealth();
  return (
    <main style={{ fontFamily: "system-ui", padding: "2rem", maxWidth: 720 }}>
      <h1>Trade Bot</h1>
      <p>Autonomous AI trading platform — paper trading phase.</p>
      <p>
        Backend API status: <strong>{apiStatus}</strong>
      </p>
      <p style={{ color: "#666" }}>
        Dashboard, equity curve, positions, and trade log are wired up as the
        backend domains come online (correctness-first build order).
      </p>
    </main>
  );
}
