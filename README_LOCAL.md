# Saloni Tiwari â€” Digital Portfolio (Improved v5)

A clean, mobile-responsive personal portfolio with a private admin area. The public site starts with **one profile photo only**; projects, certificates, education, achievements, skills, learning journey, social/coding profiles and gallery items are intentionally empty until the owner adds them.

## Included

- Public portfolio with responsive sections that appear only when content exists.
- Private admin login (`/login`) â€” deliberately not shown in public navigation.
- Dashboard with add/edit/delete and publish/hide controls for Projects, Certificates, Education, Achievements, Skills, Learning Journey, Media Gallery and Social/Coding Profiles.
- Certificate credential URL and credential ID fields.
- Project GitHub and live-demo URL fields.
- Education document upload, achievement badge/image upload, profile screenshot upload and gallery media upload.
- Profile settings for name, headline, introduction, email, location and one replaceable profile image.
- CSRF protection, HTTP-only session cookie, secure cookie option, login attempt throttling, URL scheme validation, safe random upload filenames, file size/type allow-list and baseline security headers.
- SQLite for local development; PostgreSQL supported through `DATABASE_URL`.
- Local `.env` loading for secrets; `.env` is excluded from Git.
- Static profile image and uploaded PNG/JPG/WebP images are resized and optimized as WebP using Pillow. GIF animation, PDFs and videos retain their original formats.
- `/health` health-check endpoint.

## Run locally (Windows PowerShell)

1. Install Python 3.11 or newer.
2. Open this folder in VS Code.
3. In Terminal run:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
notepad .env
```

In `.env`, replace the sample `SECRET_KEY` and `ADMIN_PASSWORD` values with your own unique, strong values, save the file, then start the app:

```powershell
python app.py
```

The app loads `.env` automatically. Do not commit `.env`; only `.env.example` belongs in Git.

4. Open `http://127.0.0.1:5000`.
5. Admin login: `http://127.0.0.1:5000/login`.

Do not commit your real password, `SECRET_KEY`, database URL or other secrets to GitHub.

## Render deployment

This version is **not safe for durable uploads on a Render Free Web Service**. Render Free uses an ephemeral filesystem; uploaded files and a local SQLite database can disappear after spin-down, restart or redeploy. Free web services also spin down after 15 minutes idle. A Free Render Postgres database expires after 30 days. See Render's official limitations: https://render.com/docs/free

Recommended straightforward setup for this Flask version:

1. Create a PostgreSQL database with a production-ready plan (for example Supabase Pro or a suitable managed Postgres provider).
2. Deploy this repository to Render as a Web Service.
3. Set Build Command: `pip install -r requirements.txt`.
4. Set Start Command: `gunicorn --workers 2 --threads 4 --timeout 60 app:app`.
5. Set environment variables: `SECRET_KEY` (long random secret), `ADMIN_USERNAME`, `ADMIN_PASSWORD`, `DATABASE_URL` (PostgreSQL connection string), `COOKIE_SECURE=1`, `DATA_DIR=/var/data`, `UPLOAD_DIR=/var/data/uploads`. Production environment variables override local `.env` values.
6. Attach a **paid Render persistent disk** mounted at `/var/data`. The database stores structured records; the disk stores uploaded media. Render persistent disks are only available on paid services and are single-instance storage, so this deployment cannot horizontally scale the web service while that disk is attached. See https://render.com/docs/disks
7. After deployment, check `/health`, then sign in at `/login` and add a test item/upload. Redeploy and verify the item and file still exist before adding all real content.

If you need horizontal scaling and reliable 50â€“100 concurrent visitors, move uploads to object storage (S3-compatible storage) and run the app on a scalable paid service. This code has not yet been load-tested; no honest 50â€“100-user capacity guarantee can be made from source inspection alone.

## Important security and operational notes

- Set a unique, strong `SECRET_KEY` and `ADMIN_PASSWORD` before any public deployment. Never reuse a password from another account.
- Admin routes require a session. The public header contains no admin/login link.
- The current version uses local disk for uploaded media. Back up `/var/data/uploads` as well as the PostgreSQL database.
- Use HTTPS in production and set `COOKIE_SECURE=1`.
- Keep the Python dependencies updated and review security advisories before major upgrades.
- This is a complete starter implementation, but a formal penetration test, accessibility audit, backup-restore drill and concurrent-user load test remain deployment validation tasks.

## Content workflow

1. Open `/login` and sign in.
2. Use the dashboard to open a manager.
3. Add content and decide whether it should be visible publicly.
4. Use Profile Settings to update the intro and replace the single profile photo.
5. Visit the public homepage on desktop and mobile to review the result.

## Existing portfolio preservation

This is a separate v5 project folder. It does not overwrite the existing v3 repository or live website. Keep v3 online until v4 has been deployed, populated with owner-approved content and tested.

## Image optimization

- The bundled profile portrait is served as WebP.
- Uploaded PNG, JPG, JPEG and WebP images are validated, resized to fit within 1600 Ã— 1600 pixels, and stored as WebP at quality 82.
- Animated GIFs, PDFs and videos retain their original formats. Uploads are limited to 20 MB before processing.

