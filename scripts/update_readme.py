"""Refresh the profile README from live GitHub data.

Run by .github/workflows/update-readme.yml every day, and whenever it is
started by hand. It rewrites only the parts of README.md between markers:

    <!--START:projects-->   every public repository, grouped by technology
    <!--START:activity-->   the latest commit in the most recently updated repos
    <!--START:updated-->    the refresh date

and regenerates assets/stats.svg (project counts and the language mix).
Publishing a new repository is therefore all it takes to add it to the profile.

Uses only the Python standard library.
"""
from __future__ import annotations

import json
import os
import re
import urllib.request
from datetime import datetime, timezone
from html import escape
from pathlib import Path

USER = os.environ.get("GITHUB_REPOSITORY_OWNER", "Swami529796")
TOKEN = os.environ.get("GITHUB_TOKEN", "")
ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
STATS = ROOT / "assets" / "stats.svg"

# (heading, topic that puts a repository in this group); the first match wins
GROUPS = [
    ("🗄️ SQL", "sql"),
    ("📗 Excel &amp; VBA", "vba"),
    ("🐍 Python", "python"),
]
DISPLAY_ORDER = ["📗 Excel &amp; VBA", "🐍 Python", "🗄️ SQL", "🧩 Other"]
LANGUAGE_COLOURS = {"VBA": "#867db1", "Python": "#3776ab", "SQL": "#e38c00", "JavaScript": "#f1e05a",
                    "HTML": "#e34c26", "CSS": "#563d7c"}
UPPERCASE_WORDS = {"sql", "vba", "etl", "api", "csv", "pdf"}


def api(path: str):
    request = urllib.request.Request(f"https://api.github.com{path}", headers={
        "Accept": "application/vnd.github+json", "User-Agent": "profile-readme-updater"})
    if TOKEN:
        request.add_header("Authorization", f"Bearer {TOKEN}")
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def pretty_name(repo_name: str) -> str:
    return " ".join(word.upper() if word in UPPERCASE_WORDS else word.capitalize()
                    for word in repo_name.split("-"))


def short_date(iso: str) -> str:
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).strftime("%d %b %Y").lstrip("0")


def group_of(repo: dict) -> str:
    topics = repo.get("topics") or []
    for heading, topic in GROUPS:
        if topic in topics:
            return heading
    language = (repo.get("language") or "").lower()
    for heading, topic in GROUPS:
        if topic == language:
            return heading
    return "🧩 Other"


def projects_section(repos: list[dict]) -> str:
    grouped: dict[str, list[dict]] = {}
    for repo in repos:
        grouped.setdefault(group_of(repo), []).append(repo)

    lines = []
    for heading in DISPLAY_ORDER:
        if heading not in grouped:
            continue
        lines += [f"### {heading}", "", "| Project | What it does | Built with | Updated |", "|---|---|---|---|"]
        for repo in sorted(grouped[heading], key=lambda r: r["pushed_at"], reverse=True):
            tags = " ".join(f"`{topic}`" for topic in (repo.get("topics") or [])[:5])
            description = (repo.get("description") or "").replace("|", "/")
            lines.append(f"| **[{pretty_name(repo['name'])}]({repo['html_url']})** | {description} "
                         f"| {tags} | {short_date(repo['pushed_at'])} |")
        lines.append("")
    return "\n".join(lines).strip()


def activity_section(repos: list[dict]) -> str:
    lines = []
    for repo in sorted(repos, key=lambda r: r["pushed_at"], reverse=True)[:5]:
        try:
            commit = api(f"/repos/{USER}/{repo['name']}/commits?per_page=1")[0]
        except Exception:  # an empty repository has no commits yet
            continue
        message = commit["commit"]["message"].splitlines()[0]
        when = short_date(commit["commit"]["committer"]["date"])
        lines.append(f"- `{when}` &nbsp; **[{repo['name']}]({repo['html_url']})**: {message}")
    return "\n".join(lines)


def language_totals(repos: list[dict]) -> dict[str, int]:
    totals: dict[str, int] = {}
    for repo in repos:
        try:
            for language, size in api(f"/repos/{USER}/{repo['name']}/languages").items():
                totals[language] = totals.get(language, 0) + size
        except Exception:
            continue
    return dict(sorted(totals.items(), key=lambda item: item[1], reverse=True))


