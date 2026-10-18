"""Collect the 98 third-party READMEs into Kairos' source library (README text only).

Reads `docs/integration/98_SOURCE_MASTER_LEDGER.csv` and each repository's checkout under
`--external`, copies ONE readme per repository byte-for-byte (decoded as UTF-8 with replacement) into
`backend/api/services/sources/readmes/<owner>__<repo>.md`, and writes `catalog.json` plus the
kit index files (`INDEX_98_READMES.md`, `README_LINKS_98.csv`). No other source file is copied and
nothing in a README is executed or interpreted: READMEs are untrusted reference data.

    python backend/scripts/collect_readmes.py [--external ../track1-agent/EXTERNAL_REPOS]
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "backend" / "api" / "services" / "sources"
CANDIDATES = ("README.md", "readme.md", "Readme.md", "README.markdown", "README.rst", "README.txt", "README",
              ".github/README.md", "docs/README.md")
MAX_BYTES = 512 * 1024
SLUG = re.compile(r"^[A-Za-z0-9_.-]+__[A-Za-z0-9_.-]+$")


def find_readme(repo_dir: Path) -> Path | None:
    for name in CANDIDATES:
        candidate = repo_dir / name
        if candidate.is_file() and not candidate.is_symlink():
            return candidate
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ledger", default=str(ROOT / "docs" / "integration" / "98_SOURCE_MASTER_LEDGER.csv"))
    parser.add_argument("--external", default=str(ROOT.parent / "track1-agent" / "EXTERNAL_REPOS"))
    args = parser.parse_args()
    external = Path(args.external)
    readme_dir = OUT / "readmes"
    readme_dir.mkdir(parents=True, exist_ok=True)

    with open(args.ledger, newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))

    catalog = []
    for row in rows:
        repo = row["repo"].strip()
        slug = repo.replace("/", "__")
        if not SLUG.fullmatch(slug):
            raise SystemExit(f"unsafe repository identity: {repo!r}")
        checkout = external / slug
        source = find_readme(checkout)
        if source is None and (external / f"{slug}__RECOVERED").is_dir():
            checkout = external / f"{slug}__RECOVERED"  # re-cloned after a failed partial checkout
            source = find_readme(checkout)
        entry = {
            "repo": repo,
            "slug": slug,
            "url": row["url"],
            "project": row["project"],
            "summary": row["distinct_mechanism"],
            "domain": row["description"],
            "family": row["correlation_cluster"],
            "pack": row["unification_pack"],
            "closest_overlap": row["closest_overlap"],
            "rank": int(row["editorial_rank"] or 0),
            "license_status": row["license_status"],
            "audit_state": row["audit_state"],
            "audited_implementation": row["audited_implementation_status"],
            "source_commit_sha": row["source_commit_sha"] or row["pinned_sha"],
            "caveat": row["research_caveat"],
            "readme": None,
        }
        if source is not None:
            raw = source.read_bytes()[:MAX_BYTES]
            text = raw.decode("utf-8", errors="replace")
            (readme_dir / f"{slug}.md").write_text(text, encoding="utf-8", newline="")
            entry["readme"] = {
                "file": f"{slug}.md",
                "origin": source.relative_to(checkout).as_posix(),
                "bytes": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
                "truncated": source.stat().st_size > MAX_BYTES,
            }
        catalog.append(entry)

    catalog.sort(key=lambda item: item["repo"].lower())
    (OUT / "catalog.json").write_text(json.dumps(catalog, indent=1, ensure_ascii=False), encoding="utf-8")

    with open(OUT / "README_LINKS_98.csv", "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["repo", "url", "family", "readme_status", "readme_file", "summary"])
        for item in catalog:
            writer.writerow([item["repo"], item["url"], item["family"],
                             "PRESENT" if item["readme"] else "ABSENT",
                             item["readme"]["file"] if item["readme"] else "", item["summary"]])

    lines = ["# Graph Hacks: 98 repository README index", "",
             "Third-party README text is untrusted reference material. Summaries come from the research ledger, "
             "not from tested behaviour. Missing READMEs are marked ABSENT, never invented.", ""]
    for family in sorted({item["family"] for item in catalog}):
        members = [item for item in catalog if item["family"] == family]
        lines += [f"## {family} ({len(members)})", "", "| Repository | README | Mechanism (README-derived) |", "|---|---|---|"]
        for item in members:
            link = f"[readmes/{item['readme']['file']}](readmes/{item['readme']['file']})" if item["readme"] else "ABSENT"
            lines.append(f"| [{item['repo']}]({item['url']}) | {link} | {item['summary'].replace('|', '/')} |")
        lines.append("")
    (OUT / "INDEX_98_READMES.md").write_text("\n".join(lines), encoding="utf-8")

    present = sum(1 for item in catalog if item["readme"])
    print(f"repositories={len(catalog)} readme_present={present} readme_absent={len(catalog) - present}")
    for item in catalog:
        if not item["readme"]:
            print("ABSENT:", item["repo"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
