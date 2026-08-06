"""Unit tests for Automated Reports, Research Notes, Data Exporter & Dashboard."""
from __future__ import annotations

from pathlib import Path
from app.domains.operations.dashboard_service import DashboardService
from app.domains.operations.data_exporter import DataExporterEngine
from app.domains.operations.report_generator import AutomatedReportGenerator
from app.domains.operations.research_notes import ResearchNotesEngine


def test_report_generator_formats():
    gen = AutomatedReportGenerator()

    json_rep = gen.generate_report("daily", "2026-08-01", "2026-08-01", export_format="json")
    assert json_rep.format == "json"
    assert "portfolio_summary" in json_rep.rendered_content

    html_rep = gen.generate_report("daily", "2026-08-01", "2026-08-01", export_format="html")
    assert "<html>" in html_rep.rendered_content

    csv_rep = gen.generate_report("daily", "2026-08-01", "2026-08-01", export_format="csv")
    assert "Metric,Value" in csv_rep.rendered_content

    pdf_rep = gen.generate_report("daily", "2026-08-01", "2026-08-01", export_format="pdf")
    assert len(pdf_rep.rendered_content) > 0


def test_research_notes_engine(tmp_path: Path):
    engine = ResearchNotesEngine(notes_dir=tmp_path)
    note = engine.create_note(
        entity_type="strategy",
        entity_id="strat_trend_v1",
        author="Quant Lead",
        title="Optimization Note",
        content_markdown="### Optimization\nAdjusted stop-loss multiplier.",
        tags=["optimization", "v1"],
    )
    assert note.author == "Quant Lead"
    listed = engine.list_notes(entity_type="strategy")
    assert len(listed) == 1


def test_data_exporter_and_dashboard():
    exporter = DataExporterEngine()
    records = [{"id": "trd_1", "symbol": "AAPL", "pnl": 120.0}]
    ctype, payload = exporter.export_data("trade_journal", "csv", records)
    assert ctype == "text/csv"
    assert "trd_1" in payload

    imp_res = exporter.import_restored_session("trade_journal", '[{"id": "trd_1"}]')
    assert imp_res.status == "success"
    assert imp_res.records_imported == 1

    dash_svc = DashboardService()
    dash_data = dash_svc.get_dashboard_data(days=10)
    assert len(dash_data.equity_curve) == 10
    assert len(dash_data.cost_accumulation) == 10
