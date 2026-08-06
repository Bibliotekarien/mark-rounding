"""Pydantic request bodies."""

from pydantic import BaseModel
from pydantic import Field


class LoginIn(BaseModel):
    password: str


class RegattaIn(BaseModel):
    name: str = Field(min_length=1)
    venue: str = ""
    organizer: str = ""
    lat: float | None = None
    lon: float | None = None
    start_date: str | None = None
    end_date: str | None = None
    sailarena_url: str = ""
    race_count: int = Field(default=1, ge=1, le=50)
    marks: list[str] = []


class RegattaPatch(BaseModel):
    name: str | None = None
    venue: str | None = None
    organizer: str | None = None
    lat: float | None = None
    lon: float | None = None
    start_date: str | None = None
    end_date: str | None = None
    sailarena_url: str | None = None
    race_count: int | None = Field(default=None, ge=1, le=50)


class BoatIn(BaseModel):
    sail_number: str = Field(min_length=1)
    boat_name: str = ""
    boat_type: str = ""
    skipper: str = ""
    club: str = ""
    nation: str = ""
    srs: str = ""
    active: bool = True


class BoatPatch(BaseModel):
    sail_number: str | None = None
    boat_name: str | None = None
    boat_type: str | None = None
    skipper: str | None = None
    club: str | None = None
    nation: str | None = None
    srs: str | None = None
    active: bool | None = None


class MarksIn(BaseModel):
    marks: list[str] = Field(min_length=1)


class RoundingIn(BaseModel):
    mark_id: int
    boat_id: int


class RaceStatusIn(BaseModel):
    status: str = Field(pattern="^(upcoming|ongoing|finished)$")


class StartSequenceIn(BaseModel):
    minutes: int = Field(default=5, ge=1, le=60)
    prep_flag: str = Field(default="P", pattern="^(P|I|Z|U|BLACK)$")


class BoatStatusIn(BaseModel):
    # OCS = tjuvstart, UFD/BFD = U-/svart flagg, ZFP = 20 %-straff,
    # DNS/DNF/RET/DSQ = klassiska resultatkoder.
    code: str = Field(pattern="^(OCS|UFD|BFD|ZFP|DNS|DNF|RET|DSQ)$")


class LogNoteIn(BaseModel):
    note: str = Field(min_length=1, max_length=2000)


class SailarenaPreviewIn(BaseModel):
    url: str = Field(min_length=8)


class BoatsImportIn(BaseModel):
    boats: list[BoatIn]
    replace: bool = False
