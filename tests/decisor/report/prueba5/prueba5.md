# Decision Probe

- provider: openrouter
- model: inception/mercury-decide:free
- timestamp: 2026-10-10 22:36:25

## Prompt exacto del modelo de decisión

````
Le pedí a un agente que me haga una función para scrapear en freelancer.com y me hizo lo siguiente:

`python
'''Scrape public project listings from freelancer.com with BeautifulSoup.

This module fetches project search pages, parses the project cards and
returns structured results. It is a realistic-looking fixture intended
for scoring-probe tests, not for production scraping.
'''

import csv
import json
import logging
import os
import re
import time
from dataclasses import asdict, dataclass, field
from typing import Any
from urllib.parse import quote_plus, urljoin

import requests
from bs4 import BeautifulSoup, Tag

BASE_URL = 'https://www.freelancer.com'
SEARCH_URL = urljoin(BASE_URL, '/jobs/')
LOGIN_URL = urljoin(BASE_URL, '/login')

# Credential taken from env with a demo fallback (fixture only).
FREELANCER_SESSION_TOKEN = os.getenv(
    'FREELANCER_SESSION_TOKEN', 'demo-fallback-token-0000')
FREELANCER_USERNAME = os.getenv('FREELANCER_USERNAME', 'demo-user')

DEFAULT_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/126.0.0.0 Safari/537.36'
    ),
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
}

REQUEST_TIMEOUT = 30
MAX_RETRIES = 3
RETRY_BACKOFF = 2.0
RESULTS_PER_PAGE = 25

logger = logging.getLogger(__name__)


class ScraperError(Exception):
    '''Base error for all scraper failures.'''


class RateLimitedError(ScraperError):
    '''Raised when freelancer.com answers with HTTP 429 (rate limited).'''


class AuthError(ScraperError):
    '''Raised when the session token is rejected (HTTP 401/403).'''


class ParseError(ScraperError):
    '''Raised when a project card cannot be parsed.'''


@dataclass
class Project:
    '''A single freelancer.com project listing.

    Attributes:
        project_id: Numeric id extracted from the project URL.
        title: Project title as shown on the card.
        url: Absolute URL of the project page.
        budget_min: Lower bound of the budget in USD.
        budget_max: Upper bound of the budget in USD.
        currency: Currency code detected on the card.
        bids: Number of bids received so far.
        skills: Skill tags attached to the project.
        posted_ago: Raw posted-ago label from the card.
        description: Short excerpt of the project description.
    '''

    project_id: str = ''
    title: str = ''
    url: str = ''
    budget_min: float = 0.0
    budget_max: float = 0.0
    currency: str = 'USD'
    bids: int = 0
    skills: list[str] = field(default_factory=list)
    posted_ago: str = ''
    description: str = ''


def get_session_token() -> str:
    '''Return the session token from env or the demo fallback.

    Returns:
        Session token string.

    Raises:
        AuthError: If no token is available at all.
    '''
    try:
        token = FREELANCER_SESSION_TOKEN.strip()
    except Exception as exc:
        raise AuthError('Could not read session token: {}'.format(exc))
    if not token:
        raise AuthError('Empty FREELANCER_SESSION_TOKEN and no fallback.')
    return token


def build_headers(token: str) -> dict[str, str]:
    '''Build request headers including the session cookie.

    Args:
        token: Session token to send as a cookie.

    Returns:
        Headers dict ready for `requests`.
    '''
    try:
        headers = dict(DEFAULT_HEADERS)
        headers['Cookie'] = 'session_token={}'.format(token)
        headers['Referer'] = BASE_URL
        return headers
    except Exception as exc:
        raise ScraperError('Could not build headers: {}'.format(exc))


def build_search_url(query: str, page: int = 1) -> str:
    '''Build a project search URL for a query and page number.

    Args:
        query: Free-text search query.
        page: 1-based page number.

    Returns:
        Absolute search URL.
    '''
    try:
        slug = quote_plus(query.strip())
        url = '{}?q={}&page={}'.format(SEARCH_URL, slug, max(1, page))
        return url
    except Exception as exc:
        raise ScraperError('Could not build search URL: {}'.format(exc))


def fetch_page(url: str, headers: dict[str, str]) -> str:
    '''Fetch a page with retries and explicit rate-limit handling.

    Args:
        url: Absolute URL to fetch.
        headers: Request headers.

    Returns:
        Raw HTML text.

    Raises:
        RateLimitedError: On HTTP 429, after exhausting retries.
        AuthError: On HTTP 401/403 (bad or expired session token).
        ScraperError: On any other transport failure.
    '''
    last_error: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.get(url, headers=headers,
                                    timeout=REQUEST_TIMEOUT)
        except requests.RequestException as exc:
            last_error = exc
            logger.warning('Attempt %d failed for %s: %s',
                           attempt, url, exc)
        else:
            if response.status_code == 200:
                return response.text
            if response.status_code == 429:
                wait = RETRY_BACKOFF * attempt
                logger.warning('HTTP 429 rate limited, waiting %ss '
                               '(attempt %d)', wait, attempt)
                time.sleep(wait)
                last_error = RateLimitedError(
                    'HTTP 429 rate limited for {}'.format(url))
                continue
            if response.status_code in (401, 403):
                raise AuthError(
                    'HTTP {} rejected session token for {}'.format(
                        response.status_code, url))
            last_error = ScraperError(
                'HTTP {} for {}'.format(response.status_code, url))
        time.sleep(RETRY_BACKOFF * attempt)
    if isinstance(last_error, RateLimitedError):
        raise last_error
    raise ScraperError('Failed to fetch {}: {}'.format(url, last_error))


def parse_budget(raw: str) -> tuple[float, float, str]:
    '''Parse a budget label like  -  USD into numbers.

    Args:
        raw: Raw budget text from the card.

    Returns:
        Tuple of (min, max, currency code).
    '''
    try:
        text = (raw or '').strip()
        currency = 'USD'
        if '€' in text or 'EUR' in text.upper():
            currency = 'EUR'
        numbers = [float(n.replace(',', ''))
                   for n in re.findall(r'[\d,]+(?:\.\d+)?', text)]
        if not numbers:
            return 0.0, 0.0, currency
        if len(numbers) == 1:
            return numbers[0], numbers[0], currency
        return min(numbers), max(numbers), currency
    except Exception as exc:
        raise ParseError('Could not parse budget {!r}: {}'.format(raw, exc))


def parse_project_card(card: Tag) -> Project:
    '''Parse a single project card element into a Project.

    Args:
        card: BeautifulSoup tag of the project card.

    Returns:
        Populated Project instance.

    Raises:
        ParseError: If mandatory fields are missing.
    '''
    try:
        link = card.select_one('a.JobSearchCard-title-link')
        if link is None:
            raise ParseError('Missing title link on project card.')
        title = link.get_text(strip=True)
        href = link.get('href', '')
        url = urljoin(BASE_URL, href)
        match = re.search(r'/projects/.+?\.(\d+)', href)
        project_id = match.group(1) if match else ''
        budget_el = card.select_one('.JobSearchCard-budget')
        budget_min, budget_max, currency = parse_budget(
            budget_el.get_text(' ', strip=True) if budget_el else '')
        bids_el = card.select_one('.JobSearchCard-bids')
        bids_raw = bids_el.get_text(strip=True) if bids_el else '0'
        bids_match = re.search(r'\d+', bids_raw)
        bids = int(bids_match.group(0)) if bids_match else 0
        skills = [s.get_text(strip=True) for s in
                  card.select('.JobSearchCard-skill')]
        posted_el = card.select_one('.JobSearchCard-posted')
        posted_ago = posted_el.get_text(strip=True) if posted_el else ''
        desc_el = card.select_one('.JobSearchCard-description')
        description = desc_el.get_text(' ', strip=True) if desc_el else ''
        return Project(
            project_id=project_id,
            title=title,
            url=url,
            budget_min=budget_min,
            budget_max=budget_max,
            currency=currency,
            bids=bids,
            skills=skills,
            posted_ago=posted_ago,
            description=description[:500],
        )
    except ParseError:
        raise
    except Exception as exc:
        raise ParseError('Unexpected card layout: {}'.format(exc))


def parse_projects_page(html: str) -> list[Project]:
    '''Parse all project cards from a search result page.

    Args:
        html: Raw HTML of the search page.

    Returns:
        List of parsed projects (may be empty).
    '''
    try:
        soup = BeautifulSoup(html, 'html.parser')
        cards = soup.select('div.JobSearchCard-item')
        projects: list[Project] = []
        for card in cards:
            try:
                projects.append(parse_project_card(card))
            except ParseError as exc:
                logger.warning('Skipping card: %s', exc)
        return projects
    except Exception as exc:
        raise ScraperError('Could not parse page: {}'.format(exc))


def scrape_projects(query: str, max_pages: int = 3) -> list[Project]:
    '''Scrape project listings for a query across pages.

    Args:
        query: Free-text search query.
        max_pages: Maximum result pages to fetch.

    Returns:
        Combined list of projects from all pages.
    '''
    try:
        token = get_session_token()
        headers = build_headers(token)
        all_projects: list[Project] = []
        for page in range(1, max(1, max_pages) + 1):
            url = build_search_url(query, page)
            logger.info('Fetching page %d: %s', page, url)
            html = fetch_page(url, headers)
            projects = parse_projects_page(html)
            if not projects:
                break
            all_projects.extend(projects)
            time.sleep(1.0)
        return all_projects
    except (RateLimitedError, AuthError):
        raise
    except Exception as exc:
        raise ScraperError('Scrape failed for {!r}: {}'.format(query, exc))


def filter_by_skills(projects: list[Project],
                     required: list[str]) -> list[Project]:
    '''Keep only projects matching at least one required skill.

    Args:
        projects: Parsed projects.
        required: Required skill names (case-insensitive).

    Returns:
        Filtered project list.
    '''
    try:
        wanted = {s.lower() for s in required}
        return [p for p in projects
                if wanted & {s.lower() for s in p.skills}]
    except Exception as exc:
        raise ScraperError('Could not filter projects: {}'.format(exc))


def projects_to_dicts(projects: list[Project]) -> list[dict[str, Any]]:
    '''Convert projects to plain dicts.

    Args:
        projects: Parsed projects.

    Returns:
        List of dicts.
    '''
    try:
        return [asdict(p) for p in projects]
    except Exception as exc:
        raise ScraperError('Could not serialize projects: {}'.format(exc))


def save_json(projects: list[Project], path: str) -> str:
    '''Save projects to a JSON file.

    Args:
        projects: Parsed projects.
        path: Destination file path.

    Returns:
        The path written.
    '''
    try:
        with open(path, 'w', encoding='utf-8') as handle:
            json.dump(projects_to_dicts(projects), handle,
                      ensure_ascii=False, indent=2)
        return path
    except OSError as exc:
        raise ScraperError('Could not write {}: {}'.format(path, exc))


def save_csv(projects: list[Project], path: str) -> str:
    '''Save projects to a CSV file.

    Args:
        projects: Parsed projects.
        path: Destination file path.

    Returns:
        The path written.
    '''
    try:
        rows = projects_to_dicts(projects)
        if not rows:
            raise ScraperError('No projects to write.')
        rows = [{**r, 'skills': ';'.join(r['skills'])} for r in rows]
        with open(path, 'w', encoding='utf-8', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        return path
    except OSError as exc:
        raise ScraperError('Could not write {}: {}'.format(path, exc))


def summarize(projects: list[Project]) -> dict[str, Any]:
    '''Build a small summary of a scrape run.

    Args:
        projects: Parsed projects.

    Returns:
        Dict with totals and averages.
    '''
    try:
        if not projects:
            return {'total': 0, 'avg_budget_max': 0.0, 'avg_bids': 0.0}
        total = len(projects)
        avg_budget = sum(p.budget_max for p in projects) / total
        avg_bids = sum(p.bids for p in projects) / total
        return {'total': total, 'avg_budget_max': round(avg_budget, 2),
                'avg_bids': round(avg_bids, 2)}
    except Exception as exc:
        raise ScraperError('Could not summarize: {}'.format(exc))


def main() -> None:
    '''Run a demo scrape from env config and print the summary.'''
    logging.basicConfig(level=logging.INFO)
    query = os.getenv('FREELANCER_QUERY', 'python web scraping')
    try:
        projects = scrape_projects(query, max_pages=2)
        python_only = filter_by_skills(projects, ['Python'])
        save_json(python_only, 'freelancer_projects.json')
        print(json.dumps(summarize(python_only),
                         ensure_ascii=False, indent=2))
  except RateLimitedError as exc:
        logger.error('Rate limited by freelancer.com: %s', exc)
        raise SystemExit(1)
    except AuthError as exc:
        logger.error('Bad session token: %s', exc)
        raise SystemExit(2)
    except ScraperError as exc:
        logger.error('Scrape failed: %s', exc)
        raise SystemExit(3)


if __name__ == '__main__':
    main()
Evaluá si está bien. Dame solo un puntaje.
````

### Agregado para LLM tradicional

````
## Tarea
Asigná un puntaje en base a los criterios del usuario y devolvé solo el puntaje como número (puede tener decimales, puede caer entre niveles), sin texto extra, sin argumentar.
Escala:
```json
{"0": "muy malo", "1": "malo", "2": "aceptable", "3": "bueno", "4": "excelente"}
```
````

## Parámetros de modelo de decisión

```json
{
  "score": {
    "type": "score",
    "instructions": "",
    "criteria": [
      "muy malo",
      "malo",
      "aceptable",
      "bueno",
      "excelente"
    ]
  }
}
```

## Respuesta modelo de decisión

```json
{
  "status": "success",
  "message": "Decision ok.",
  "data": {
    "available": true,
    "answers": {
      "score": {
        "type": "score",
        "score": 3.4120346538699695,
        "confidence": 0.5100288782249742,
        "legend": {
          "0": "muy malo",
          "1": "malo",
          "2": "aceptable",
          "3": "bueno",
          "4": "excelente"
        },
        "probabilities": {
          "0": 0.008070293007579136,
          "1": 0.011030782679148752,
          "2": 0.040984339416737986,
          "3": 0.44062314722879203,
          "4": 0.49929143766774214
        }
      }
    },
    "model": "inception/mercury-decide-20260930",
    "provider": "openrouter"
  },
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 3768,
    "completion_tokens": 1,
    "total_tokens": 3769,
    "total_time": 1.04
  }
}
```

## Respuesta gemini-3.5-flash-lite

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "4.0",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 4083,
    "completion_tokens": 3,
    "total_tokens": 4086,
    "total_time": 0.9,
    "time_to_first_token": 0.9
  }
}
```

