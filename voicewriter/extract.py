"""Rule-based voice feature extraction from prose samples."""

from __future__ import annotations

import re
import statistics
from collections import Counter

WORD_RE = re.compile(r"[A-Za-z0-9]+(?:['\u2019][A-Za-z]+)?")

CONTRACTION_ENDINGS = (
    "n't",
    "'re",
    "'ll",
    "'ve",
    "'m",
    "'d",
    "n\u2019t",
    "\u2019re",
    "\u2019ll",
    "\u2019ve",
    "\u2019m",
    "\u2019d",
)

HEDGE_WORDS = {
    "maybe",
    "perhaps",
    "might",
    "may",
    "could",
    "seems",
    "seem",
    "likely",
    "somewhat",
    "arguably",
    "probably",
    "possibly",
    "generally",
    "usually",
    "tends",
    "tend",
    "apparently",
    "presumably",
}

FIRST_PERSON = {
    "i",
    "me",
    "my",
    "mine",
    "myself",
    "we",
    "us",
    "our",
    "ours",
    "ourselves",
}

SECOND_PERSON = {"you", "your", "yours", "yourself", "yourselves"}

STOPWORDS = {
    "the",
    "a",
    "an",
    "and",
    "or",
    "but",
    "if",
    "then",
    "than",
    "so",
    "for",
    "nor",
    "yet",
    "of",
    "at",
    "by",
    "in",
    "on",
    "to",
    "from",
    "with",
    "without",
    "as",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "being",
    "have",
    "has",
    "had",
    "do",
    "does",
    "did",
    "will",
    "would",
    "shall",
    "should",
    "can",
    "could",
    "may",
    "might",
    "must",
    "it",
    "its",
    "this",
    "that",
    "these",
    "those",
    "i",
    "you",
    "he",
    "she",
    "they",
    "we",
    "me",
    "him",
    "her",
    "us",
    "them",
    "my",
    "your",
    "his",
    "our",
    "their",
    "not",
    "no",
    "yes",
    "just",
    "also",
    "very",
    "really",
    "about",
    "into",
    "over",
    "under",
    "again",
    "more",
    "most",
    "other",
}


def words(text: str) -> list[str]:
    """Return lowercased word tokens, keeping contractions together."""
    return [m.group(0).lower() for m in WORD_RE.finditer(text)]


def sentences(text: str) -> list[str]:
    """Split prose into sentences on terminal punctuation or line breaks."""
    cleaned = text.replace("\r", " ").replace("\n", " ")
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", cleaned) if part.strip()]


def paragraphs(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]


def _formality_score(
    long_word_ratio: float,
    contraction_rate: float,
    hedge_rate: float,
    passive_rate: float,
    second_person_rate: float,
) -> float:
    score = 0.0
    score += min(long_word_ratio * 3.0, 0.3)
    score += min(hedge_rate * 0.04, 0.2)
    score += min(passive_rate * 0.05, 0.2)
    if contraction_rate < 0.5:
        score += 0.15
    if second_person_rate < 0.8:
        score += 0.15
    return max(0.0, min(1.0, score))


def formality_label(score: float) -> str:
    if score < 0.35:
        return "casual"
    if score < 0.55:
        return "conversational"
    if score < 0.75:
        return "balanced"
    return "formal"


def extract_features(text: str) -> dict:
    """Extract a normalized voice fingerprint from a block of prose."""
    ws = words(text)
    sents = sentences(text)
    paras = paragraphs(text)

    word_count = len(ws)
    unique = len(set(ws))
    ttr = unique / word_count if word_count else 0.0
    word_lengths = [len(w) for w in ws]
    avg_word_len = statistics.fmean(word_lengths) if word_lengths else 0.0
    long_word_ratio = sum(1 for length in word_lengths if length > 7) / word_count if word_count else 0.0

    sent_lengths = [len(words(s)) for s in sents]
    avg_sentence_len = statistics.fmean(sent_lengths) if sent_lengths else 0.0
    sentence_std = statistics.pstdev(sent_lengths) if len(sent_lengths) > 1 else 0.0
    short_sentence_ratio = (
        sum(1 for length in sent_lengths if length < 8) / len(sent_lengths)
        if sent_lengths
        else 0.0
    )
    long_sentence_ratio = (
        sum(1 for length in sent_lengths if length > 25) / len(sent_lengths)
        if sent_lengths
        else 0.0
    )

    para_sentence_counts = [len(sentences(p)) for p in paras]
    avg_para_len = statistics.fmean(para_sentence_counts) if para_sentence_counts else 0.0

    per_100 = lambda count: (count / word_count * 100) if word_count else 0.0

    contraction_count = sum(1 for w in ws if w.endswith(CONTRACTION_ENDINGS))
    hedge_count = sum(1 for w in ws if w in HEDGE_WORDS)
    low = text.lower()
    hedge_count += low.count("sort of") + low.count("kind of")

    first_person = sum(1 for w in ws if w in FIRST_PERSON)
    second_person = sum(1 for w in ws if w in SECOND_PERSON)

    passive_hints = len(re.findall(r"\b(?:is|are|was|were|been|being)\s+\w+ed\b", low))

    content_words = [w for w in ws if w not in STOPWORDS]
    bigrams = Counter(zip(content_words, content_words[1:]))
    trigrams = Counter(zip(content_words, content_words[1:], content_words[2:]))
    signature = [
        " ".join(ngram)
        for ngram, count in (bigrams + trigrams).most_common(10)
        if count >= 2
    ]

    formality = _formality_score(
        long_word_ratio=long_word_ratio,
        contraction_rate=per_100(contraction_count),
        hedge_rate=per_100(hedge_count),
        passive_rate=per_100(passive_hints),
        second_person_rate=per_100(second_person),
    )

    return {
        "word_count": word_count,
        "unique_words": unique,
        "type_token_ratio": round(ttr, 4),
        "avg_word_length": round(avg_word_len, 2),
        "long_word_ratio": round(long_word_ratio, 4),
        "sentence_count": len(sents),
        "avg_sentence_length": round(avg_sentence_len, 2),
        "sentence_length_std": round(sentence_std, 2),
        "short_sentence_ratio": round(short_sentence_ratio, 4),
        "long_sentence_ratio": round(long_sentence_ratio, 4),
        "paragraph_count": len(paras),
        "avg_paragraph_sentences": round(avg_para_len, 2),
        "comma_per_100": round(per_100(text.count(",")), 2),
        "semicolon_per_100": round(per_100(text.count(";")), 2),
        "colon_per_100": round(per_100(text.count(":")), 2),
        "em_dash_per_100": round(per_100(text.count("\u2014")), 2),
        "en_dash_per_100": round(per_100(text.count("\u2013")), 2),
        "question_per_100": round(per_100(text.count("?")), 2),
        "exclamation_per_100": round(per_100(text.count("!")), 2),
        "parenthesis_per_100": round(per_100(text.count("(") + text.count(")")), 2),
        "contractions_per_100": round(per_100(contraction_count), 2),
        "hedging_per_100": round(per_100(hedge_count), 2),
        "first_person_per_100": round(per_100(first_person), 2),
        "second_person_per_100": round(per_100(second_person), 2),
        "passive_hints_per_100": round(per_100(passive_hints), 2),
        "formality": round(formality, 4),
        "signature_phrases": signature,
    }


