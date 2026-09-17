# Node seed datasets

Loaded by `hospital-node seed --dataset <name>` (ARCHITECTURE §21). Hand-maintained JSON, no importer.

- `demo_ksp/articles.json` — the 10 rows of the client's sample article list
  (`sample-challenge-v01`, Tabelle3), converted once from the CSV with every value kept exactly
  as exported, including the Excel apostrophe in GTIN/EAN. **Client data: the repository must stay
  private.**
- `demo_spital2/articles.json` — 2 synthetic articles for the second tenant (isolation tests).
- `users.json` — demo accounts without passwords; `seed` gives every account
  `NODE_SEED_PASSWORD` from the node's `.env`.
