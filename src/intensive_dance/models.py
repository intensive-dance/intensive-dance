"""Pydantic models for a scraped intensive offering.

Mirrors docs/data-model.md. One `Offering` == one offering of an intensive /
master class in a specific year. The `application.requirements` list is a
discriminated union so "photos in defined poses" and "open-brief video" keep
their structure instead of collapsing to free text.
"""

from __future__ import annotations

import hashlib
import re
from datetime import date, datetime, timezone
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, model_validator

Genre = Literal["classical", "contemporary", "neoclassical", "character", "repertoire", "pointe"]
# Whether the offering itself takes place — separate from `application.status`
# (which is about the booking window). "past" is NOT a value: it's derived from
# `schedule.end < today` so it never goes stale. `postponed` keeps the original
# record (with `supersededBy`) alongside a new-date one (with `supersedes`).
Lifecycle = Literal["scheduled", "cancelled", "postponed"]
Level = Literal["beginner", "intermediate", "advanced", "pre-professional", "professional", "open"]
PriceInclude = Literal["tuition", "accommodation", "meals", "materials", "performance", "studio"]
# Category of a single Price line: the course charge (`tuition`) vs the gate fee
# paid just to apply (`registration`), a `deposit`, a standalone `accommodation`
# or `meals` charge, or `other`. Distinct from `includes`, which lists what a
# *tuition* charge bundles. Auto-derived from `includes`+`label` when a scraper
# doesn't set it (see `_classify_price_type`), so it stays stable across re-scrapes.
PriceType = Literal["tuition", "registration", "deposit", "accommodation", "meals", "other"]
# Application cycle state. `closed` covers a cycle still listed but no longer
# accepting applications; `upcoming` = announced but not yet open.
ApplicationStatus = Literal["open", "closed", "upcoming"]
# `both` == offered to female and male dancers (also the default when the source
# is silent on gender).
Gender = Literal["female", "male", "both"]


# --- application.requirements: tagged union on `type` ---


class NoneReq(BaseModel):
    type: Literal["none"] = "none"


class PhotosReq(BaseModel):
    type: Literal["photos"] = "photos"
    specificity: Literal["defined-poses", "freeform"]
    poses: list[str] = Field(default_factory=list)
    notes: str | None = None


class VideoReq(BaseModel):
    type: Literal["video"] = "video"
    specificity: Literal["specific", "unspecific"]
    description: str | None = None


class CVReq(BaseModel):
    type: Literal["cv"] = "cv"


class HeadshotReq(BaseModel):
    """Headshot / portrait photo."""

    type: Literal["headshot"] = "headshot"


Requirement = Annotated[
    NoneReq | PhotosReq | VideoReq | CVReq | HeadshotReq,
    Field(discriminator="type"),
]


# --- supporting blocks ---


class Source(BaseModel):
    provider: str  # FK into providers.json
    url: str
    scraped_at: datetime = Field(alias="scrapedAt")  # last time content changed
    attempted_at: datetime | None = Field(
        default=None, alias="attemptedAt"
    )  # last fetch attempt (rotation cursor)
    hash: str | None = None

    model_config = {"populate_by_name": True}


class Organization(BaseModel):
    name: str
    slug: str
    country: str  # ISO 3166-1 alpha-2
    city: str | None = None


class Location(BaseModel):
    venue: str | None = None
    city: str | None = None
    country: str | None = None
    online: bool | None = None  # set True only for online programs; omitted otherwise


class Session(BaseModel):
    label: str | None = None
    start: date | None = None
    end: date | None = None
    age_range: dict | None = Field(default=None, alias="ageRange")  # null bound = open-ended
    gender: Gender | None = None
    notes: str | None = None  # raw source text for this block (ages/gender normalized)

    model_config = {"populate_by_name": True}


class Schedule(BaseModel):
    season: str
    start: date | None = None
    end: date | None = None
    timezone: str | None = None
    sessions: list[Session] = Field(default_factory=list)
    notes: str | None = None  # raw dates text, kept because dates are normalized to ISO


