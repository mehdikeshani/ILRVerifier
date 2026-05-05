"""
Given a GitHub issue URL, returns the set of commit hashes whose messages
developers linked to that issue (via "fixes #N", "closes #N", etc.).

Usage:
    python issue_commits.py <issue_url> [--token <github_token>]

The GitHub token is optional but recommended to avoid rate-limiting.
It can also be set via the GITHUB_TOKEN environment variable.
"""

import os
import re
import sys
import argparse

import requests


def parse_issue_url(url: str) -> tuple[str, str, int]:
    match = re.search(r"github\.com/([^/]+)/([^/]+)/issues/(\d+)", url)
    if not match:
        raise ValueError(f"Not a valid GitHub issue URL: {url}")
    owner, repo, number = match.groups()
    return owner, repo, int(number)


def get_resolving_commits(issue_url: str, token: str | None = None) -> set[str]:
    """Return the set of commit SHAs that reference the given GitHub issue."""
    owner, repo, issue_number = parse_issue_url(issue_url)

    session = requests.Session()
    session.headers.update({
        # Required to access the timeline endpoint (stable since 2022, no preview needed)
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    if token:
        session.headers["Authorization"] = f"Bearer {token}"

    commit_hashes: set[str] = set()
    page = 1

    while True:
        response = session.get(
            f"https://api.github.com/repos/{owner}/{repo}/issues/{issue_number}/timeline",
            params={"per_page": 100, "page": page},
        )

        if response.status_code == 404:
            raise ValueError(f"Issue not found: {issue_url}")
        if response.status_code == 403:
            raise PermissionError(
                "GitHub API rate limit exceeded or access denied. "
                "Provide a personal access token via --token or GITHUB_TOKEN."
            )
        response.raise_for_status()

        events = response.json()
        if not events:
            break

        for event in events:
            # "referenced" fires when a commit pushed to the repo mentions the issue.
            # "cross-referenced" fires when a PR or issue mentions it — we skip those
            # unless they include a commit_id (some PR merges do).
            if event.get("event") == "referenced":
                sha = event.get("commit_id")
                if sha:
                    commit_hashes.add(sha)

        if len(events) < 100:
            break
        page += 1

    return commit_hashes


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Find commits that developers linked to a GitHub issue."
    )
    parser.add_argument("issue_url", help="Full GitHub issue URL")
    parser.add_argument(
        "--token",
        default=os.environ.get("GITHUB_TOKEN"),
        help="GitHub personal access token (or set GITHUB_TOKEN env var)",
    )
    args = parser.parse_args()

    try:
        commits = get_resolving_commits(args.issue_url, token=args.token)
    except (ValueError, PermissionError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    if not commits:
        print("No commits found that reference this issue.")
    else:
        print(f"Found {len(commits)} commit(s) referencing the issue:")
        for sha in sorted(commits):
            print(sha)


if __name__ == "__main__":
    main()