def stats_card(repos: list[dict], languages: dict[str, int]) -> str:
    """A small SVG card: project counts on the left, language mix on the right."""
    counts = {heading: 0 for heading in DISPLAY_ORDER}
    for repo in repos:
        counts[group_of(repo)] += 1
    tiles = [("Projects", len(repos)), ("Excel & VBA", counts["📗 Excel &amp; VBA"]),
             ("Python", counts["🐍 Python"]), ("SQL", counts["🗄️ SQL"])]

    parts = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 150" width="100%" role="img" '
             'aria-label="Portfolio at a glance">',
             '<style>.n{font:700 34px "Segoe UI",Helvetica,Arial,sans-serif;fill:#fff}'
             '.l{font:400 13px "Segoe UI",Helvetica,Arial,sans-serif;fill:#bcd6ea}'
             '.h{font:600 13px "Segoe UI",Helvetica,Arial,sans-serif;fill:#bcd6ea;letter-spacing:1px}'
             '.g{font:400 13px "Segoe UI",Helvetica,Arial,sans-serif;fill:#fff}</style>',
             '<rect width="1000" height="150" rx="14" fill="#12324f"/>',
             '<text x="36" y="38" class="h">PORTFOLIO AT A GLANCE</text>']
    for index, (label, value) in enumerate(tiles):
        x = 36 + index * 112
        parts.append(f'<text x="{x}" y="92" class="n">{value}</text><text x="{x}" y="116" class="l">{escape(label)}</text>')

    total = sum(languages.values())
    if total:
        parts.append('<text x="520" y="38" class="h">CODE BY LANGUAGE</text>')
        x, width = 520.0, 444.0
        shown = [(name, size / total) for name, size in languages.items() if size / total >= 0.02][:6]
        scale = sum(share for _, share in shown)
        parts.append(f'<clipPath id="bar"><rect x="{x}" y="58" width="{width}" height="14" rx="7"/></clipPath>'
                     '<g clip-path="url(#bar)">')
        for name, share in shown:
            segment = width * share / scale
            colour = LANGUAGE_COLOURS.get(name, "#8b949e")
            parts.append(f'<rect x="{x:.1f}" y="58" width="{segment:.1f}" height="14" fill="{colour}"/>')
            x += segment
        parts.append("</g>")
        for index, (name, share) in enumerate(shown):
            lx, ly = 520 + (index % 3) * 150, 100 + (index // 3) * 24
            colour = LANGUAGE_COLOURS.get(name, "#8b949e")
            parts.append(f'<circle cx="{lx + 5}" cy="{ly - 4}" r="5" fill="{colour}"/>'
                         f'<text x="{lx + 18}" y="{ly}" class="g">{escape(name)} {share:.0%}</text>')
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def replace_block(text: str, name: str, content: str) -> str:
    pattern = re.compile(rf"(<!--START:{name}-->).*?(<!--END:{name}-->)", re.DOTALL)
    if not pattern.search(text):
        raise SystemExit(f"Marker '{name}' not found in README.md")
    return pattern.sub(lambda match: f"{match.group(1)}\n{content}\n{match.group(2)}", text)


def main() -> None:
    repos = [repo for repo in api(f"/users/{USER}/repos?per_page=100&type=owner")
             if not repo["fork"] and not repo["private"] and not repo["archived"] and repo["name"] != USER]
    if not repos:
        raise SystemExit("No public repositories found; README left unchanged.")

    original = README.read_text(encoding="utf-8")
    text = replace_block(original, "projects", projects_section(repos))
    text = replace_block(text, "activity", activity_section(repos))
    stats = stats_card(repos, language_totals(repos))
    old_stats = STATS.read_text(encoding="utf-8") if STATS.exists() else ""

    if text == original and stats == old_stats:
        print("Nothing has changed; README left as it is.")
        return

    # stamp the date only when something really changed, so there is no daily no-op commit
    text = replace_block(text, "updated",
                         f"<sub>🔄 Project list and stats last refreshed automatically on "
                         f"{datetime.now(timezone.utc):%d %b %Y} by a GitHub Action in this repository.</sub>")
    README.write_text(text, encoding="utf-8", newline="\n")
    STATS.parent.mkdir(exist_ok=True)
    STATS.write_text(stats, encoding="utf-8", newline="\n")
    print(f"README refreshed: {len(repos)} repositories.")


if __name__ == "__main__":
    main()
