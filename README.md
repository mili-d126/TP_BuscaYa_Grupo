# BuscaYa

## Supabase setup

1. In the Supabase dashboard, open **SQL Editor**:
   - For an existing BuscaYa database created with the previous schema, back it up and run `supabase/migrations/20261116_normalize_relational_schema.sql` once. It transactionally rebuilds the two application tables, copies their rows and photos, verifies the copied row counts, then swaps in the normalized tables. A failed check rolls the transaction back.
   - For a new Supabase project, run `supabase/schema.sql`. It creates the normalized schema, authentication triggers, row-level security policies, and the public `report-photos` storage bucket.
2. Copy `.env.example` to `.env`. Set `FLASK_SECRET_KEY` to a random secret; the Supabase URL and publishable key are already filled in. The publishable key is intended for client applications; never use a Supabase secret/service-role key in this app.
3. Install the Python dependencies and start Flask:

   ```sh
   python -m pip install -r requirements.txt
   python app.py
   ```

The application schema has eight normalized tables: `roles`, `usuarios`, `tipos_reporte`, `categorias`, `estados_reporte`, `reportes`, `archivos_adjuntos`, and `comentarios`. Existing roles and report catalogs are seeded by the SQL scripts. New accounts, profiles, reports, and report photos are stored in Supabase and are shared by all app instances connected to this project. If email confirmation is enabled in Supabase Auth, new users must confirm their email before signing in.

The confirmation email returns users to the BuscaYa confirmation page. Add the app's `/confirmacion` URL (for local development, `http://localhost:5000/confirmacion`; for production, your deployed app URL) to **Authentication → URL Configuration → Redirect URLs** in Supabase. Keep the confirmation email template linked to Supabase's `{{ .ConfirmationURL }}` so Supabase verifies the link before redirecting.

Users can change their password from their profile or request a reset link from the sign-in page. Add the app's `/restablecer-contrasena` URL to Supabase's allowed Redirect URLs, and ensure the recovery email template uses Supabase's `{{ .ConfirmationURL }}` link. The reset page reads the recovery access token from the URL fragment, removes it from the address bar, and uses it to update the password.

For production, set `FLASK_DEBUG=0` and use a strong, private `FLASK_SECRET_KEY` in the hosting provider's environment settings. The existing ignored `database.db` file is no longer read or updated. For a database that predates the normalized schema, back up the project before running the one-time migration.
