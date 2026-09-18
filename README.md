# Bot Anagrafe

Bot Telegram per la gestione del registro cittadini di una simulazione politica.

Tiene l'elenco dei cittadini in un database SQLite, gestisce le richieste di
cittadinanza con approvazione da parte degli amministratori, e registra ogni
modifica su un canale Telegram di log.

---

## Funzionalità

- **Registro dei cittadini** consultabile da chiunque (`/elenco`, `/cerca`) ed
  esportabile in Markdown (`/esporta`).
- **Richieste di cittadinanza** (`/richiedi`): ogni amministratore riceve una
  notifica in privato con i pulsanti *Accetta* / *Rifiuta*. Quando uno decide,
  la notifica si aggiorna per tutti gli altri e il richiedente viene avvisato.
- **Gestione del registro** riservata agli amministratori: inserimento singolo
  (`/inserisci`), rimozione (`/rimuovi`) e **import di massa da CSV**
  (`/importa`).
- **Tre livelli di autorizzazione**: pubblico, amministratore, root.
- **Pulsantiera guidata** (`/menu`): esegue tutti i comandi senza doverne
  ricordare la sintassi, chiedendo i dati un campo alla volta.
- **Aiuto dinamico** (`/help`): mostra solo i comandi che chi lo invoca può
  davvero usare.
- **Username sempre aggiornati**: a ogni interazione con il bot (in privato,
  in un gruppo o premendo un pulsante) il `@username` di un cittadino viene
  aggiornato nel registro. Un tag appartiene a un solo utente alla volta: se lo
  prende qualcun altro, viene tolto al cittadino che lo aveva prima.
- **Il tag al posto dell'ID**: `/rimuovi`, `/aggiungi_admin` e `/rimuovi_admin`
  accettano anche `@username` (di un cittadino) oltre all'ID.
- **Ricerca per parole**: `/cerca Mario Rossi` (in qualunque ordine, ignorando
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
| `/elenco` | Elenco completo dei cittadini (nome, cognome, username). |
| `/esporta` | Invia il registro come file Markdown. |
| `/cerca <testo>` | Cerca per nome e/o cognome (in qualunque ordine), `@username`, `#ID` o ID Telegram. Senza risultati esatti propone i nomi più simili. |
| `/richiedi <nome>, <cognome>` | Invia una richiesta di cittadinanza. |

### Amministratori

| Comando | Cosa fa |
|---|---|
| `/inserisci <ID_telegram>, <username>, <nome>, <cognome>` | Inserisce un cittadino. Lo username può essere lasciato vuoto. |
| `/rimuovi <ID_cittadino \| @username>` | Rimuove il cittadino con quell'ID (il numero dopo `#`) o con quel tag. |
| `/importa` | Importa più cittadini da un file CSV (vedi sotto). |

### Root

| Comando | Cosa fa |
|---|---|
| `/aggiungi_admin <ID_telegram \| @username>` | Promuove un utente ad amministratore (il tag deve essere di un cittadino). |
| `/rimuovi_admin <ID_telegram \| @username>` | Revoca i privilegi di amministratore. |
| `/elenco_admin` | Mostra gli amministratori configurati. |

---

## La pulsantiera `/menu`

`/menu` mostra un pulsante per ogni comando che il tuo ruolo consente.

- I comandi senza parametri (`/elenco`, `/esporta`, `/elenco_admin`) partono
  subito.
- Gli altri aprono un **wizard**: il bot chiede un valore alla volta
  («Qual è il nome?», «Qual è il cognome?»), valida ogni risposta e chiude con
  un riepilogo da confermare. I campi facoltativi hanno un pulsante *Salta*.
- *Annulla* interrompe in qualsiasi momento; il comando `/annulla` fa lo stesso.
- Dopo 5 minuti di inattività il wizard scade da solo.

I permessi vengono ricontrollati al momento del click, non solo quando la
pulsantiera è stata disegnata.

---

## Import da CSV

Invia il file `.csv` al bot **allegandolo in chat con didascalia `/importa`**
(oppure premi *Importa CSV* nel menu e poi manda il file).

Colonne attese:

```csv
Telegram ID,Username,Nome,Cognome
123456789,@mariorossi,Mario,Rossi
987654321,,Anna,Verdi
```

Il parser è volutamente tollerante:

- riconosce l'intestazione anche con nomi equivalenti (`telegram_id`, `id`,
  `first name`, `utente`…) e in qualsiasi ordine di colonne;
- se non trova un'intestazione, legge le colonne nell'ordine
  `Telegram ID, Username, Nome, Cognome`;
- accetta `,` `;` o tabulazione come separatore, e file UTF-8 (anche con BOM)
  o Windows-1252;
- ignora le righe completamente vuote, comprese quelle tipo `,,,` che i fogli
  di calcolo mettono spesso in cima al file.

Al termine ricevi un resoconto con quanti cittadini sono stati **inseriti**,
quanti **saltati** perché già presenti, e l'elenco delle **righe non valide**
con il numero di riga e il motivo. I cittadini già registrati non vengono mai
duplicati, quindi rilanciare lo stesso import è innocuo.

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

## Log su canale

Se imposti `LOG_CHANNEL_ID`, il bot scrive sul canale un messaggio per ogni:

- nuova richiesta di cittadinanza, e ogni accettazione / rifiuto / annullamento;
- inserimento o rimozione di un cittadino;
- import CSV andato a buon fine;
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
2. **Per scrivere sul canale di log, il bot deve esserne amministratore.**
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
├── csv_import.py      parsing e import dei file CSV
├── logbook.py         log sul canale Telegram
└── handlers/
    ├── azioni.py      le azioni, condivise fra comandi e pulsantiera
    ├── controlli.py   quali controlli girano a ogni passo del wizard
    ├── comandi.py     i comandi testuali
    ├── menu.py        la pulsantiera e il wizard
    ├── richieste.py   accettazione e rifiuto delle richieste
    ├── importazione.py ricezione del file CSV
    └── misc.py        tag automatici e catch-all
tests/                 test della logica (niente Telegram)
```

Il punto da cui partire per modificare il bot è `anagrafe/commands.py`:
aggiungendo una voce a `COMMANDS`, il comando compare da solo in `/help`, nella
pulsantiera `/menu` e — se pubblico — nel menu nativo di Telegram. Resta da
scrivere la sua azione in `handlers/azioni.py` e registrarla in `AZIONI`.

### Schema del database

**`cittadini`** — `citizen_id` (PK), `telegram_id` (unico), `username`, `nome`,
`cognome`, `data_acquisizione`.

**`richieste`** — `request_id` (PK), `telegram_id`, `username`, `nome`,
`cognome`, `data_richiesta`, `stato` (`in_attesa` / `accettata` / `rifiutata`),
`admin_id`, `admin_username`, `data_gestione`, `notifiche` (JSON dei messaggi
di notifica inviati agli amministratori, per poterli aggiornare tutti).
