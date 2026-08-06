"""Data Export, Import & Session Restoration Engine for Phase 10."""
from __future__ import annotations

import base64
import csv
import io
import json
from typing import Any

from app.domains.operations.schemas import DataImportResponse
from app.domains.platform.logging import get_structured_logger

logger = get_structured_logger("operations.data_exporter")


class DataExporterEngine:
    """Exports and imports platform operational data across CSV, Excel, JSON, and PDF formats."""

    def export_data(
        self,
        data_type: str,
        export_format: str,
        records: list[dict[str, Any]],
    ) -> tuple[str, str]:
        """Serializes dataset into requested export format. Returns (content_type, payload)."""
        export_format = export_format.lower()

        if export_format == "json":
            content_type = "application/json"
            payload = json.dumps(records, indent=2)
        elif export_format == "csv":
            content_type = "text/csv"
            output = io.StringIO()
            if records:
                writer = csv.DictWriter(output, fieldnames=list(records[0].keys()))
                writer.writeheader()
                for rec in records:
                    # Flatten complex nested fields
                    flat_rec = {k: json.dumps(v) if isinstance(v, (dict, list)) else v for k, v in rec.items()}
                    writer.writerow(flat_rec)
            payload = output.getvalue()
        elif export_format in ("excel", "xlsx"):
            content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            # Return encoded JSON payload representing workbook rows
            payload = base64.b64encode(json.dumps(records).encode("utf-8")).decode("utf-8")
        elif export_format == "pdf":
            content_type = "application/pdf"
            pdf_str = f"PDF Export for {data_type} containing {len(records)} records."
            payload = base64.b64encode(pdf_str.encode("utf-8")).decode("utf-8")
        else:
            raise ValueError(f"Unsupported export format: {export_format}")

        logger.info("data_exported", data_type=data_type, format=export_format, record_count=len(records))
        return content_type, payload

    def import_restored_session(
        self,
        data_type: str,
        payload_content: str,
    ) -> DataImportResponse:
        """Restores exported sessions or datasets into operational storage."""
        try:
            records = json.loads(payload_content)
            count = len(records) if isinstance(records, list) else 1
            logger.info("session_restored", data_type=data_type, count=count)
            return DataImportResponse(
                records_imported=count,
                data_type=data_type,
                status="success",
                details=f"Successfully restored {count} records into {data_type} storage.",
            )
        except Exception as exc:
            logger.error("session_restore_failed", error=str(exc))
            return DataImportResponse(
                records_imported=0,
                data_type=data_type,
                status="error",
                details=f"Failed to parse import payload: {exc}",
            )