def style_markers(features: dict) -> list[str]:
    """Translate a feature fingerprint into human-readable style markers."""
    markers: list[str] = []
    if features["em_dash_per_100"] >= 1.0:
        markers.append("Heavy em-dash user - joins clauses with dashes.")
    elif features["em_dash_per_100"] >= 0.3:
        markers.append("Uses em-dashes occasionally.")
    if features["short_sentence_ratio"] >= 0.4:
        markers.append("Favors short, punchy sentences.")
    elif features["long_sentence_ratio"] >= 0.3:
        markers.append("Favors longer, flowing sentences.")
    if features["contractions_per_100"] >= 2.0:
        markers.append("Uses contractions naturally.")
    elif features["contractions_per_100"] < 0.5:
        markers.append("Mostly avoids contractions (more formal).")
    if features["second_person_per_100"] >= 1.5:
        markers.append("Speaks directly to the reader.")
    if features["first_person_per_100"] >= 3.0:
        markers.append("Strong first-person presence.")
    if features["hedging_per_100"] >= 1.0:
        markers.append("Frequent hedging (maybe, might, perhaps).")
    if features["exclamation_per_100"] >= 0.8:
        markers.append("Uses exclamation marks for emphasis.")
    if features["question_per_100"] >= 1.5:
        markers.append("Asks questions, often rhetorical.")
    if features["semicolon_per_100"] >= 0.5:
        markers.append("Uses semicolons.")
    if features["type_token_ratio"] >= 0.65:
        markers.append("Rich, varied vocabulary.")
    elif features["type_token_ratio"] < 0.4:
        markers.append("Repetitive, familiar vocabulary.")
    if features["avg_word_length"] >= 5.5:
        markers.append("Prefers longer, more complex words.")
    elif features["avg_word_length"] < 4.2:
        markers.append("Prefers plain, accessible words.")
    return markers


def build_voice_instructions(name: str, features: dict, markers: list[str]) -> str:
    """Build an LLM-ready instruction block describing the author's voice."""
    register = formality_label(features["formality"])
    lines = [
        f'## Voice instructions for "{name}"',
        "",
        f"- Register: {register} (formality {features['formality']:.2f}).",
        f"- Sentence rhythm: {features['avg_sentence_length']} words average; "
        f"{features['short_sentence_ratio'] * 100:.0f}% short (<8 words), "
        f"{features['long_sentence_ratio'] * 100:.0f}% long (>25 words).",
        f"- Paragraph rhythm: about {features['avg_paragraph_sentences']} sentences per paragraph.",
        f"- Punctuation (per 100 words): commas {features['comma_per_100']}, "
        f"em-dashes {features['em_dash_per_100']}, semicolons {features['semicolon_per_100']}, "
        f"questions {features['question_per_100']}, exclamations {features['exclamation_per_100']}.",
        f"- Pronouns: first-person {features['first_person_per_100']}/100w, "
        f"second-person {features['second_person_per_100']}/100w.",
        f"- Contractions: {features['contractions_per_100']}/100w; "
        f"hedging: {features['hedging_per_100']}/100w.",
        f"- Vocabulary: {features['type_token_ratio']:.2f} type-token ratio, "
        f"{features['avg_word_length']} letters/word average.",
    ]
    if features.get("signature_phrases"):
        phrases = ", ".join(f'"{phrase}"' for phrase in features["signature_phrases"][:8])
        lines.append(f"- Signature phrases (reuse sparingly): {phrases}.")
    if markers:
        lines.append("")
        lines.append("Style markers:")
        lines.extend(f"- {marker}" for marker in markers)
    lines.append("")
    lines.append(
        "Match this rhythm, punctuation, pronoun, contraction and hedging profile "
        "when writing in this voice. Reuse signature phrases only when they fit "
        "naturally - do not force them."
    )
    return "\n".join(lines)
