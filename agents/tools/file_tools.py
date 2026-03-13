from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import aiofiles
import structlog
from pydantic import BaseModel

logger = structlog.get_logger()

# Restrict file writes to the outputs directory
SAFE_OUTPUT_DIR = Path("/app/outputs")


class DataSummary(BaseModel):
    """Summary of a CSV dataset."""

    shape: list[int]
    columns: list[str]
    dtypes: dict[str, str]
    null_counts: dict[str, int]
    statistics: dict[str, Any]
    sample_rows: list[dict[str, Any]]


async def file_read(path: str) -> str:
    """Read a file from the local filesystem."""
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    async with aiofiles.open(str(file_path), mode="r", encoding="utf-8", errors="replace") as f:
        content = await f.read()

    logger.info("file_tools.read", path=path, chars=len(content))
    return content


async def file_write(path: str, content: str) -> bool:
    """Write content to a file. Restricted to the outputs directory."""
    file_path = Path(path)

    # Security: only allow writes to safe directory
    try:
        file_path.resolve().relative_to(SAFE_OUTPUT_DIR.resolve())
    except ValueError:
        # If relative path given, put it in outputs
        file_path = SAFE_OUTPUT_DIR / file_path.name

    file_path.parent.mkdir(parents=True, exist_ok=True)

    async with aiofiles.open(str(file_path), mode="w", encoding="utf-8") as f:
        await f.write(content)

    logger.info("file_tools.write", path=str(file_path), chars=len(content))
    return True


async def csv_analyze(file_path: str) -> DataSummary:
    """Analyze a CSV file and return a structured summary.

    Uses pandas for analysis but returns a Pydantic model, never a raw DataFrame.
    """
    import pandas as pd

    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"CSV not found: {file_path}")

    def _analyze() -> DataSummary:
        df = pd.read_csv(str(path))

        stats = df.describe(include="all").to_dict()
        # Convert stats to serializable format
        clean_stats: dict[str, Any] = {}
        for col, col_stats in stats.items():
            clean_stats[col] = {
                k: (None if pd.isna(v) else v)
                for k, v in col_stats.items()
            }

        return DataSummary(
            shape=list(df.shape),
            columns=df.columns.tolist(),
            dtypes={col: str(dtype) for col, dtype in df.dtypes.items()},
            null_counts=df.isnull().sum().to_dict(),
            statistics=clean_stats,
            sample_rows=df.head(5).to_dict(orient="records"),
        )

    summary = await asyncio.to_thread(_analyze)
    logger.info("file_tools.csv_analyze", path=file_path, shape=summary.shape)
    return summary


async def json_parse(file_path: str, jq_query: str | None = None) -> dict[str, Any]:
    """Parse a JSON file and optionally filter with a simple key path."""
    content = await file_read(file_path)
    data = json.loads(content)

    if jq_query:
        # Simple dot-notation key path (e.g., "data.items")
        keys = jq_query.strip(".").split(".")
        result = data
        for key in keys:
            if isinstance(result, dict):
                result = result.get(key, {})
            elif isinstance(result, list) and key.isdigit():
                result = result[int(key)]
            else:
                break
        return {"query": jq_query, "result": result}

    return {"data": data}
