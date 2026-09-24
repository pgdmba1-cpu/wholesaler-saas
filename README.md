# Wholesaler SaaS — starter scaffold

What's here so far, from the build plan:

```
wholesaler-saas/
├── db/
│   └── schema.sql          # Full Postgres schema: orgs, users, deals,
│                            # comps, buyers, matches, contracts, pipeline stages
└── backend/
    ├── requirements.txt
    └── app/
        ├── deal_analyzer.py # Core calc engine: ARV, MAO, assignment fee, viability
        └── main.py          # FastAPI app exposing POST /deals/analyze
```

## Run it

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Then:

```bash
curl -X POST http://localhost:8000/deals/analyze \
  -H "Content-Type: application/json" \
  -d '{
        "subject_sqft": 1500,
        "repair_estimate": 25000,
        "contract_price": 110000,
        "investor_margin_pct": 0.30,
        "target_assignment_fee": 10000,
        "comps": [
          {"address": "123 Main St", "sale_price": 225000, "sqft": 1480},
          {"address": "456 Oak Ave", "sale_price": 232000, "sqft": 1550},
          {"address": "789 Pine Rd", "sale_price": 218000, "sqft": 1450}
        ]
      }'
```

Returns ARV, MAO, max/projected assignment fee, end-buyer margin, and a
`is_viable` flag with plain-English notes on why a deal does or doesn't work.

## How the math works

- **ARV** = average $/sqft across your comps × subject property sqft
  (or pass `manual_arv` to skip comps entirely).
- **MAO** (max allowable offer) = `ARV × (1 - investor_margin_pct) - repair_estimate`
  — this is the classic "70% rule" with the percentage as a variable you control.
- **Assignment fee** = clamped between $0 and the headroom left between MAO
  and your contract price, so it can never show a fee that would make the
  deal unprofitable for the end buyer.

## Set up the database

```bash
createdb wholesaler_saas
psql wholesaler_saas -f db/schema.sql
```

(Or point `db/schema.sql` at a Supabase/Railway Postgres instance — no changes needed.)

## Next steps (from the build plan)

1. Wire `deal_analyzer.py` to real SQLAlchemy models so `/deals/analyze` reads/writes
   actual `deals` and `comps` rows instead of taking a raw payload.
2. Add `POST /deals` and `GET /deals/{id}` CRUD endpoints.
3. Scaffold the Next.js frontend (marketing site + app shell) and hook up
   Clerk/Supabase Auth.
4. Build the Buyer CRM endpoints + matching logic (`deal_buyer_matches`).
5. Add Dropbox Sign/DocuSign integration for `contracts`.
