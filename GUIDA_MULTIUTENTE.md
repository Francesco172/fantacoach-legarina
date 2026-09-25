# FantaCoach v0.8 — attivazione Multi‑utente

La v0.8 funziona subito anche in **modalità locale**. In questa modalità la tua Legarina resta disponibile sul singolo dispositivo.

Per permettere a persone diverse di registrarsi dal proprio telefono e conservare ognuna la propria rosa, serve un database cloud. Il progetto è già predisposto per **Supabase Auth + Postgres**.

## 1. Crea un progetto Supabase

1. Vai su `https://supabase.com` e accedi.
2. Crea un nuovo progetto.
3. Attendi che il progetto sia pronto.

## 2. Crea le tabelle

1. In Supabase apri **SQL Editor**.
2. Crea una nuova query.
3. Copia tutto il contenuto del file `supabase_setup.sql`.
4. Esegui la query.

Le policy RLS fanno sì che un utente autenticato possa leggere e modificare soltanto le proprie squadre e le proprie rose.

## 3. Recupera i due valori pubblici

In Supabase apri **Project Settings → API** e copia:

- Project URL → sarà `SUPABASE_URL`
- anon/public key → sarà `SUPABASE_ANON_KEY`

**Non usare e non inserire la service_role key.**

## 4. Inserisci le variabili su Render

Nel servizio Render `fantacoach-legarina` apri **Environment** e aggiungi:

- `SUPABASE_URL` = Project URL di Supabase
- `SUPABASE_ANON_KEY` = anon/public key di Supabase

Salva. Render farà un nuovo deploy.

## 5. Configura il link di conferma email

In Supabase apri **Authentication → URL Configuration**.

Imposta come **Site URL** il tuo indirizzo Render, per esempio:

`https://fantacoach-legarina.onrender.com`

Aggiungi lo stesso indirizzo tra i redirect consentiti. In questo modo, se Supabase richiede la conferma email, il link riporta correttamente a FantaCoach.

## 6. Prova

Apri FantaCoach. Dovresti vedere **Accedi / Registrati**.

Dopo esserti registrato puoi:

- premere **Importa la mia Legarina (25)** per caricare la rosa già costruita;
- oppure creare una squadra nuova e aggiungere i giocatori uno a uno;
- ogni altro utente può registrare un account diverso e avrà dati separati.

## Come viene aggiunto un giocatore

Apri **Gestisci rosa**, digita nome/cognome e scegli il risultato. FantaCoach usa un catalogo locale più una ricerca online TheSportsDB. Se la ricerca non trova il giocatore, puoi usare **Aggiunta manuale** indicando nome, club e ruolo.

Il ruolo trovato online è una stima derivata dalla posizione calcistica: prima di aggiungere il giocatore puoi cambiarlo in POR/DIF/CEN/ATT.

## Email di conferma

Supabase può richiedere la conferma via email per i nuovi account. In quel caso il nuovo utente riceve l'email, conferma l'indirizzo e poi accede a FantaCoach.
