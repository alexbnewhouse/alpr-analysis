"""Harvard Dataverse downloads, including guestbook-gated files.

Some datasets (MEDSL county returns, Jacob Kaplan's UCR archive) require a
*guestbook* response before the file will download. There is no account or API
token involved -- the depositor uses it for download tracking -- but it does
transmit your name, email, institution, and free-text answers to Harvard.

That makes it a disclosure, so nothing here has defaults: an
:class:`Identity` must be constructed explicitly by the caller. A pipeline
should never submit one silently on a user's behalf.

The payload shape is undocumented in the API guides; it was read off the
Dataverse source (``JsonParser.parseGuestbookResponse``). Custom answers go in
an ``answers`` array of ``{"id": <customQuestionId>, "value": ...}``, and a
``textarea`` question must receive a **list of lines** -- passing a bare string
raises a ClassCastException server-side.
"""

from __future__ import annotations

import logging
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import requests

log = logging.getLogger(__name__)

DATAVERSE = "https://dataverse.harvard.edu"
ACCESS = f"{DATAVERSE}/api/access/datafile"
GUESTBOOKS = f"{DATAVERSE}/api/guestbooks"
USER_AGENT = "alpr-research-pipeline/1.0 (academic research)"


@dataclass(frozen=True)
class Identity:
    """Who to declare on a guestbook form. All fields are disclosed."""

    name: str
    email: str
    institution: str
    position: str = "Researcher"
    #: Answers to the guestbook's custom questions, keyed by question id.
    answers: tuple[tuple[int, str], ...] = ()

    def __post_init__(self) -> None:
        if not (self.name and self.email and self.institution):
            raise ValueError(
                "name, email and institution are all disclosed to Harvard "
                "Dataverse and must be supplied explicitly."
            )


def describe_guestbook(guestbook_id: int) -> dict:
    """Fetch a guestbook definition: required fields and custom questions.

    Call this before constructing an Identity so you know exactly what will be
    asked and what will be sent.
    """
    resp = requests.get(f"{GUESTBOOKS}/{guestbook_id}",
                        headers={"User-Agent": USER_AGENT}, timeout=60)
    resp.raise_for_status()
    return resp.json()["data"]


def fetch_datafile(file_id: int, dest: Path,
                   identity: Identity | None = None,
                   textarea_ids: frozenset[int] = frozenset()) -> Path:
    """Download a Dataverse file, using a guestbook response only if required.

    Tries an anonymous GET first. Only if the server refuses with a guestbook
    error does it fall back to submitting `identity` -- so a file that happens
    to be ungated never causes a disclosure.
    """
    dest = Path(dest)
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)

    anon = requests.get(f"{ACCESS}/{file_id}", stream=True, timeout=1800,
                        headers={"User-Agent": USER_AGENT})
    if anon.ok:
        _stream_to(anon, dest)
        log.info("Cached %s (%.1f MB, no guestbook)",
                 dest.name, dest.stat().st_size / 1e6)
        return dest
    anon.close()

    if identity is None:
        raise PermissionError(
            f"Datafile {file_id} requires a guestbook response and no Identity "
            f"was supplied. Server said: {anon.text[:200]}"
        )

    log.warning(
        "Submitting a guestbook response to dataverse.harvard.edu for file %d. "
        "This discloses name=%r, email=%r, institution=%r.",
        file_id, identity.name, identity.email, identity.institution,
    )

    answers = [
        {"id": qid, "value": [value] if qid in textarea_ids else value}
        for qid, value in identity.answers
    ]
    resp = requests.post(
        f"{ACCESS}/{file_id}",
        json={"guestbookResponse": {
            "name": identity.name,
            "email": identity.email,
            "institution": identity.institution,
            "position": identity.position,
            "answers": answers,
        }},
        headers={"User-Agent": USER_AGENT, "Content-Type": "application/json"},
        timeout=300,
    )
    if not resp.ok:
        raise RuntimeError(
            f"Guestbook submission for file {file_id} failed "
            f"({resp.status_code}): {resp.text[:300]}"
        )

    signed = resp.json()["data"]["signedUrl"]
    # The signed URL carries its own token; requests' session headers are not
    # needed and urllib keeps the query string byte-identical.
    req = urllib.request.Request(signed, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=1800) as fh, open(dest, "wb") as out:
        while chunk := fh.read(1 << 20):
            out.write(chunk)

    log.info("Cached %s (%.1f MB, via guestbook)",
             dest.name, dest.stat().st_size / 1e6)
    return dest


def _stream_to(resp: requests.Response, dest: Path) -> None:
    with resp, open(dest, "wb") as fh:
        for chunk in resp.iter_content(chunk_size=1 << 20):
            fh.write(chunk)