class Affiliation(BaseModel):
    organization: str
    slug: str | None = None
    role: str | None = None
    current: bool | None = None


class Teacher(BaseModel):
    name: str
    role: str | None = None  # role in THIS intensive
    affiliations: list[Affiliation] = Field(default_factory=list)


_FEE_RX = re.compile(
    r"appl|regist|enrol|inscri|iscriz|matric|anmeld|einschreib|\bfee\b", re.IGNORECASE
)
_DEPOSIT_RX = re.compile(r"deposit|anzahl|acconto|caparra|down.?payment", re.IGNORECASE)
_ACCOM_RX = re.compile(
    r"accommod|housing|lodging|\broom\b|residen|unterkunft|alloggi", re.IGNORECASE
)
_MEAL_RX = re.compile(r"\bmeal|\bboard\b|verpfleg|catering|\bfood\b", re.IGNORECASE)


def _classify_price_type(includes: list[str], label: str | None) -> PriceType:
    """Category of a price from the signals a scraper already produces. A
    `tuition`-tagged charge is the course price; otherwise classify by label
    (registration/deposit) or a standalone accommodation/meals `includes` tag.
    Deterministic, so re-scrapes re-derive the same value (no churn)."""
    if "tuition" in (includes or []):
        return "tuition"
    inc = set(includes or [])
    lab = label or ""
    if _DEPOSIT_RX.search(lab):
        return "deposit"
    if _FEE_RX.search(lab):
        return "registration"
    if "accommodation" in inc or _ACCOM_RX.search(lab):
        return "accommodation"
    if "meals" in inc or _MEAL_RX.search(lab):
        return "meals"
    return "other"


class Price(BaseModel):
    amount: float
    currency: str  # ISO 4217
    label: str | None = None
    type: PriceType = "tuition"  # category; auto-derived from includes/label when unset
    includes: list[PriceInclude] = Field(default_factory=list)
    notes: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _derive_type(cls, data: Any) -> Any:
        if isinstance(data, dict) and not data.get("type"):
            return {
                **data,
                "type": _classify_price_type(data.get("includes") or [], data.get("label")),
            }
        return data


class Application(BaseModel):
    status: ApplicationStatus | None = None  # None == not stated
    opens_at: date | None = Field(default=None, alias="opensAt")
    deadline: date | None = None
    url: str | None = None
    # [] == unknown/not stated; [NoneReq] == explicitly nothing required.
    requirements: list[Requirement] = Field(default_factory=list)
    notes: str | None = None  # raw deadline/booking text (e.g. "Applications are now closed.")

    model_config = {"populate_by_name": True}


class Offering(BaseModel):
    id: str  # {providerSlug}/{offeringSlug}
    source: Source
    title: str
    genres: list[Genre] = Field(default_factory=list)
    lifecycle: Lifecycle = "scheduled"
    lifecycle_note: str | None = Field(
        default=None, alias="lifecycleNote"
    )  # raw source text, e.g. "Cancelled — full refund"
    superseded_by: str | None = Field(
        default=None, alias="supersededBy"
    )  # id of the replacement (postponed → new)
    supersedes: str | None = None  # id of the original this replaces (new → postponed)
    level: list[Level] = Field(default_factory=list)
    age_range: dict | None = Field(default=None, alias="ageRange")
    organization: Organization
    location: Location | None = None
    schedule: Schedule
    teachers: list[Teacher] = Field(default_factory=list)
    prices: list[Price] = Field(default_factory=list)
    application: Application = Field(default_factory=Application)

    model_config = {"populate_by_name": True}

    def content_hash(self) -> str:
        """Stable hash of the meaningful fields, for change detection.

        Excludes `source` (url/scraped_at/hash) so a re-scrape of unchanged
        content yields the same hash.
        """
        payload = self.model_dump(by_alias=True, exclude={"source"}, mode="json")
        digest = hashlib.sha256(_canonical(payload).encode()).hexdigest()
        return f"sha256:{digest}"


def _canonical(value: object) -> str:
    import json

    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)