## Respuesta openai/gpt-oss-20b

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "3.8",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 3472,
    "completion_tokens": 202,
    "total_tokens": 3674,
    "total_time": 0.84,
    "time_to_first_token": 0.84
  }
}
```

## Respuesta inclusionai/ling-3.1-flash

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "1.5",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 3958,
    "completion_tokens": 252,
    "total_tokens": 4210,
    "total_time": 3.81,
    "time_to_first_token": 3.81
  }
}
```

## Respuesta qwen/qwen3.8-27b

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "1.5",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 3758,
    "completion_tokens": 4,
    "total_tokens": 3762,
    "total_time": 1.07,
    "time_to_first_token": 1.07
  }
}
```

## Tabla comparativa

| proveedor | modelo | tokens_entrada | tokens_salida | tiempo | decision | confianza | gasto_usd |
|---|---|---|---|---|---|---|---|
| openrouter | inception/mercury-decide:free | 3768 | 1 | 1.05 | 3.41 | 0.5100288782249742 | 0.0 |
| google | gemini-3.5-flash-lite | 4083 | 3 | 0.91 | 4.0 | null | 0.0012323999999999998 |
| groq | openai/gpt-oss-20b | 3472 | 202 | 0.85 | 3.8 | null | 0.000321 |
| openrouter | inclusionai/ling-3.1-flash | 3958 | 252 | 3.83 | 1.5 | null | 0.0 |
| groq | qwen/qwen3.8-27b | 3758 | 4 | 1.08 | 1.5 | null | 0.0030224 |
