# Entity-relationship diagram

Generated from the Pydantic models in `src/intensive_dance/models.py` — **do not edit by hand**. Regenerate after a model change with `uv run python -m intensive_dance.erd --write` (CI fails on drift). Companion to [`data-model.md`](./data-model.md), which is the prose source of truth.

```mermaid
erDiagram
    Offering {
        string id
        string title
        Genre[] genres "classical | contemporary | neoclassical | character | repertoire | pointe"
        Lifecycle lifecycle "scheduled | cancelled | postponed"
        string lifecycleNote
        string supersededBy
        string supersedes
        Level[] level "beginner | intermediate | advanced | pre-professional | professional | open"
        object ageRange
    }
    Source {
        string provider
        string url
        datetime scrapedAt
        string hash
    }
    Organization {
        string name
        string slug
        string country
        string city
    }
    Location {
        string venue
        string city
        string country
        boolean online
    }
    Schedule {
        string season
        date start
        date end
        string timezone
        string notes
    }
    Teacher {
        string name
        string role
    }
    Price {
        float amount
        string currency
        string label
        PriceInclude[] includes "tuition | accommodation | meals | materials | performance | studio"
        string notes
    }
    Application {
        ApplicationStatus status "open | closed | upcoming"
        date opensAt
        date deadline
        string url
        string notes
    }
    Session {
        string label
        date start
        date end
        object ageRange
        Gender gender "female | male | both"
        string notes
    }
    Affiliation {
        string organization
        string slug
        string role
        boolean current
    }
    NoneReq {
        string type "none"
    }
    PhotosReq {
        string type "photos"
        enum specificity "defined-poses | freeform"
        string[] poses
        string notes
    }
    VideoReq {
        string type "video"
        enum specificity "specific | unspecific"
        string description
    }
    CVReq {
        string type "cv"
    }
    HeadshotReq {
        string type "headshot"
    }
    Offering ||--|| Source : source
    Offering ||--|| Organization : organization
    Offering ||--o| Location : location
    Offering ||--|| Schedule : schedule
    Offering ||--o{ Teacher : teachers
    Offering ||--o{ Price : prices
    Offering ||--|| Application : application
    Schedule ||--o{ Session : sessions
    Teacher ||--o{ Affiliation : affiliations
    Application ||--o{ NoneReq : requirements
    Application ||--o{ PhotosReq : requirements
    Application ||--o{ VideoReq : requirements
    Application ||--o{ CVReq : requirements
    Application ||--o{ HeadshotReq : requirements
```
