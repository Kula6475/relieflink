# ReliefLink hosted application

This directory is the primary hosted Next.js application and the ATLAS MVP. Neon
Postgres is its only persistent source of truth. The root FastAPI/SQLite application is
retained as a prototype and as the stateless OR-Tools/Claude service during migration.

## Local key-free demo

```bash
cd vision_agent/web
npm install
cp .env.example .env.local
npm run dev
```

Keep `ATLAS_SYNTHETIC_MODE=true`, then open <http://localhost:3000>. The disruption,
request, offers, logistics validation, allocation, four human approvals, reservation,
and audit timeline work without Neon or API keys. Image review also has a synthetic
package-detection path.

## Persistent Neon setup

1. Create a Neon project and copy its pooled connection string to `DATABASE_URL`.
2. Generate `AUTH_SECRET` with `openssl rand -base64 32`.
3. Set `ATLAS_SYNTHETIC_MODE=false`.
4. Run `npm run db:migrate && npm run db:seed`.
5. Start the app and sign in using `ATLAS_DEMO_ADMIN_EMAIL` and
   `ATLAS_DEMO_ADMIN_PASSWORD` from your local environment.

The migration is additive. Never reset the hosted database to apply it.

## Optional services

Run `uvicorn ledger.main:app --reload` from the repository root to expose the stateless
OR-Tools endpoint and Claude explanation/follow-up node. Both have key-free fallbacks.
For cloud still-image analysis, configure Roboflow for package-level detection and
OpenAI for label/category interpretation. A generic detector is not treated as a SKU
classifier.

The demo defaults to the public `supermarket-shelves-7eum5/2` package detector with
`YOLO_COUNT_CLASSES=Product`. Replace it with a validated or fine-tuned food-bank model
for production; the public model is only a package-level MVP baseline.

## Vercel

Create or update a Vercel project with **Root Directory** set to `vision_agent/web`.
Add the environment variables from `.env.example`; do not upload or commit `.env`.
Run Neon migrations separately before switching the deployment out of synthetic mode.

## Checks

```bash
npm test
npm run typecheck
npm run build
```
