"""Text-level checks for Devanagari data: script mix, malformed sequences, PII-like patterns,
duplicate detection. Heuristics only: every finding is a *flag for a human*, not a verdict."""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict

DEP_VOWEL = {chr(c) for c in range(0x093E, 0x094D)} | {"ॢ", "ॣ"}
MARKS = DEP_VOWEL | {"ऀ", "ँ", "ं", "ः", "़", "्"}
ZW = {"‌", "‍"}
DEV_DIGITS = "०१२३४५६७८९"
_WS = re.compile(r"\s+")

EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
URL = re.compile(r"(?:https?://|www\.)\S+", re.I)
# Matched after Devanagari digits are mapped to ASCII. Nepali mobile: 9[78]xxxxxxxx, optional +977.
PHONE = re.compile(r"(?<!\d)(?:(?:\+|00)977[-\s]?)?9[78]\d{8}(?!\d)")
LONG_ID = re.compile(r"(?<!\d)\d{9,}(?!\d)")
HANDLE = re.compile(r"(?<!\w)@\w{3,}")

_DIGIT_MAP = {ord(c): str(i) for i, c in enumerate(DEV_DIGITS)}


def normalize_for_dedup(text: str) -> str:
    t = unicodedata.normalize("NFC", text)
    t = "".join(c for c in t if c not in ZW).translate(_DIGIT_MAP).casefold()
    t = "".join(c for c in t if not unicodedata.category(c).startswith("P"))
    return _WS.sub(" ", t).strip()


def is_dev(ch: str) -> bool:
    return "ऀ" <= ch <= "ॿ"


def script_ratio(text: str) -> tuple[float, float]:
    """(devanagari share, latin share) of letters/marks."""
    dev = lat = 0
    for ch in text:
        if is_dev(ch) and (ch.isalpha() or unicodedata.category(ch).startswith("M")):
            dev += 1
        elif ch.isascii() and ch.isalpha():
            lat += 1
    n = dev + lat
    return (dev / n, lat / n) if n else (0.0, 0.0)


def devanagari_issues(text: str) -> list[str]:
    issues: list[str] = []
    if "�" in text:
        issues.append("contains U+FFFD replacement character (encoding damage)")
    if any(unicodedata.category(c) == "Cc" and c not in "\n\t" for c in text):
        issues.append("contains control characters")
    for w in text.split():
        stripped = w.lstrip("‌‍")
        if stripped and stripped[0] in MARKS and stripped[0] != "ऀ":
            issues.append(f"word starts with a combining mark: {w!r}")
        for a, b in zip(w, w[1:], strict=False):
            if a in DEP_VOWEL and b in DEP_VOWEL:
                issues.append(f"two dependent vowel signs in a row: {w!r}")
                break
        if w[0] in ZW or w[-1] in ZW:
            issues.append(f"stray zero-width joiner/non-joiner at word edge: {w!r}")
    dev_d = sum(c in DEV_DIGITS for c in text)
    asc_d = sum(c.isdigit() and c.isascii() for c in text)
    if dev_d and asc_d:
        issues.append("mixes Devanagari and ASCII digits")
    return issues


def legacy_font_suspect(text: str) -> bool:
    """Latin-only text full of symbols inside words, typical of Preeti-style legacy fonts."""
    dev, lat = script_ratio(text)
    if dev > 0 or lat == 0:
        return False
    odd = sum(text.count(c) for c in "{}[]|\\;`~")
    return odd >= 2 and odd / max(len(text), 1) > 0.03


def pii_flags(text: str) -> list[str]:
    flags = []
    raw, text = text, text.translate(_DIGIT_MAP)
    if EMAIL.search(raw):
        flags.append("email address")
    if URL.search(raw):
        flags.append("URL")
    if PHONE.search(text):
        flags.append("phone number")
    elif LONG_ID.search(text):
        flags.append("long digit sequence (possible ID / account number)")
    if HANDLE.search(raw):
        flags.append("@handle")
    return flags


def shingles(text: str, n: int = 3) -> set[str]:
    t = normalize_for_dedup(text).replace(" ", "")
    if len(t) < n:
        return {t} if t else set()
    return {t[i : i + n] for i in range(len(t) - n + 1)}


def near_duplicates(texts: dict[str, str], threshold: float = 0.85) -> list[tuple[str, str, float]]:
    """Pairs (id_a, id_b, jaccard) over character 3-gram shingles, via an inverted index
    so it stays fast for tens of thousands of short records."""
    sh = {k: shingles(v) for k, v in texts.items()}
    index: dict[str, list[str]] = defaultdict(list)
    out: list[tuple[str, str, float]] = []
    done: set[tuple[str, str]] = set()
    for k, s in sh.items():
        counts: dict[str, int] = defaultdict(int)
        for g in s:
            for other in index[g]:
                counts[other] += 1
        for other, c in counts.items():
            if (other, k) in done:
                continue
            union = len(s) + len(sh[other]) - c
            j = c / union if union else 0.0
            if j >= threshold:
                out.append((other, k, round(j, 3)))
                done.add((other, k))
        for g in s:
            index[g].append(k)
    return out


_END_MARKS = ("\u0964", "?", "!", "\u0965")


def punctuation_issues(text: str, kind: str | None) -> list[str]:
    """Mechanical punctuation checks for sentence-like records. Heuristic: a flag, not a verdict
    (informal writing legitimately varies; reviewers decide)."""
    issues: list[str] = []
    t = text.strip()
    if kind in ("sentence", "paragraph", "dialogue") and t:
        if t.endswith("."):
            issues.append("ends with '.'; Nepali sentences normally end with '\u0964' (danda)")
        elif not t.endswith(_END_MARKS) and len(t.split()) > 2:
            issues.append("sentence has no ending mark (\u0964 / ? / !)")
    if " \u0964" in t or " ?" in t or " !" in t:
        issues.append("space before the sentence-ending mark")
    if "\u0964\u0964" in t or "..." in t:
        issues.append("repeated end marks or ellipsis")
    return issues
