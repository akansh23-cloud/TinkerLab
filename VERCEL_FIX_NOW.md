# TinkerLab — Vercel Fix

The `tinker-lab` Vercel project must deploy the Next.js application from:

`apps/web`

In Vercel:
1. Open `cloud14/tinker-lab`.
2. Settings → Build and Deployment.
3. Set **Root Directory** to `apps/web`.
4. Set Framework Preset to **Next.js** (or leave framework auto-detection after Root Directory is corrected).
5. Leave Build Command and Output Directory at their Next.js defaults.
6. Save.
7. Settings → Deployment Protection.
8. If the production site should be public, disable Vercel Authentication for the production deployment/domain.
9. Deployments → Redeploy the latest `develop` commit without the old build cache.

The API should be a second Vercel project from the same repository:
- Root Directory: `apps/api`
- Entrypoint: `app.py`
- Framework: FastAPI/Python

Never commit real `DATABASE_URL`, Materials Project keys, EPA keys, or other credentials to GitHub.
Use Vercel Project Settings → Environment Variables.
