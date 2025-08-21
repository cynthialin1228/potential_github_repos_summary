#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import base64
from datetime import datetime, timedelta

import requests
from dotenv import load_dotenv
import google.generativeai as genai
from github_screenshot import screenshot_github
# -----------------------
# Environment & Settings
# -----------------------
load_dotenv()

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "").strip()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

PROCESSED_REPOS_FILE = "processed_repos.txt"
GITHUB_API_BASE = "https://api.github.com"
GH_HEADERS = {
    "Authorization": f"token {GITHUB_TOKEN}" if GITHUB_TOKEN else "",
    "Accept": "application/vnd.github+json",
    "User-Agent": "repo-summarizer-script"
}

MODEL_NAME = "models/gemini-2.5-flash"  # Or "models/gemini-2.5-flash" for cheaper/faster


# -----------------------
# Utilities
# -----------------------
def load_processed_repos():
    if not os.path.exists(PROCESSED_REPOS_FILE):
        return set()
    with open(PROCESSED_REPOS_FILE, "r", encoding="utf-8") as f:
        return set(line.strip() for line in f if line.strip())


def save_processed_repo(repo_full_name: str):
    with open(PROCESSED_REPOS_FILE, "a", encoding="utf-8") as f:
        f.write(repo_full_name + "\n")


def _gh_get(url, headers=None, ok_statuses=(200,), **kwargs):
    h = GH_HEADERS if headers is None else headers
    r = requests.get(url, headers=h, timeout=30, **kwargs)
    if r.status_code not in ok_statuses:
        # Graceful error with details
        raise requests.HTTPError(f"GitHub API {r.status_code} for {url}: {r.text[:200]}")
    return r


# -----------------------
# GitHub fetchers
# -----------------------
def get_top_github_repos(days_back: int = 31, per_page: int = 10):
    since_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%d')
    query = f"created:>{since_date}"
    url = f"{GITHUB_API_BASE}/search/repositories?q={query}&sort=stars&order=desc&per_page={per_page}"
    r = _gh_get(url)
    return r.json().get("items", [])


def get_readme_content(repo_full_name: str):
    url = f"{GITHUB_API_BASE}/repos/{repo_full_name}/readme"
    r = requests.get(url, headers=GH_HEADERS, timeout=30)
    if r.status_code == 404:
        return None
    if r.status_code != 200:
        raise requests.HTTPError(f"GitHub API {r.status_code} for README: {r.text[:200]}")
    try:
        content = base64.b64decode(r.json().get("content", "")).decode("utf-8", errors="replace")
    except Exception:
        content = None
    return content


def get_repo_metadata(repo_obj: dict):
    return {
        "name": repo_obj.get("full_name"),
        "description": repo_obj.get("description"),
        "stars": repo_obj.get("stargazers_count"),
        "forks": repo_obj.get("forks_count"),
        "watchers": repo_obj.get("watchers_count"),
        "license": (repo_obj.get("license") or {}).get("name"),
        "homepage": repo_obj.get("homepage"),
        "language": repo_obj.get("language"),
        "url": repo_obj.get("html_url"),
        "default_branch": repo_obj.get("default_branch"),
        "created_at": repo_obj.get("created_at"),
        "updated_at": repo_obj.get("updated_at"),
        "open_issues": repo_obj.get("open_issues_count"),
    }


def get_repo_topics(repo_full_name: str):
    # Topics require a special preview accept header historically; GitHub has stabilized, but keep fallback
    headers = {**GH_HEADERS, "Accept": "application/vnd.github+json"}
    url = f"{GITHUB_API_BASE}/repos/{repo_full_name}/topics"
    r = requests.get(url, headers=headers, timeout=30)
    if r.status_code == 200:
        return r.json().get("names", [])
    return []


def get_repo_languages(repo_full_name: str):
    url = f"{GITHUB_API_BASE}/repos/{repo_full_name}/languages"
    try:
        r = _gh_get(url)
        langs = r.json()
        return [f"{k} ({v} bytes)" for k, v in sorted(langs.items(), key=lambda x: x[1], reverse=True)[:5]]
    except Exception:
        return []


def get_latest_release(repo_full_name: str):
    url = f"{GITHUB_API_BASE}/repos/{repo_full_name}/releases/latest"
    r = requests.get(url, headers=GH_HEADERS, timeout=30)
    if r.status_code == 200:
        j = r.json()
        return {"tag": j.get("tag_name"), "name": j.get("name"), "published_at": j.get("published_at")}
    return None


