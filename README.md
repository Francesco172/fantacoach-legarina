# FantaCoach v0.8 Multi‑utente

Novità principali:

- registrazione e login con Supabase;
- ogni utente vede solo le proprie squadre;
- possibilità di gestire più squadre con lo stesso account;
- import rapido della rosa Legarina già configurata;
- creazione autonoma di nuove squadre;
- gestione rosa con aggiunta/rimozione giocatori;
- ricerca giocatore locale + TheSportsDB;
- scelta/override del ruolo Classic prima dell'inserimento;
- aggiunta manuale se un calciatore non è trovato;
- dashboard live calcolata sulla rosa della squadra selezionata;
- modalità locale di fallback finché Supabase non è configurato.

## Deploy

Il servizio continua a partire con:

`python3 server.py`

Per attivare il vero multi‑utente segui `GUIDA_MULTIUTENTE.md` ed esegui `supabase_setup.sql` su Supabase.

Le variabili richieste su Render sono:

- `SUPABASE_URL`
- `SUPABASE_ANON_KEY`

Non inserire mai una chiave `service_role` nel frontend o nelle variabili esposte all'app.
