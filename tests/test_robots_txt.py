"""robots.txt (frontend/public/robots.txt) — what search engines and AI bots get.

Anubis used to serve its own robots.txt, which ended in `User-agent: *` /
`Disallow: /` and so shut Google out of the whole site. These tests lock in
that ours welcomes search engines, keeps the secret report links and admin out
of any index, and shuts out AI crawlers."""

from pathlib import Path

ROBOTS = Path(__file__).resolve().parent.parent / "frontend" / "public" / "robots.txt"


def groups() -> list[tuple[list[str], list[str]]]:
    """Groups of `User-agent` lines → the rules that follow them."""
    out: list[tuple[list[str], list[str]]] = []
    for raw in ROBOTS.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, _, value = line.partition(":")
        key, value = key.strip().lower(), value.strip()
        if key == "user-agent":
            if not out or out[-1][1]:
                out.append(([], []))
            out[-1][0].append(value.lower())
        elif out:
            out[-1][1].append(f"{key}:{value}")
    return out


def rules_for(agent: str) -> list[str]:
    g = groups()
    own = next((rules for agents, rules in g if agent.lower() in agents), None)
    if own is not None:
        return own
    return next(rules for agents, rules in g if "*" in agents)


def test_search_engines_welcome():
    for bot in ["Googlebot", "Bingbot", "DuckDuckBot", "Applebot", "facebookexternalhit"]:
        assert "allow:/" in rules_for(bot), bot
        assert "disallow:/" not in rules_for(bot), bot


def test_only_admin_and_report_links_disallowed():
    disallowed = sorted(r for r in rules_for("*") if r.startswith("disallow:"))
    assert disallowed == ["disallow:/admin", "disallow:/report/"]


def test_ai_crawlers_shut_out():
    for bot in ["GPTBot", "ClaudeBot", "Google-Extended", "CCBot", "Bytespider"]:
        assert rules_for(bot) == ["disallow:/"], bot