def get_issue_pr_counts(repo_full_name: str):
    base = f"{GITHUB_API_BASE}/search/issues"
    def count(q):
        try:
            r = _gh_get(f"{base}?q={q}")
            return r.json().get("total_count", 0)
        except Exception:
            return None
    open_issues = count(f"repo:{repo_full_name}+type:issue+state:open")
    open_prs    = count(f"repo:{repo_full_name}+type:pr+state:open")
    closed_prs  = count(f"repo:{repo_full_name}+type:pr+state:closed")
    return {"open_issues": open_issues, "open_prs": open_prs, "closed_prs": closed_prs}


def get_key_files_and_docs(repo_full_name: str, default_branch: str, max_items: int = 20):
    """List notable files/dirs likely useful to explain the repo."""
    url = f"{GITHUB_API_BASE}/repos/{repo_full_name}/git/trees/{default_branch}?recursive=1"
    try:
        r = _gh_get(url)
        paths = [t.get("path", "") for t in r.json().get("tree", []) if t.get("type") == "blob"]
    except Exception:
        return []

    interesting = [
        p for p in paths if re.search(
            r"(^README\.|^docs/|^example|^examples/|^demo/|requirements\.txt$|setup\.(py|sh)$|install(\.md|\.sh)?$|"
            r"usage(\.md)?$|LICENSE$|CONTRIBUTING|CHANGELOG|benchmark|paper|model|notebook|\.ipynb$)",
            p, re.I
        )
    ]
    return interesting[:max_items]


def extract_links_from_readme(readme_text: str, max_links: int = 10):
    urls = re.findall(r'https?://\S+', readme_text or "")
    seen, out = set(), []
    for u in urls:
        if u not in seen:
            out.append(u)
            seen.add(u)
        if len(out) >= max_links:
            break
    return out


# -----------------------
# Gemini summarizer
# -----------------------
def summarize_with_gemini(readme_content: str, repo_obj: dict):
    if not GEMINI_API_KEY:
        return "GEMINI_API_KEY is missing. Set it in your .env."

    meta = get_repo_metadata(repo_obj)
    repo_full_name = meta.get("name") or ""
    topics = get_repo_topics(repo_full_name) if repo_full_name else []
    langs  = get_repo_languages(repo_full_name) if repo_full_name else []
    rel    = get_latest_release(repo_full_name) if repo_full_name else None
    counts = get_issue_pr_counts(repo_full_name) if repo_full_name else {}
    key_files = get_key_files_and_docs(repo_full_name, meta.get("default_branch") or "main") if repo_full_name else []
    links = extract_links_from_readme(readme_content, max_links=10)

    readme_snip = (readme_content or "")[:12000]

    model = genai.GenerativeModel(model_name=MODEL_NAME)

    prompt = f"""
You are a tech YouTuber for smart teens (~15yo). Write a 1500–2000 word YouTube video transcript about this repository.

Tone & delivery
- Engaging, expert, practical; no hype. Short sentences. Use [PAUSE] after dense parts.
- Define jargon once, then translate to plain meaning (“so what?”).
- No fabrication. If a fact isn’t in first-party sources, write “not mentioned”.
- 1 short opinion block only, marked [OPINION:], grounded in sources.

Sources you may use
- ONLY: the provided text + first-party links found in README or repo metadata (official docs, model cards, owner blog, release notes). No third-party blogs. If missing, write “not mentioned”.

Evidence & citations (strict)
- Any numbers, dates, model/provider names, licenses, or claims of recency must be followed by one inline source tag: [SOURCE: url]. If none, write “not mentioned”.
- Do not include more than 6 total [SOURCE: …] tags; keep only the most important.

Visuals & formatting
- Use Markdown headers.
- On-screen text: [CAPTION: …]
- Visual suggestions: [VISUAL: … (use --- as a section/slide separator)] with a single concise bullet list or a tiny table.

Benchmarks (only if present)
- For each mentioned benchmark: name → plain-English purpose → number (or “not mentioned”) → one-sentence user meaning. No number dumps.

Output format (use this exact order)
# Title
## Hook (≤15s: bold claim + why it matters)
## Setup: What it is, why it matters, who should care (3 bullets)
## Quick Stats (first-party only)
- Purpose: …
- License: …
- Stars: … (add 1-line “so what”)
- Latest release: …
[PAUSE]

## Benchmarks in Plain English (only if present)
- Benchmark A: what it tests → number (or “not mentioned”) → what it means
- Benchmark B: …
[PAUSE] One-line recap.

## Main Features (friendly analogies; no jargon walls)
- Feature 1: what it is → analogy → why it helps
- Feature 2: …
- Feature 3: …
[VISUAL: input → tool → output]
[CAPTION: “How it helps in practice”]

## How It Works (step-by-step story; keep generic ML background to ≤2 sentences)
1) Data/pretraining: what happens + why it matters (≤2 sentences or “not mentioned”)
2) Architecture/routing: plain-language path of a request
3) Post-training/tuning or tooling: what improves for users
[PAUSE]

## Try It (3 steps, first-party only)
1) Install/setup
2) Run once
3) See expected result
[CAPTION: Use .env placeholders; never paste real API keys.]

## Example / Demo (only if README shows it and it’s simple)
- One code block ≤10 lines; explain briefly in plain language. Add [SOURCE: url] if copied.

## Limits & Gotchas
- Hardware footprint (if stated) → local meaning
- Licensing caveats, stability, “under active development,” or “not mentioned”
- One privacy/safety note about secrets (.env, .gitignore)
[PAUSE]

## Who Should Use It & Alternatives
- Best for: …
- Might struggle for: …
- Alternatives (first-party mentions only); else “not mentioned.”

## My Take [OPINION:]
- 1–2 sentences: where it shines, where it likely lags; grounded in sources.
[PAUSE]

## Wrap Up & CTA
- One-line value summary
- One audience question to drive comments
- Ask to like/subscribe if helpful

README START
{readme_snip}
README END
""".strip()

    try:    
        resp = model.generate_content(prompt)
        return (resp.text).strip()
    except Exception as e:
        return f"An error occurred while generating the summary: {e}"

