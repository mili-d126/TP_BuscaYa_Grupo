# BuscaYa

## Supabase setup

1. In the Supabase dashboard, open **SQL Editor**, paste in `supabase/schema.sql`, and run it. This creates the profile and report tables, authentication triggers, row-level security policies, and the public `report-photos` storage bucket.
2. Copy `.env.example` to `.env`. Set `FLASK_SECRET_KEY` to a random secret; the Supabase URL and publishable key are already filled in. The publishable key is intended for client applications; never use a Supabase secret/service-role key in this app.
(If .env File is included, this step can be skiped.)
3. Install the Python dependencies and start Flask:

   ```sh
   python -m pip install -r requirements.txt
   python app.py
   ```

New accounts, profiles, reports, and report photos are stored in Supabase and are shared by all app instances connected to this project. If email confirmation is enabled in Supabase Auth, new users must confirm their email before signing in.

The confirmation email returns users to the BuscaYa confirmation page. Add the app's `/confirmacion` URL (for local development, `http://localhost:5000/confirmacion`; for production, your deployed app URL) to **Authentication → URL Configuration → Redirect URLs** in Supabase. Keep the confirmation email template linked to Supabase's `{{ .ConfirmationURL }}` so Supabase verifies the link before redirecting.

Users can change their password from their profile or request a reset link from the sign-in page. Add the app's `/restablecer-contrasena` URL to Supabase's allowed Redirect URLs, and ensure the recovery email template uses Supabase's `{{ .ConfirmationURL }}` link. The reset page reads the recovery access token from the URL fragment, removes it from the address bar, and uses it to update the password.

For production, set `FLASK_DEBUG=0` and use a strong, private `FLASK_SECRET_KEY` in the hosting provider's environment settings. The existing ignored `database.db` file is no longer read or updated. Its existing users and reports are not migrated automatically; re-register users through the app and migrate any reports separately if they need to be retained.
