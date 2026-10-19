# Bot Anagrafe

Bot Telegram per la gestione del registro cittadini di una simulazione politica.

Tiene l'elenco dei cittadini in un database SQLite, gestisce le richieste di
cittadinanza con approvazione da parte degli amministratori, cura il Registro
Pubblico delle Attività, e registra ogni modifica su un canale Telegram di log.

## Table of Contents

- [Bot Anagrafe](#bot-anagrafe)
  - [Table of Contents](#table-of-contents)
  - [Funzionalità](#funzionalità)
  - [Requisiti](#requisiti)
  - [Installazione](#installazione)
  - [Configurazione](#configurazione)
  - [Avvio](#avvio)
  - [Comandi](#comandi)
    - [Per tutti](#per-tutti)
    - [Amministratori](#amministratori)
    - [Root](#root)
  - [La pulsantiera `/menu`](#la-pulsantiera-menu)
  - [Import da CSV](#import-da-csv)
  - [Ruoli e amministratori](#ruoli-e-amministratori)
  - [Registro Pubblico delle Attività](#registro-pubblico-delle-attività)
  - [Log su canale](#log-su-canale)
  - [Note su Telegram](#note-su-telegram)
  - [Test](#test)
  - [Struttura del progetto](#struttura-del-progetto)
    - [Schema del database](#schema-del-database)


---

## Funzionalità

- **Registro dei cittadini** consultabile da chiunque (`/elenco_cittadini`, `/cerca_cittadino`) ed
  esportabile in **Markdown o CSV** (`/esporta_cittadini`).
- **Import ed export per entrambi i registri**: cittadini e attività si
  scaricano e si ricaricano con gli stessi due formati. Il CSV prodotto
  dall'export si reimporta così com'è.
- **Richieste di cittadinanza** (`/richiedi_cittadinanza`): ogni amministratore riceve una
  notifica in privato con i pulsanti *Accetta* / *Rifiuta*. Quando uno decide,
  la notifica si aggiorna per tutti gli altri e il richiedente viene avvisato.
- **Gestione del registro** riservata agli amministratori: inserimento singolo
  (`/inserisci_cittadino`), rimozione (`/rimuovi_cittadino`) e **import di massa da CSV**
  (`/importa_cittadini`).
- **Registro Pubblico delle Attività** (`/registra_attivita`, `/elenco_attivita`):
  ogni cittadino iscrive gratuitamente la propria organizzazione, associazione
  o attività privata. L'iscrizione è immediata, la scheda viene pubblicata
  sulla Gazzetta Ciompista e il Ministero dell'Interno può rifiutarla o
  eliminarla d'ufficio *dopo* (vedi sotto). Il proprietario può ritirare la
  propria attività con `/rimuovi_attivita`.
- **Tre livelli di autorizzazione**: pubblico, amministratore, root.
- **Pulsantiera guidata a due livelli** (`/menu`): prima si sceglie l'area
  (*Cittadinanza*, *Attività*, *Amministrazione*), poi l'azione. Esegue tutti i
  comandi senza doverne ricordare la sintassi, chiedendo i dati un campo alla
  volta.
- **Nomi dei comandi espliciti**: ogni comando dice su cosa opera
  (`/elenco_cittadini` e `/elenco_attivita`, non `/elenco`).
- **Niente ID da copiare a mano**: rimuovere un cittadino o un'attività, e
  moderarla, si fa scegliendo da un elenco di pulsanti con nomi e tag.
- **Aiuto dinamico** (`/help`): mostra solo i comandi che chi lo invoca può
  davvero usare.
- **Username sempre aggiornati**: a ogni interazione con il bot (in privato,
  in un gruppo o premendo un pulsante) il `@username` di un cittadino viene
  aggiornato nel registro. Un tag appartiene a un solo utente alla volta: se lo
  prende qualcun altro, viene tolto al cittadino che lo aveva prima.
- **Il tag al posto dell'ID**: `/rimuovi_cittadino`, `/aggiungi_admin` e `/rimuovi_admin`
  accettano anche `@username` (di un cittadino) oltre all'ID.
- **Ricerca per parole**: `/cerca_cittadino Mario Rossi` (in qualunque ordine, ignorando
  maiuscole e accenti); se non trova nulla propone i nomi più simili.
- **Errori subito**: un'operazione destinata a fallire (es. richiedere la
  cittadinanza quando la si ha già, rimuovere un ID inesistente) lo dice prima
  di chiedere altri dati.
- **Log su canale**: ogni inserimento, rimozione, richiesta e cambio di
  username viene scritto su un canale Telegram scelto.

---

## Requisiti

- Python 3.10 o superiore
- Un bot Telegram creato con [@BotFather](https://t.me/BotFather)

---

## Installazione

```bash
git clone <url-del-repository>
cd bot-anagrafe

python -m venv .venv
source .venv/bin/activate        # su Windows: .venv\Scripts\activate

pip install -r requirements.txt
```

---

## Configurazione

Copia `.env.example` in `.env` e riempi i valori:

```bash
cp .env.example .env
```

| Variabile | Obbligatoria | Descrizione |
|---|---|---|
| `TOKEN_CITIZENS_BOT` | ✅ | Token del bot, fornito da @BotFather. |
| `ROOT_ADMIN_ID` | ✅ | ID Telegram numerico dell'utente root. Per scoprirlo scrivi a [@userinfobot](https://t.me/userinfobot). |
| `LOG_CHANNEL_ID` | — | Canale su cui registrare le modifiche: ID numerico (`-1001234567890`) o `@nomecanale`. Se vuoto, il log su canale è disattivato. |
| `GAZZETTA_CHANNEL_ID` | — | Canale della Gazzetta Ciompista, dove viene pubblicata una scheda per ogni attività iscritta: ID numerico o `@nomecanale`. Se vuoto, le attività vengono registrate ma non pubblicate. |
| `ANAGRAFE_DB_PATH` | — | Percorso del database SQLite. Default: `./registro.db`. |
| `ANAGRAFE_ADMINS_PATH` | — | Percorso dell'elenco amministratori. Default: `./admins.txt`. |

Se manca una variabile obbligatoria il bot non parte e dice quale.

---

## Avvio

```bash
python -m anagrafe
```

Al primo avvio il database viene creato automaticamente. Per fermare il bot:
`Ctrl+C`.

---

## Comandi

### Per tutti

| Comando | Cosa fa |
|---|---|
| `/start` | Presentazione del bot e comandi disponibili. |
| `/help` | Elenco dei comandi che *tu* puoi usare. |
| `/menu` | Apre la pulsantiera guidata. |
| `/elenco_cittadini` | Elenco completo dei cittadini (nome, cognome, username). |
| `/esporta_cittadini [md \| csv]` | Invia il registro dei cittadini come file. Senza argomento è Markdown. |
| `/cerca_cittadino <testo>` | Cerca per nome e/o cognome (in qualunque ordine), `@username`, `#ID` o ID Telegram. Senza risultati esatti propone i nomi più simili. |
| `/richiedi_cittadinanza <nome>, <cognome>` | Invia una richiesta di cittadinanza. |
| `/registra_attivita` | Iscrive una tua attività al Registro Pubblico. Procedura guidata a passi; richiede la cittadinanza. |
| `/elenco_attivita` | Elenco delle attività iscritte al Registro Pubblico. |
| `/rimuovi_attivita <ID_attività>` | Ritira una tua attività dal Registro. Un amministratore può usarlo su qualunque attività. |
| `/esporta_attivita [md \| csv]` | Invia il Registro delle Attività come file. Contiene le attività attive. |

### Amministratori

| Comando | Cosa fa |
|---|---|
| `/inserisci_cittadino <ID_telegram>, <username>, <nome>, <cognome>` | Inserisce un cittadino. Lo username può essere lasciato vuoto. |
| `/rimuovi_cittadino <ID_cittadino | ID_telegram | @username>` | Rimuove il cittadino indicato per ID cittadino (il numero dopo `#`), ID Telegram o tag. |
| `/tagga_cittadini` | Menziona tutti i cittadini che hanno uno username. |
| `/importa_cittadini` | Importa più cittadini da un file CSV (vedi sotto). |
| `/importa_attivita` | Importa più attività da un file CSV (vedi sotto). |
| `/modera_attivita <ID_attività>` | Rimanda la scheda di un'attività con i pulsanti *Rifiuta* / *Elimina*, utile se la notifica è andata perduta. |

### Root

| Comando | Cosa fa |
|---|---|
| `/aggiungi_admin <ID_telegram \| @username>` | Promuove un utente ad amministratore (il tag deve essere di un cittadino). |
| `/rimuovi_admin <ID_telegram \| @username>` | Revoca i privilegi di amministratore. |
| `/elenco_admin` | Mostra gli amministratori configurati. |

---

## La pulsantiera `/menu`

`/menu` chiede prima **l'area** e poi l'azione, così le operazioni sui cittadini
non si confondono con quelle sulle attività:

```
⌨️ Pulsantiera comandi          👥 Cittadinanza
                                 👥 Elenco      📤 Esporta
Scegli l'area su cui      →      🔍 Cerca       📝 Richiedi
vuoi operare.                    ➕ Inserisci   ❌ Rimuovi
                                 📣 Tagga tutti 📥 Importa CSV
👥 Cittadinanza
🏪 Attività                      ⬅️ Indietro    ✖️ Chiudi
👮 Amministrazione
✖️ Chiudi
```

- Compaiono **solo le aree in cui il tuo ruolo ha qualcosa da fare**: un
  cittadino non vede «Amministrazione».
- Dentro un'area compaiono solo i comandi che puoi usare. L'area dice di che
  cosa si parla, il ruolo dice chi può agire: per questo i comandi riservati
  agli amministratori che riguardano i cittadini stanno in «Cittadinanza», non
  in «Amministrazione».
- Navigare fra le aree **riscrive lo stesso messaggio** invece di aggiungerne
  uno: la pulsantiera resta un solo messaggio in chat.
- Eseguito un comando, si torna **all'area da cui si era partiti**. `/menu`
  ricomincia invece dalla scelta dell'area.
- I comandi senza parametri (`/elenco_cittadini`, `/esporta_cittadini`, `/elenco_admin`) partono
  subito.
- Gli altri aprono un **wizard**: il bot chiede un valore alla volta
  («Qual è il nome?», «Qual è il cognome?»), valida ogni risposta e chiude con
  un riepilogo da confermare. I campi facoltativi hanno un pulsante *Salta*.
- Alcuni campi si compilano **a pulsanti** invece che a mano. Le scelte fisse
  sono dichiarate nel registro dei comandi (la tipologia di un'attività); altre
  vengono **lette dal registro al momento della domanda**, perché dipendono dai
  dati e da chi sta chiedendo:

  ```
  🗑 rimuovi_attivita
  Passo 1 di 1

  Quale attività vuoi rimuovere?

  (3 voci; puoi anche scrivere la risposta)

    💼 Pizzeria Da Mario
    🤝 Circolo dei Ciompi
    🏢 Cooperativa Arno
    ❌ Annulla
  ```

  Oltre le otto voci la tastiera si impagina con le frecce `⬅️ 2/5 ➡️`.
  Si può sempre scrivere la risposta invece di premere: il bot continua ad
  accettare `#ID`, `@username` e ID Telegram dove li accettava prima.
- Chi può scegliere che cosa è deciso dagli stessi controlli che poi eseguono
  l'operazione: in `/rimuovi_attivita` un cittadino vede solo le proprie
  attività, un amministratore tutte. Una tastiera che mostrasse voci poi
  rifiutate sarebbe peggio di nessuna tastiera.
- Se non c'è nulla da scegliere (nessuna attività da ritirare, registro vuoto)
  il bot lo dice e non avvia la procedura.
- Alcuni comandi (`/registra_attivita`) entrano **direttamente nel proprio wizard**
  quando li digiti, senza passare dalla pulsantiera. Il testo scritto dopo il
  comando viene ignorato: i dati si danno un passo alla volta.
- *Annulla* interrompe in qualsiasi momento; il comando `/annulla` fa lo stesso.
- Dopo 5 minuti di inattività il wizard scade da solo.

I permessi vengono ricontrollati al momento del click, non solo quando la
pulsantiera è stata disegnata.

---

## Export: Markdown o CSV

`/esporta_cittadini` e `/esporta_attivita` chiedono in che formato vuoi il file,
con due pulsanti:

- **📝 Markdown** — una tabella da leggere, col cognome in maiuscolo come in
  tutti gli elenchi del bot;
- **📊 CSV** — un file di scambio, da aprire in un foglio di calcolo o da
  **ricaricare con l'import**.

Dalla pulsantiera l'export parte appena scegli il formato: non c'è una conferma
da dare, perché non modifica nulla. Dai comandi puoi anche scrivere il formato
di seguito (`/esporta_cittadini csv`); senza argomento è Markdown, come è
sempre stato.

Il CSV usa le stesse intestazioni che l'import riconosce, quindi **un registro
esportato in CSV si reimporta senza ritoccarlo**. È l'invariante che lega i due
comandi, e due test la verificano facendo il giro completo. Il file porta il BOM
UTF-8, così Excel non storpia i nomi accentati, e nel CSV i dati non vengono
alterati (il cognome resta come è scritto nel registro).

L'export delle attività contiene le sole attività **attive**: è quello che il
pubblico vede, ed è anche ciò che l'import riaccetta.

---

## Import da CSV

Invia il file `.csv` al bot **allegandolo in chat con didascalia
`/importa_cittadini`** o **`/importa_attivita`** (oppure premi *Importa CSV*
nella sezione giusta del menu e poi manda il file). È la didascalia, o il
comando che hai appena premuto, a dire al bot in quale registro mettere le
righe.

Colonne attese per i **cittadini**:

```csv
ID Telegram,Username,Nome,Cognome
123456789,@mariorossi,Mario,Rossi
987654321,,Anna,Verdi
```

Colonne attese per le **attività**:

```csv
Nome,Tipologia,Descrizione,Contatto,Proprietario
Pizzeria Da Mario,Attività Privata,Pizza al taglio,@pizzeria,123456789
Circolo dei Ciompi,Associazione,Letture collettive,,#3
```

Per le attività valgono le stesse due regole dell'iscrizione singola: il
**proprietario deve essere un cittadino** già iscritto (si indica con l'ID
Telegram, `#ID cittadino` o `@username`), e lo stesso proprietario non può
avere due attività attive con lo stesso nome. Le righe che violano una delle
due vengono **saltate con il motivo**, non importate a metà.

Le attività importate **non vengono pubblicate sulla Gazzetta Ciompista** e non
generano notifiche al Ministero: un file da cinquanta righe produrrebbe
cinquanta post e cinquanta messaggi per amministratore, e Telegram limita gli
invii. Il resoconto lo dice esplicitamente.

Il parser è volutamente tollerante:

- riconosce l'intestazione anche con nomi equivalenti (`telegram_id`, `id`,
  `first name`, `utente`…) e in qualsiasi ordine di colonne;
- se non trova un'intestazione, legge le colonne nell'ordine
  `Telegram ID, Username, Nome, Cognome`;
- accetta `,` `;` o tabulazione come separatore, e file UTF-8 (anche con BOM)
  o Windows-1252;
- ignora le righe completamente vuote, comprese quelle tipo `,,,` che i fogli
  di calcolo mettono spesso in cima al file.

Al termine ricevi un resoconto con quante righe sono state **inserite**, quante
**saltate** e l'elenco delle **righe non valide** con il numero di riga e il
motivo. Né i cittadini già registrati né le attività omonime vengono duplicati,
quindi rilanciare lo stesso import è innocuo.

Limiti: solo file con estensione `.csv`, massimo 2 MB.

---

## Ruoli e amministratori

| Ruolo | Come si ottiene |
|---|---|
| **root** | È l'ID nella variabile `ROOT_ADMIN_ID`. Uno solo, non rimovibile. |
| **amministratore** | Il suo ID Telegram compare in `admins.txt`, una riga per ID. |
| **pubblico** | Tutti gli altri. |

Il root è sempre anche amministratore, anche se non compare in `admins.txt`.

`admins.txt` viene riletto a ogni controllo: puoi modificarlo a mano senza
riavviare il bot. Le righe vuote e quelle che iniziano con `#` sono ignorate.

```
# amministratori del registro
123456789
987654321
```

---

## Registro Pubblico delle Attività

Istituito dal **Decreto Ministeriale n. 3 del 13 ottobre 2026**. L'iscrizione è
gratuita e **non richiede approvazione preventiva**: il controllo del Ministero
dell'Interno è *successivo*.

**1. Iscrizione** — `/registra_attivita` (o il pulsante *Registra attività* in `/menu`)
apre una procedura guidata che chiede nome, tipologia (*Organizzazione*,
*Associazione*, *Attività Privata*, scelta con i pulsanti), descrizione e un
contatto facoltativo, e si chiude con un riepilogo da confermare. È riservata
ai **cittadini già iscritti all'anagrafe**: a chi non lo è il bot risponde
rimandandolo a `/richiedi_cittadinanza`. Ogni cittadino può iscrivere più attività, ma non
due attive con lo stesso nome.

**2. Pubblicazione** — alla conferma l'attività è subito attiva e la sua scheda
viene pubblicata sulla **Gazzetta Ciompista** (il canale di
`GAZZETTA_CHANNEL_ID`). Se il canale non è configurato o non è raggiungibile
l'attività viene iscritta comunque, e il bot lo dice: il Registro vive nel
database, la Gazzetta ne è una vista.

**3. Consultazione** — `/elenco_attivita` elenca le attività attive. Come
`/elenco_cittadini`, non genera menzioni: gli username in elenco non notificano nessuno.
Nella scheda pubblicata in Gazzetta, invece, il contatto è un tag vero.

**4. Ritiro** — `/rimuovi_attivita` toglie un'attività dal Registro. Dalla
pulsantiera si sceglie dall'elenco delle proprie attività, senza cercarne l'ID;
il comando accetta comunque `/rimuovi_attivita 7` per chi preferisce digitare.
Chi può usarlo non dipende dal ruolo ma dalla **proprietà**: il cittadino sulle
proprie attività, l'amministratore su qualunque. Chi indica un'attività che non
è sua riceve lo stesso messaggio che riceverebbe per un ID inesistente, così un
ID indovinato non rivela nulla.

I due casi restano distinti negli atti:

| Chi | Stato nel database |
|---|---|
| il proprietario, sulla propria | `CHIUSA` (ritiro volontario) |
| un amministratore, su quella di un altro | `RIMOSSA` (atto d'ufficio, con avviso al proprietario) |

Un amministratore che ritira la *propria* attività fa un ritiro volontario, non
un atto d'ufficio: lo stato dipende da chi agisce, non dal ruolo che ha.

**5. Correzione: si rimuove e si reimmette** — non esiste un comando per
modificare un'attività. Per correggerla si usa `/rimuovi_attivita` e poi di
nuovo `/registra_attivita`: il vincolo «un nome per proprietario» vale solo fra
le attività attive, quindi il nome torna subito disponibile. Da sapere: la
nuova iscrizione ha un **ID diverso** e un **post nuovo** in Gazzetta, e fa
ripartire la notifica al Ministero. Per un registro pubblico è il comportamento
corretto — una voce corretta è una voce nuova — ma l'ID cambia.

**6. Moderazione** — appena un'attività è iscritta, ogni amministratore
(il Ministero dell'Interno) riceve in privato la sua scheda con due pulsanti:

- **❌ Rifiuta** — la voce è illegittima o legata a un profilo non riconosciuto;
- **➖ Elimina** — la voce va rimossa d'ufficio dal Registro.

In entrambi i casi il bot aggiorna la copia della notifica di *tutti* gli
amministratori, toglie il post dalla Gazzetta, avvisa il proprietario e scrive
sul canale di log. Il record resta nel database con lo stato `RIFIUTATA` o
`RIMOSSA`, insieme a chi ha deciso e quando: la moderazione resta agli atti, e
il nome torna libero. Se due amministratori premono il pulsante nello stesso
istante vince il primo, e il secondo riceve un avviso.

Il post in Gazzetta viene **cancellato**. Se Telegram non lo consente più (un
post oltre le 48 ore, il bot rimosso dal canale) viene riscritto segnalando la
rimozione d'ufficio; se non riesce nemmeno quello, il bot lo dice
all'amministratore e lo annota nel log — ma la moderazione nel database resta
valida in ogni caso.

---

## Log su canale

Se imposti `LOG_CHANNEL_ID`, il bot scrive sul canale un messaggio per ogni:

- nuova richiesta di cittadinanza, e ogni accettazione / rifiuto / annullamento;
- inserimento o rimozione di un cittadino;
- import CSV andato a buon fine;
- iscrizione, ritiro, rifiuto o eliminazione di un'attività del Registro Pubblico;
- promozione o revoca di un amministratore;
- aggiornamento automatico di uno username (anche quando un tag passa a un altro utente).

Se il canale non è raggiungibile l'errore viene solo annotato nei log locali:
il comando dell'utente non fallisce mai per colpa del log.

---

## Note su Telegram

Tre inciampi che non dipendono dal bot ma dalla piattaforma:

1. **Un amministratore riceve le notifiche delle richieste solo se ha già
   avviato una chat privata col bot.** Se non l'ha mai fatto, deve premere
   `/start` in privato. Il bot avvisa quando non riesce a raggiungere qualcuno.
2. **Per scrivere sul canale di log, il bot deve esserne amministratore.** Lo
   stesso vale per la Gazzetta Ciompista, dove gli serve anche il permesso di
   **eliminare i propri messaggi**, altrimenti i post delle attività rimosse
   possono solo essere riscritti.
3. **Per aggiornare gli username anche dai messaggi di gruppo, la *privacy
   mode* va disattivata** da @BotFather (*Bot Settings → Group Privacy → Turn
   off*). Con la privacy mode attiva il bot non vede i messaggi di gruppo che
   non lo menzionano: l'aggiornamento avviene comunque, ma solo quando il
   cittadino usa il bot.

---

## Test

```bash
pip install -r requirements-dev.txt
python -m pytest
```

I test coprono la logica del bot — registro, ruoli, validazione degli
argomenti, parsing CSV, formattazione dei messaggi e registro dei comandi — e
non richiedono né un token né una connessione a Telegram.

---

## Struttura del progetto

```
anagrafe/
├── __main__.py        avvio: configurazione, handler, polling
├── config.py          lettura di .env e delle variabili d'ambiente
├── db.py              connessione SQLite e schema
├── repository.py      tutte le query sul registro
├── roles.py           ruoli e file admins.txt
├── commands.py        registro dei comandi (fonte unica di /help e /menu)
├── validators.py      validazione degli argomenti
├── controlli.py       controlli fail-fast e risoluzione di #ID / @tag
├── formatting.py      escape e impaginazione dei messaggi
├── csv_import.py      primitive CSV e import dei cittadini
├── csv_attivita.py    import delle attività da CSV
├── esportazione.py    produzione dei file di export (Markdown e CSV)
├── logbook.py         log sul canale Telegram
└── handlers/
    ├── azioni.py      le azioni, condivise fra comandi e pulsantiera
    ├── controlli.py   quali controlli girano a ogni passo del wizard
    ├── comandi.py     i comandi testuali
    ├── menu.py        la pulsantiera e il wizard
    ├── richieste.py   accettazione e rifiuto delle richieste
    ├── attivita.py    Registro delle Attività: iscrizione e moderazione
    ├── gazzetta.py    pubblicazione delle schede sul canale pubblico
    ├── notifiche.py   notifiche agli admin e aggiornamento delle copie
    ├── scelte.py      le voci che la pulsantiera legge dal registro
    ├── importazione.py ricezione del file CSV
    └── misc.py        tag automatici e catch-all
tests/                 test della logica (niente Telegram)
```

Il punto da cui partire per modificare il bot è `anagrafe/commands.py`:
aggiungendo una voce a `COMMANDS`, il comando compare da solo in `/help`, nella
pulsantiera `/menu` e — se pubblico — nel menu nativo di Telegram. Resta da
scrivere la sua azione e registrarla nel dizionario `AZIONI` di
`handlers/azioni.py`. Un campo con `opzioni=(...)` diventa una fila di pulsanti
nel wizard; `scelte="..."` le fa invece leggere dal registro da un fornitore in
`handlers/scelte.py`, con `messaggio_vuoto` per il caso in cui non ci sia nulla
da scegliere; `sezione="..."` decide in quale area della pulsantiera compare il
pulsante; un comando con `wizard_diretto=True` entra nel proprio wizard appena
digitato e va negli `entry_points` di `build_menu_handler()`, **non** nel
dizionario `COMANDI`; `attende_allegato=True` lo fa uscire dal wizard per
aspettare un file (e richiede una voce in `IMPORTAZIONI`);
`senza_conferma=True` esegue appena i dati sono raccolti, senza riepilogo.

Un test (`test_nessuna_chiave_orfana_nei_dizionari_dei_comandi`) verifica che
ogni chiave di `COMANDI`, `AZIONI`, `PRECONDIZIONI` e `VERIFICHE_CAMPO` nomini
un comando che esiste davvero: è la rete che rende sicuro rinominare un
comando, perché una chiave rimasta indietro resterebbe altrimenti muta. Altri
due test verificano che ogni scelta a pulsante — fissa o letta dal registro —
superi il validatore del proprio campo: una scelta e il suo validatore non
possono disallinearsi senza che la suite se ne accorga.

### Schema del database

**`cittadini`** — `citizen_id` (PK), `telegram_id` (unico), `username`, `nome`,
`cognome`, `data_acquisizione`.

**`richieste`** — `request_id` (PK), `telegram_id`, `username`, `nome`,
`cognome`, `data_richiesta`, `stato` (`in_attesa` / `accettata` / `rifiutata`),
`admin_id`, `admin_username`, `data_gestione`, `notifiche` (JSON dei messaggi
di notifica inviati agli amministratori, per poterli aggiornare tutti).

**`attivita`** — `attivita_id` (PK), `owner_id` (ID Telegram del proprietario),
`owner_username`, `nome_attivita`, `tipologia`, `descrizione`, `contatto_link`,
`stato` (`ATTIVA` / `CHIUSA` / `RIMOSSA` / `RIFIUTATA`), `chat_id_pubblico` e
`message_id_pubblico` (il post in Gazzetta, per poterlo togliere),
`created_at`, `admin_id`, `admin_username`, `data_moderazione`, `notifiche`.

`owner_id` **non** è dichiarato come foreign key verso `cittadini(telegram_id)`,
e non è una dimenticanza: quella colonna non è la primary key e il suo indice
unico può mancare sui registri che contengono ID Telegram duplicati. Con
`PRAGMA foreign_keys = ON` una foreign key verso una colonna non unica farebbe
fallire ogni inserimento, e senza `ON DELETE` impedirebbe di rimuovere un
cittadino che ha delle attività. Il requisito di cittadinanza è applicato in
`controlli.precondizione_attivita`, come già accade per `richieste`.

Le colonne `admin_id`, `admin_username` e `data_moderazione` registrano *chi ha
chiuso* l'attività: per un ritiro volontario è il proprietario stesso, e lo
`stato` dice in quale veste. L'indice unico su `(owner_id, nome_attivita)` è
**parziale**, limitato alle attività `ATTIVA`: è ciò che permette di correggere
un'attività rimuovendola e reimmettendola con lo stesso nome.

Le tabelle vengono create al primo avvio con `CREATE TABLE IF NOT EXISTS`: un
`registro.db` già esistente acquisisce `attivita` da sé, senza migrazioni.