def main():
    processed = load_processed_repos()
    print("Searching for the top new repository...")

    try:
        top_repos = get_top_github_repos()
        if not top_repos:
            print("No new repositories found in the last 31 days.")
            return

        for repo in top_repos:
            repo_name = repo.get("full_name")
            if not repo_name:
                continue

            if repo_name in processed:
                print(f"Skipping already processed repository: {repo_name}")
                continue

            print(f"Found new top repository: {repo_name} (⭐ {repo.get('stargazers_count')})")
            print(f"URL: {repo.get('html_url')}")
            
            # Save outputs
            from datetime import datetime

            # create a single timestamp once
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            # safe directory path
            safe_repo = repo['full_name'].replace('/', '_')
            output_dir = f"output/{timestamp}_{safe_repo}"

            # ensure the directory exists
            os.makedirs(output_dir, exist_ok=True)
            # take screenshot
            try:
                print("Taking repository screenshot...")
                screenshot_path=os.path.join(output_dir, "screenshot.png")
                screenshot_github(repo.get('html_url'), output=screenshot_path)
                if screenshot_path:
                    print(f"Screenshot saved to: {screenshot_path}")
                else:
                    print("Failed to take screenshot.")
            except Exception as e:
                print(f"An error occurred while taking screenshot: {e}")

            readme = get_readme_content(repo_name)
            if readme:
                print("\nGenerating summary with Gemini... 🤖")
                summary = summarize_with_gemini(readme, repo)
                print("\n--- Summary ---")
                print(summary)
                print("--- End of Summary ---\n")

                # write transcript
                with open(os.path.join(output_dir, "transcript.md"), "w", encoding="utf-8") as f:
                    f.write("# YouTube Transcript\n\n")
                    f.write(summary)

                # clean plain text summary
                plain_summary = re.sub(r'#+\s*', '', summary)                                # remove headers
                plain_summary = re.sub(r'^\s*[\*\-]\s*', '', plain_summary, flags=re.MULTILINE)  # remove list stars/dashes
                plain_summary = re.sub(r'\*{1,2}([^*]+)\*{1,2}', r'\1', plain_summary)       # strip bold/italic markers
                plain_summary = re.sub(r'\[PAUSE\]', '', plain_summary)
                plain_summary = re.sub(r'\[VISUAL:.*?\]', '', plain_summary)
                plain_summary = re.sub(r'\[CAPTION:.*?\]', '', plain_summary)

                # normalize whitespace
                plain_summary = re.sub(r'\n\s*\n+', '\n\n', plain_summary)  # collapse multiple blank lines
                plain_summary = plain_summary.strip()

                # write plain summary
                summary_filepath = os.path.join(output_dir, "summary.txt")
                with open(summary_filepath, "w", encoding="utf-8") as f:
                    f.write(plain_summary)


            else:
                print("This repository does not have a README file.")

            # Mark as processed and exit after handling the first new one
            save_processed_repo(repo_name)
            # video_filename = f"{output_dir}/summary_video.mp4"
            # text to speech
            try:
                # from txt_to_srt import generate_video
                # generate_video(summary_filepath, video_filename)
                from text_to_speech import generate_tts_from_text
                print("Generating text-to-speech audio...")
                audio_filepath = f"{output_dir}/summary_audio.mp3"
                generate_tts_from_text(plain_summary, audio_filepath)
                print(f"Audio saved to: {audio_filepath}")
            except ImportError:
                print("text_to_speech module not found. Skipping TTS generation.")
            except Exception as e:
                print(f"An error occurred during TTS generation: {e}")
            break
        else:
            print("No new, unprocessed repositories found.")

    except requests.exceptions.RequestException as e:
        print(f"Error fetching data from GitHub: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    main()
