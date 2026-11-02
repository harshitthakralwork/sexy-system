from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher
from enum import StrEnum

from app.shared.normalization import canonical_hash


class MatchClass(StrEnum):
    CONFIRMED = "confirmed"
    PROBABLE = "probable"
    POSSIBLE = "possible"
    NOT_DUPLICATE = "not_duplicate"


@dataclass(frozen=True)
class DedupKey:
    """The identity signals a record exposes, already normalised.

    Only *confirmed* pairs auto-merge. Everything weaker goes to a human,
    because merging the wrong two businesses destroys provenance that cannot be
    reconstructed (database-schema.md section 12).
    """

    name: str | None = None
    domain: str | None = None
    phone: str | None = None
    email: str | None = None
    profile_url: str | None = None
    city: str | None = None
    address: str | None = None

    def identity_keys(self) -> set[str]:
        keys = set()
        if self.domain:
            keys.add(f"domain:{self.domain}")
        if self.phone:
            keys.add(f"phone:{self.phone}")
        if self.email:
            keys.add(f"email:{self.email}")
        if self.profile_url:
            keys.add(f"profile:{self.profile_url.lower().rstrip('/')}")
        return keys


@dataclass(frozen=True)
class Candidate:
    ref: str
    key: DedupKey

    def fingerprint(self) -> str:
        return canonical_hash(self.key.name, self.key.domain, self.key.phone, self.key.email)


@dataclass(frozen=True)
class DuplicatePair:
    left_ref: str
    right_ref: str
    classification: MatchClass
    similarity: float
    reasons: tuple[str, ...]

    @property
    def auto_mergable(self) -> bool:
        return self.classification is MatchClass.CONFIRMED


def _similarity(a: str | None, b: str | None) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def compare(left: Candidate, right: Candidate) -> DuplicatePair | None:
    """Classify one pair. Returns None when they are plainly unrelated."""
    reasons: list[str] = []
    shared = left.key.identity_keys() & right.key.identity_keys()
    if shared:
        reasons.extend(sorted(shared))

    name_score = _similarity(left.key.name, right.key.name)
    address_present = bool(left.key.address and right.key.address)
    address_score = _similarity(left.key.address, right.key.address)
    same_city = bool(
        left.key.city
        and right.key.city
        and left.key.city.strip().lower() == right.key.city.strip().lower()
    )
    # Averaging in a *missing* address would report 0.47 for a near-identical
    # name, which reads as a weak match when it is not one.
    combined = (name_score + address_score) / 2 if address_present else name_score

    if shared:
        return DuplicatePair(left.ref, right.ref, MatchClass.CONFIRMED, 1.0, tuple(reasons))

    if name_score >= 0.93 and (address_score >= 0.80 or same_city):
        return DuplicatePair(
            left.ref,
            right.ref,
            MatchClass.PROBABLE,
            round(combined, 4),
            ("name_similarity", "address_or_city"),
        )

    if name_score >= 0.93:
        return DuplicatePair(
            left.ref, right.ref, MatchClass.POSSIBLE, name_score, ("name_similarity",)
        )

    if name_score >= 0.80 and same_city:
        return DuplicatePair(
            left.ref,
            right.ref,
            MatchClass.POSSIBLE,
            name_score,
            ("fuzzy_name", "same_city"),
        )

    return None


def find_duplicates(candidates: list[Candidate]) -> list[DuplicatePair]:
    """Compare candidates and return every non-trivial pair.

    Quadratic on purpose at development scale, with the cost stated rather than
    hidden: once a run exceeds a few hundred candidates this must switch to
    blocking by identity key (domain / phone / email buckets) and only compare
    inside blocks. That is tracked as Phase 2b work, not a surprise.
    """
    pairs: list[DuplicatePair] = []
    for index, left in enumerate(candidates):
        for right in candidates[index + 1 :]:
            pair = compare(left, right)
            if pair is not None:
                pairs.append(pair)
    return sorted(pairs, key=lambda pair: (-pair.similarity, pair.left_ref, pair.right_ref))


@dataclass
class DedupOutcome:
    unique_refs: list[str] = field(default_factory=list)
    merged_away: dict[str, str] = field(default_factory=dict)
    needs_review: list[DuplicatePair] = field(default_factory=list)

    @property
    def review_count(self) -> int:
        return len(self.needs_review)


def partition(candidates: list[Candidate], pairs: list[DuplicatePair]) -> DedupOutcome:
    """Collapse confirmed duplicates, queue everything uncertain for review.

    The first candidate in a confirmed chain survives, because it is the one
    with the earliest ``collected_at`` in the real pipeline; ordering is the
    caller's responsibility and is documented here rather than assumed.
    """
    outcome = DedupOutcome(unique_refs=[candidate.ref for candidate in candidates])
    parent: dict[str, str] = {candidate.ref: candidate.ref for candidate in candidates}

    def find(ref: str) -> str:
        while parent[ref] != ref:
            parent[ref] = parent[parent[ref]]
            ref = parent[ref]
        return ref

    for pair in pairs:
        if pair.auto_mergable:
            left_root, right_root = find(pair.left_ref), find(pair.right_ref)
            if left_root != right_root:
                parent[right_root] = left_root
                outcome.merged_away[right_root] = left_root
        else:
            outcome.needs_review.append(pair)

    outcome.unique_refs = sorted({find(ref) for ref in parent})
    return outcome
