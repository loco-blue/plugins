#!/usr/bin/env python3
"""Sync plugins/groq/ai/groq.yaml with https://console.groq.com/docs/models.

Scrapes the "Production Models", "Production Systems", and "Preview Models"
tables on the Groq docs page and updates each model's context_window,
max_output_tokens, and pricing in groq.yaml. For each of those models it also
fetches its own https://console.groq.com/docs/model/<id> page and reads the
capability link row rendered under the model's icon strip, e.g.:

    <div class="text-xs mt-3 text-primary">
      <a href="/docs/tool-use">Tool Use</a>,
      <a href="/docs/structured-outputs#json-object-mode">JSON Object Mode</a>,
      <a href="/docs/structured-outputs">JSON Schema Mode</a>,
      <a href="/docs/reasoning">Reasoning</a>,
      <a href="/docs/vision">Vision</a>
    </div>

to set `tool_call` / `structured_output` (JSON Schema Mode specifically --
"JSON Object Mode" has no dedicated flag today) / `thinking` / `vision`. Any
other feature already listed on a model (streaming, document, ...) is left
untouched since this page doesn't cover it. Models found on the page but
missing from groq.yaml are appended with a `# TODO: review pricing/limits`
marker instead of being silently dropped.

Audio (whisper), TTS (orpheus), and other non-per-token-priced models are
skipped since groq.yaml only tracks `type: llm` chat models.

Usage:
    python plugins/groq/scripts/update_models.py [--dry-run] [--remove-stale]
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import httpx
from bs4 import BeautifulSoup
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq

DOCS_URL = "https://console.groq.com/docs/models"
MODEL_PAGE_URL = "https://console.groq.com/docs/model/{model_id}"
YAML_PATH = Path(__file__).resolve().parents[1] / "ai" / "groq.yaml"

SECTION_HEADINGS = {"Production Models", "Production Systems", "Preview Models"}
MANAGED_FEATURES = ("tool_call", "structured_output", "thinking", "vision")

# href -> feature flag, matched against the capability link row on a model's
# own docs page. "/docs/structured-outputs#json-object-mode" (JSON Object
# Mode) is deliberately unmapped -- groq.yaml has no separate flag for it,
# only for JSON Schema Mode's "/docs/structured-outputs" (no anchor).
CAPABILITY_HREFS = {
    "/docs/tool-use": "tool_call",
    "/docs/structured-outputs": "structured_output",
    "/docs/reasoning": "thinking",
    "/docs/vision": "vision",
}


def fetch_html(url: str = DOCS_URL) -> str:
    resp = httpx.get(
        url,
        headers={"User-Agent": "Mozilla/5.0 (compatible; loco-groq-model-sync)"},
        timeout=30,
        follow_redirects=True,
    )
    resp.raise_for_status()
    return resp.text


def _parse_int(text: str) -> int | None:
    text = text.strip()
    if not text or text == "-":
        return None
    digits = re.sub(r"[^\d]", "", text)
    return int(digits) if digits else None


def _parse_price_cell(cell) -> tuple[float, float] | None:
    """Return (input_per_1m, output_per_1m) or None (contact sales / non-token pricing)."""
    spans = cell.select("div.flex-grow > div > span")
    if len(spans) != 2:
        return None

    values = []
    for span in spans:
        raw = span.get_text(" ", strip=True)
        # e.g. "$0.15 input" -> 0.15 ; skip anything not "$<num> <input|output>"
        match = re.match(r"\$([\d.]+)\s+(input|output)", raw)
        if not match:
            return None
        values.append(float(match.group(1)))

    if len(values) != 2:
        return None
    return values[0], values[1]


def scrape_models(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    models = []

    for heading in soup.find_all(["h2", "h3"]):
        title = heading.get_text(strip=True)
        if title not in SECTION_HEADINGS:
            continue

        table = heading.find_next("table")
        if table is None:
            continue

        for row in table.select("tbody tr"):
            cells = row.find_all("td")
            if len(cells) < 6:
                continue

            id_cell, speed_cell, price_cell, _rate_limits, ctx_cell, max_out_cell = cells[:6]

            model_id_el = id_cell.select_one("div[id]")
            if model_id_el is None:
                continue
            model_id = model_id_el["id"].strip()

            name_link = id_cell.find("a")
            label = name_link.get_text(strip=True) if name_link else model_id
            # Most models live at /docs/model/<id>, but Groq's own compound
            # systems (groq/compound, groq/compound-mini) link elsewhere
            # (e.g. /docs/compound/systems/compound) -- always prefer the
            # href actually on this page over guessing the URL pattern.
            href = name_link.get("href") if name_link else None
            page_url = (
                f"https://console.groq.com{href}"
                if href
                else MODEL_PAGE_URL.format(model_id=model_id)
            )

            context_window = _parse_int(ctx_cell.get_text())
            max_output_tokens = _parse_int(max_out_cell.get_text())
            if context_window is None or max_output_tokens is None:
                # Non chat-completion rows (e.g. audio) don't carry both values.
                continue

            # Models with no token throughput (e.g. Prompt Guard classifiers)
            # aren't autoregressive chat models despite having context/output
            # figures.
            if _parse_int(speed_cell.get_text()) is None:
                continue

            price_text = price_cell.get_text(" ", strip=True)
            if "per 1M characters" in price_text or "per hour" in price_text:
                # TTS / audio pricing units -- not a chat completion model.
                continue

            pricing = _parse_price_cell(price_cell)

            models.append(
                {
                    "model": model_id,
                    "label": label,
                    "context_window": context_window,
                    "max_output_tokens": max_output_tokens,
                    "pricing": pricing,
                    "section": title,
                    "page_url": page_url,
                }
            )

    return models


def scrape_model_capabilities(html: str) -> set[str]:
    """Parse a model's own /docs/model/<id> page for its capability link row:

        <div class="text-xs mt-3 text-primary">
          <a href="/docs/tool-use">Tool Use</a>, ...
        </div>
    """
    soup = BeautifulSoup(html, "html.parser")
    caps: set[str] = set()
    for div in soup.select("div.text-xs.mt-3.text-primary"):
        for a in div.find_all("a", href=True):
            feature = CAPABILITY_HREFS.get(str(a["href"]))
            if feature:
                caps.add(feature)
    return caps


def fetch_model_capabilities(model_id: str, page_url: str) -> set[str] | None:
    """Returns None (rather than an empty set) on fetch failure, so callers
    can tell "no capabilities" apart from "couldn't check" and leave that
    model's managed features untouched instead of clearing them.
    """
    try:
        html = fetch_html(page_url)
    except httpx.HTTPError as e:
        print(
            f"Warning: failed to fetch {page_url} ({e}); {model_id}'s feature flags left as-is.",
            file=sys.stderr,
        )
        return None
    return scrape_model_capabilities(html)


def load_yaml(path: Path) -> tuple[YAML, CommentedMap]:
    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.indent(mapping=2, sequence=4, offset=2)
    yaml.width = 4096
    with path.open("r", encoding="utf-8") as f:
        data = yaml.load(f)
    if data.get("models") is None:
        # groq.yaml has no `models:` section yet (fresh file, or a previous
        # run was interrupted mid-write and left a partial file) -- start a
        # fresh list instead of crashing on data["models"].
        print("Warning: groq.yaml has no 'models:' section; starting a new one.", file=sys.stderr)
        data["models"] = CommentedSeq()
    return yaml, data


def _desired_features(
    model_id: str,
    existing: list | None,
    capabilities: dict[str, set[str] | None],
) -> list[str]:
    """Managed flags (tool_call, structured_output, thinking, vision) come
    from the model's own docs page; any other feature already on the entry
    (streaming, document, ...) is preserved as-is since that page doesn't
    cover it. If this model's page failed to fetch (None), its managed flags
    are left untouched rather than cleared.
    """
    existing = existing or []
    unmanaged = [f for f in existing if f not in MANAGED_FEATURES]

    caps = capabilities.get(model_id)
    if caps is None:
        managed = [f for f in MANAGED_FEATURES if f in existing]
    else:
        managed = [f for f in MANAGED_FEATURES if f in caps]

    return managed + unmanaged


def update_yaml(
    data: CommentedMap,
    scraped: list[dict],
    capabilities: dict[str, set[str] | None],
) -> tuple[list[str], list[str], list[str]]:
    by_id = {m["model"]: m for m in scraped}
    existing_ids = {entry["model"] for entry in data["models"]}

    updated: list[str] = []
    unchanged: list[str] = []

    for entry in data["models"]:
        remote = by_id.get(entry["model"])
        if remote is None:
            continue

        changed = False
        props = entry.setdefault("properties", CommentedMap())
        if props.get("context_window") != remote["context_window"]:
            props["context_window"] = remote["context_window"]
            changed = True
        if props.get("max_output_tokens") != remote["max_output_tokens"]:
            props["max_output_tokens"] = remote["max_output_tokens"]
            changed = True

        if remote["pricing"] is not None:
            input_price, output_price = remote["pricing"]
            pricing = entry.setdefault("pricing", CommentedMap())
            if pricing.get("input_per_1m") != input_price:
                pricing["input_per_1m"] = input_price
                changed = True
            if pricing.get("output_per_1m") != output_price:
                pricing["output_per_1m"] = output_price
                changed = True

        new_features = _desired_features(
            entry["model"], entry.get("features"), capabilities
        )
        if new_features != list(entry.get("features") or []):
            if new_features:
                entry["features"] = new_features
            elif "features" in entry:
                del entry["features"]
            changed = True

        (updated if changed else unchanged).append(entry["model"])

    added: list[str] = []
    for model_id, remote in by_id.items():
        if model_id in existing_ids:
            continue

        new_entry = CommentedMap()
        new_entry["model"] = model_id
        new_entry["label"] = CommentedMap({"en_US": remote["label"]})
        new_entry["type"] = "llm"
        features = _desired_features(model_id, None, capabilities)
        if features:
            new_entry["features"] = features
        new_entry["properties"] = CommentedMap(
            {
                "context_window": remote["context_window"],
                "max_output_tokens": remote["max_output_tokens"],
            }
        )
        if remote["pricing"] is not None:
            input_price, output_price = remote["pricing"]
            new_entry["pricing"] = CommentedMap(
                {"input_per_1m": input_price, "output_per_1m": output_price}
            )
        # Attach the marker as a start-of-block comment owned by the new
        # entry's own mapping node (not the parent sequence's "before item"
        # index) -- a sequence-level comment gets mis-positioned by ruamel on
        # a later re-dump once a *sibling* entry's map gains a new trailing
        # key (e.g. a subsequent features update), since its render anchor is
        # tied to token position rather than to this entry.
        new_entry.yaml_set_start_comment(
            "TODO: review pricing/limits -- Contact Sales models have none scraped "
            "(added by update_models.py)"
        )
        data["models"].append(new_entry)
        added.append(model_id)

    return updated, added, list(existing_ids - by_id.keys())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true", help="Print the diff without writing groq.yaml"
    )
    parser.add_argument(
        "--remove-stale",
        action="store_true",
        help="Delete entries no longer listed on the Groq docs page",
    )
    args = parser.parse_args()

    html = fetch_html()
    scraped = scrape_models(html)
    if not scraped:
        print("No models scraped from docs page; aborting without changes.", file=sys.stderr)
        return 1

    capabilities: dict[str, set[str] | None] = {}
    for m in scraped:
        capabilities[m["model"]] = fetch_model_capabilities(m["model"], m["page_url"])

    yaml, data = load_yaml(YAML_PATH)
    updated, added, stale = update_yaml(data, scraped, capabilities)

    if args.remove_stale and stale:
        data["models"] = [entry for entry in data["models"] if entry["model"] not in stale]

    print(f"Scraped {len(scraped)} chat models from {DOCS_URL}")
    print(f"Updated:  {updated or '(none)'}")
    print(f"Added:    {added or '(none)'}")
    print(f"Stale:    {stale or '(none)'}" + ("" if not stale else "" if args.remove_stale else "  (kept; pass --remove-stale to delete)"))

    if args.dry_run:
        print("\n--dry-run: not writing groq.yaml")
        return 0

    if not updated and not added and not (args.remove_stale and stale):
        print("\ngroq.yaml already up to date.")
        return 0

    # Write to a temp file and replace atomically so an interrupted run
    # (Ctrl+C, crash) can never leave groq.yaml as a partially-written file.
    tmp_path = YAML_PATH.with_suffix(".yaml.tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        yaml.dump(data, f)
    tmp_path.replace(YAML_PATH)
    print(f"\nWrote {YAML_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
