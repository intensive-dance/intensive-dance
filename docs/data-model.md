# Data model

One scraped record = **one offering** of an intensive or master class (i.e. a specific program in a specific year). A school's "Summer Intensive 2026" and "Summer Intensive 2027" are two records.

Stored as JSON. The interesting part is `application.requirements`, which is a **tagged union** so we can capture "photos in defined poses" vs. "open-brief video" without losing structure.

## Shape

```jsonc
{
  "id": "royal-ballet-school/summer-intensive-2026",   // {providerSlug}/{offeringSlug}
  "source": {
    "provider": "royal-ballet-school",                  // FK into providers.json
    "url": "https://www.royalballetschool.org.uk/...",  // canonical page scraped
    "scrapedAt": "2026-06-03T10:00:00Z",
    "hash": "sha256:…"                                   // of the meaningful fields, for change detection
  },

  "title": "Summer Intensive 2026",
  "genres": ["classical", "contemporary"],              // enum: classical | contemporary | neoclassical | character | repertoire | pointe
  "kind": "intensive",                                  // enum: intensive | masterclass | summer-school | workshop | audition-tour
  "level": ["advanced", "pre-professional"],            // enum: beginner | intermediate | advanced | pre-professional | professional | open
  "ageRange": { "min": 16, "max": 19 },                 // null bound = open-ended

  "organization": {
    "name": "The Royal Ballet School",
    "slug": "royal-ballet-school",
    "country": "GB",                                    // ISO 3166-1 alpha-2
    "city": "London"
  },

  "location": {                                         // where it physically runs (may differ from org HQ)
    "venue": "White Lodge, Richmond Park",
    "city": "London",
    "country": "GB",
    "online": false
  },

  "schedule": {
    "season": "2026",                                   // human label for the offering cycle
    "start": "2026-07-20",                              // ISO date; null if announced-but-undated
    "end": "2026-08-07",
    "timezone": "Europe/London",
    "sessions": [                                        // optional: multi-block intensives
      { "label": "Week 1", "start": "2026-07-20", "end": "2026-07-24" }
    ]
  },

  "teachers": [
    {
      "name": "Jane Doe",
      "role": "guest teacher",                          // their role in THIS intensive
      "affiliations": [                                 // where they actually teach / dance
        { "organization": "The Royal Ballet", "slug": "the-royal-ballet", "role": "principal dancer", "current": true },
        { "organization": "The Royal Ballet School", "role": "faculty", "current": true }
      ]
    }
  ],

  "prices": [
    {
      "amount": 2500,                                   // integer minor-unit-free; use decimals only if the source does
      "currency": "GBP",                                // ISO 4217
      "label": "Tuition",
      "includes": ["tuition", "studio"],                // enum-ish: tuition | accommodation | meals | materials | performance
      "notes": "Excludes accommodation."
    }
  ],

  "application": {
    "opensAt": "2025-11-01",                            // nullable
    "deadline": "2026-03-01",                           // nullable
    "url": "https://…/apply",
    "requirements": [
      { "type": "none" },
      { "type": "photos",   "specificity": "defined-poses", "poses": ["first arabesque", "à la seconde", "tendu devant"], "notes": "On pointe where applicable." },
      { "type": "photos",   "specificity": "freeform" },
      { "type": "video",    "specificity": "specific",   "description": "Barre + center adage and allegro, set combinations provided." },
      { "type": "video",    "specificity": "unspecific", "description": "A solo of the applicant's choice." },
      { "type": "cv" },
      { "type": "headshot" }                            // === portrait
    ]
  }
}
```

## `application.requirements` — the tagged union

Each entry has a `type`; the rest of the fields depend on it. An empty array means "unknown / not stated"; a single `{ "type": "none" }` means "explicitly no requirements".

| `type`     | extra fields                                                        | meaning |
|------------|---------------------------------------------------------------------|---------|
| `none`     | —                                                                   | explicitly no application material required |
| `photos`   | `specificity`: `defined-poses` \| `freeform`; `poses?: string[]`    | stills; `poses` lists the required positions when defined |
| `video`    | `specificity`: `specific` \| `unspecific`; `description?: string`   | `specific` = set combinations/brief; `unspecific` = applicant's choice |
| `cv`       | —                                                                   | résumé / training history |
| `headshot` | —                                                                   | headshot / portrait photo |

Keep raw source text in `notes` whenever we have to interpret/normalize, so we can re-derive if the enum grows.

## Why this shape

- **One offering per record** keeps year-over-year and per-session changes diffable via `source.hash`.
- **`teachers[].affiliations`** is the explicit answer to "where they actually teach and dance" — separate from their role *in the intensive*.
- **`prices` is a list** because schools quote tuition / accommodation / early-bird separately.
- **Requirements as a union** preserves the structure the platform will eventually filter on (e.g. "no video required").
