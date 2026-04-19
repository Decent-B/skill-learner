from __future__ import annotations

from pathlib import Path

import pytest

from skill_learner.connectors.config import (
    ExploitDBJob,
    GitHubAdvisoriesJob,
    HackerOneReportsJob,
    NVDJob,
    PentesterLandJob,
    load_connector_pack,
)


def test_load_connector_pack_parses_discriminated_jobs(tmp_path: Path) -> None:
    pack_path = tmp_path / "pack.yaml"
    pack_path.write_text(
        "\n".join(
            [
                "benchmark_id: test-benchmark",
                "jobs:",
                "  - source: nvd",
                "    enabled: true",
                "    max_records: 100",
                "  - source: github_advisories",
                "    enabled: true",
                "    advisory_type: reviewed",
                "  - source: exploit_db",
                "    enabled: false",
                "  - source: pentester_land",
                "    enabled: true",
                "    max_links_per_record: 1",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    pack = load_connector_pack(pack_path)

    assert pack.benchmark_id == "test-benchmark"
    assert pack.max_concurrent_jobs == 1
    assert isinstance(pack.jobs[0], NVDJob)
    assert isinstance(pack.jobs[1], GitHubAdvisoriesJob)
    assert isinstance(pack.jobs[2], ExploitDBJob)
    assert isinstance(pack.jobs[3], PentesterLandJob)


def test_load_connector_pack_accepts_max_concurrency_and_hackerone_discovery(
    tmp_path: Path,
) -> None:
    pack_path = tmp_path / "pack.yaml"
    pack_path.write_text(
        "\n".join(
            [
                "benchmark_id: test-benchmark",
                "max_concurrent_jobs: 6",
                "jobs:",
                "  - source: hackerone_reports",
                "    enabled: true",
                "    discover_reports_via_graphql: true",
                "    discovery_page_size: 50",
                "    discovery_max_pages: 3",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    pack = load_connector_pack(pack_path)

    assert pack.max_concurrent_jobs == 6
    assert isinstance(pack.jobs[0], HackerOneReportsJob)
    assert pack.jobs[0].report_ids == []
    assert pack.jobs[0].discover_reports_via_graphql is True


def test_hackerone_job_requires_report_ids_or_discovery() -> None:
    with pytest.raises(ValueError):
        HackerOneReportsJob(source="hackerone_reports")
