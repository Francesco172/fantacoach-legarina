# FantaCoach - Legarina Mobile v0.5

Questa versione trasforma FantaCoach in una **Progressive Web App (PWA)** installabile su iPhone e Android.

## Cosa include

- icona FantaCoach sulla schermata Home;
- apertura a schermo intero come un'app;
- news reali e calendario tramite il backend Python;
- formazione consigliata, alert, score e "Chi schiero?";
- cache dell'interfaccia: se la rete cade, l'app può comunque aprire la UI (i dati live richiedono Internet);
- pulsante **📲 Installa app** con istruzioni per iPhone e Android;
- configurazione `render.yaml` pronta per pubblicare il backend online;
- cartella `capacitor/` pronta come base per una futura APK/IPA nativa.

## Metodo consigliato per usarla sul telefono

Per avere le news live, FantaCoach deve essere raggiungibile da Internet. Il modo più semplice è pubblicare questa cartella come Web Service.

### 1. Carica il progetto su GitHub

1. Crea un repository, per esempio `fantacoach-legarina`.
2. Carica **tutti i file di questa cartella** nella root del repository.
3. Verifica che nella root ci siano `server.py`, `index.html` e `render.yaml`.

### 2. Pubblica su Render

1. Accedi a Render.
2. Crea un nuovo **Blueprint** o **Web Service** collegato al repository GitHub.
3. Se usi Blueprint, Render leggerà automaticamente `render.yaml`.
4. Se configuri manualmente:
   - Runtime: Python
   - Build command: `echo "FantaCoach non richiede dipendenze Python esterne"`
   - Start command: `python3 server.py`
   - Health check: `/api/health`
5. Attendi il deploy.
6. Render ti darà un indirizzo HTTPS del tipo `https://nome-servizio.onrender.com`.

A quel punto FantaCoach è utilizzabile da qualsiasi telefono.

## Installazione su iPhone

1. Apri l'indirizzo HTTPS di FantaCoach in **Safari**.
2. Tocca **Condividi**.
3. Scegli **Aggiungi alla schermata Home**.
4. Attiva **Apri come app** se viene mostrato.
5. Tocca **Aggiungi**.

Comparirà l'icona FantaCoach sulla Home.

## Installazione su Android

1. Apri FantaCoach in **Chrome**.
2. Tocca il menu `⋮`.
3. Scegli **Installa app** / **Installa e crea scorciatoia**.
4. Conferma con **Installa**.

Comparirà FantaCoach tra le app e sulla schermata Home.

## Test locale sul computer

Windows: doppio clic su `avvia_fantacoach.bat`.

Mac: doppio clic su `avvia_fantacoach.command`.

Oppure:

```bash
python3 server.py
```

Poi apri `http://127.0.0.1:8787`.

## APK Android / app nativa iPhone

La cartella `capacitor/` contiene uno starter Capacitor. **Prima della build nativa devi inserire in `capacitor/www/index.html` l’URL HTTPS del backend pubblicato**, come spiegato in `capacitor/README_NATIVE.md`. Per generare progetti nativi servono poi gli strumenti ufficiali sul proprio computer.

### Android

Richiede Node.js + Android Studio / Android SDK:

```bash
cd capacitor
npm install
npx cap add android
npx cap sync
npx cap open android
```

Da Android Studio puoi generare APK/AAB.

### iPhone

Richiede un Mac con Xcode:

```bash
cd capacitor
npm install
npx cap add ios
npx cap sync
npx cap open ios
```

Per installare una build iOS su un dispositivo reale serve la firma Apple prevista da Xcode.

> Per l'uso personale, la PWA è molto più semplice: niente store e niente APK/IPA da aggiornare manualmente.

## Dati live e stime

Titoli, fonti, date e link delle news vengono recuperati dal backend. Stato, indice di titolarità, impatto sullo score e formazione consigliata sono invece elaborazioni di FantaCoach e vanno considerate stime.
