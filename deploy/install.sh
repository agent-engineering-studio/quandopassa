#!/usr/bin/env bash
# =====================================================================================
#  QuandoPassa – installazione chiavi in mano su una macchina Linux SENZA Docker
#
#    sudo ./deploy/install.sh                               app e backoffice su http://IP-della-VM (nginx, porta 80)
#    sudo ./deploy/install.sh --dominio bus.comune.it --email it@comune.it    con HTTPS Let's Encrypt
#    sudo ./deploy/install.sh --aiuto                       tutte le opzioni
#
#  Rilanciare lo script (dopo un git pull) aggiorna l'installazione mantenendo configurazione e scelte.
#
#  Cosa fa:
#    - pacchetti di sistema (Debian/Ubuntu con apt, RHEL/Rocky/Alma/Fedora con dnf)
#    - Python >= 3.11 (di sistema, oppure scaricato con uv se la distribuzione è più vecchia)
#    - Node.js 22 temporaneo per costruire l'interfaccia (verificato con SHA-256, poi rimosso)
#    - utente di sistema "quandopassa", codice in /opt/quandopassa, configurazione in /etc/quandopassa
#    - servizi systemd: quandopassa-app, quandopassa-inference, quandopassa-mcp (e -demo), raccolti
#      in quandopassa.target, non-root e con hardening systemd
#    - nginx come reverse proxy con rate limiting e log senza query string (coordinate), HTTPS opzionale
#    - firewall (ufw o firewalld, se attivi) e SELinux (se attivo)
#    - backoffice /admin con Postgres locale e backup giornaliero
#    - opzionale: Ollama con un LLM locale (--llm)
# =====================================================================================
set -Eeuo pipefail
umask 022

# ------------------------------------------------------------------ valori predefiniti
PREFIX=/opt/quandopassa
CONF_DIR=/etc/quandopassa
DATA_DIR=/var/lib/quandopassa
BACKUP_DIR=/var/backups/quandopassa
SERVICE_USER=quandopassa
REPO_URL=https://github.com/agent-engineering-studio/quandopassa.git
REPO_REF=main
NODE_MAJOR=22
OLLAMA_PIN=0.12.11
APP_PORT=8000
DEMO_PORT=8001
INFERENCE_PORT=8080
MCP_PORT=8090

# scelte: lette da install.conf (installazione precedente), poi sovrascritte dalle opzioni
USE_NGINX=si
DOMAIN=
EMAIL=
LLM=no
DEMO=no
ADMIN_NAME="admin"
ADMIN_ALLOW=
UNINSTALL=no
SKIP_PACKAGES=no

LOG_FILE=/var/log/quandopassa-install.log

# ------------------------------------------------------------------ messaggi
if [[ -t 1 ]]; then B=$'\033[1m'; GREEN=$'\033[32m'; YELLOW=$'\033[33m'; RED=$'\033[31m'; N=$'\033[0m'
else B='' GREEN='' YELLOW='' RED='' N=''; fi
step() { printf '\n%s==> %s%s\n' "$B" "$*" "$N"; }
info() { printf '    %s\n' "$*"; }
ok()   { printf '    %s✔%s %s\n' "$GREEN" "$N" "$*"; }
warn() { printf '    %s!%s %s\n' "$YELLOW" "$N" "$*" >&2; }
fail() { printf '\n%sERRORE:%s %s\n' "$RED" "$N" "$*" >&2; exit 1; }
trap 'printf "\n%sInstallazione interrotta%s (riga %s: %s). Dettagli in %s\n" "$RED" "$N" "$LINENO" "$BASH_COMMAND" "$LOG_FILE" >&2' ERR

usage() {
  cat <<EOF
Installazione di QuandoPassa senza Docker (Debian 12+, Ubuntu 22.04+, RHEL/Rocky/Alma 8+, Fedora).

uso: sudo $0 [opzioni]

  --dominio NOME        nome pubblico del servizio (es. bus.comune.example.it): nginx risponde a quel nome
                        e BASE_URL diventa https://NOME (o http:// senza --email)
  --email INDIRIZZO     con --dominio: certificato HTTPS Let's Encrypt con certbot (rinnovo automatico)
  --utente-admin NOME   nome dell'utente del backoffice /admin (predefinito: $ADMIN_NAME)
  --admin-da RETE       apre /admin solo da questa rete, es. 10.0.0.0/8 (ripetibile; predefinito: da ovunque)
  --senza-nginx         niente reverse proxy: l'app ascolta direttamente su 0.0.0.0:$APP_PORT
  --con-nginx           riattiva nginx dopo un'installazione con --senza-nginx
  --llm                 installa Ollama $OLLAMA_PIN con il modello di LLM_MODEL e usa INFERENCE_BACKEND=openai
                        (fare prima la valutazione d'impatto prevista dalle Linee guida AgID)
  --senza-llm           torna al motore a regole offline (Ollama resta installato)
  --demo                anche l'istanza demo con orologio fisso (porta $DEMO_PORT)
  --senza-demo          rimuove l'istanza demo
  --prefisso DIR        cartella di installazione (predefinita $PREFIX)
  --repo URL            repository da clonare se lo script non è lanciato da un clone (predefinito $REPO_URL)
  --ref RAMO|TAG        ramo o tag da clonare (predefinito $REPO_REF)
  --salta-pacchetti     non installa pacchetti di sistema (ambienti senza accesso ai repository)
  --disinstalla         rimuove servizi, codice, utente e sito nginx (configurazione, dati e database restano)
  --aiuto               questo messaggio

Il backoffice /admin è sempre attivo: Postgres locale, dati in $DATA_DIR, backup notturno in $BACKUP_DIR.
Utente e password stanno nella configurazione (ADMIN_USER, ADMIN_PASSWORD): la password si chiede alla prima
installazione (o si genera e si mostra una volta); per cambiarla:  sudo quandopassa password

Rilanciare lo script aggiorna l'installazione: codice, dipendenze e interfaccia vengono ricostruiti,
la configurazione ($CONF_DIR/quandopassa.env), i dati e le scelte fatte con le opzioni restano.
EOF
}

# ------------------------------------------------------------------ opzioni
[[ ${EUID:-$(id -u)} -eq 0 ]] || { usage; fail "va eseguito come root (sudo)."; }

# scelte della volta precedente
# shellcheck disable=SC1091
[[ -f $CONF_DIR/install.conf ]] && . "$CONF_DIR/install.conf"

ADMIN_ALLOW_NEW=
while [[ $# -gt 0 ]]; do
  case $1 in
    --dominio)          DOMAIN=${2:?--dominio richiede un nome}; shift ;;
    --email)            EMAIL=${2:?--email richiede un indirizzo}; shift ;;
    --backoffice)       ;;  # compatibilità: il backoffice è sempre attivo
    --utente-admin)     ADMIN_NAME=${2:?--utente-admin richiede un nome}; shift ;;
    --admin-da)         ADMIN_ALLOW_NEW="$ADMIN_ALLOW_NEW ${2:?--admin-da richiede una rete}"; shift ;;
    --senza-nginx)      USE_NGINX=no ;;
    --con-nginx)        USE_NGINX=si ;;
    --llm)              LLM=si ;;
    --senza-llm)        LLM=no ;;
    --demo)             DEMO=si ;;
    --senza-demo)       DEMO=no ;;
    --prefisso)         PREFIX=${2:?--prefisso richiede una cartella}; shift ;;
    --repo)             REPO_URL=${2:?}; shift ;;
    --ref)              REPO_REF=${2:?}; shift ;;
    --salta-pacchetti)  SKIP_PACKAGES=si ;;
    --disinstalla)      UNINSTALL=si ;;
    -h|--aiuto|--help)  usage; exit 0 ;;
    *) usage; fail "opzione sconosciuta: $1" ;;
  esac
  shift
done
[[ -n $ADMIN_ALLOW_NEW ]] && ADMIN_ALLOW=${ADMIN_ALLOW_NEW# }
[[ -n $EMAIL && -z $DOMAIN ]] && fail "--email serve solo insieme a --dominio."
[[ -n $DOMAIN && $USE_NGINX == no ]] && fail "--dominio richiede nginx (non usare --senza-nginx)."
[[ $DOMAIN =~ ^[A-Za-z0-9.-]*$ ]] || fail "dominio non valido: $DOMAIN"
[[ $ADMIN_NAME =~ ^[A-Za-z0-9._-]{1,50}$ ]] || fail "nome utente del backoffice non valido: $ADMIN_NAME"
for net in $ADMIN_ALLOW; do [[ $net =~ ^[0-9a-fA-F.:/]+$ ]] || fail "rete non valida per --admin-da: $net"; done

VENV=$PREFIX/.venv
TOOLS_DIR=$PREFIX/.strumenti
ENV_FILE=$CONF_DIR/quandopassa.env
NGINX_CONF=/etc/nginx/conf.d/quandopassa.conf
SERVICES=(quandopassa-inference quandopassa-app quandopassa-mcp)

mkdir -p "$(dirname "$LOG_FILE")"
exec > >(tee -a "$LOG_FILE") 2>&1
printf '\n===== %s  %s %s\n' "$(date -Is)" "$0" "$*" >>"$LOG_FILE"

# ------------------------------------------------------------------ sistema
[[ -r /etc/os-release ]] || fail "/etc/os-release mancante: distribuzione non riconosciuta."
# shellcheck disable=SC1091
. /etc/os-release
FAMILY=
case " ${ID:-} ${ID_LIKE:-} " in
  *" debian "*|*" ubuntu "*) FAMILY=debian ;;
  *" rhel "*|*" fedora "*|*" centos "*) FAMILY=rhel ;;
esac
command -v systemctl >/dev/null || fail "serve systemd."
case $(uname -m) in
  x86_64|amd64)  NODE_ARCH=x64;   UV_ARCH=x86_64 ;;
  aarch64|arm64) NODE_ARCH=arm64; UV_ARCH=aarch64 ;;
  *) fail "architettura non supportata: $(uname -m)" ;;
esac

# ================================================================== disinstallazione
if [[ $UNINSTALL == si ]]; then
  step "Disinstallazione di QuandoPassa"
  systemctl disable --now quandopassa.target quandopassa-demo quandopassa-backup.timer "${SERVICES[@]}" 2>/dev/null || true
  rm -f /etc/systemd/system/quandopassa{.target,-app.service,-inference.service,-mcp.service,-demo.service} \
        /etc/systemd/system/quandopassa-backup.{service,timer}
  systemctl daemon-reload
  ok "servizi rimossi"
  if [[ -f $NGINX_CONF ]]; then
    rm -f "$NGINX_CONF"
    systemctl reload nginx 2>/dev/null || true
    ok "sito nginx rimosso (nginx e i certificati restano)"
  fi
  rm -rf "$PREFIX" /usr/local/bin/quandopassa /usr/local/lib/quandopassa
  id "$SERVICE_USER" >/dev/null 2>&1 && userdel "$SERVICE_USER" && ok "utente $SERVICE_USER rimosso"
  rm -f "$CONF_DIR/install.conf"
  ok "codice rimosso da $PREFIX"
  info "Restano: configurazione in $CONF_DIR, dati in $DATA_DIR, backup in $BACKUP_DIR e il database"
  info "Postgres «quandopassa» (per eliminarlo: sudo -u postgres dropdb quandopassa)."
  exit 0
fi

step "QuandoPassa – installazione senza Docker"
info "Sistema: ${PRETTY_NAME:-$ID} ($(uname -m))"
info "Cartella: $PREFIX   configurazione: $CONF_DIR   log: $LOG_FILE"
info "nginx: $USE_NGINX   dominio: ${DOMAIN:-nessuno}   HTTPS: $([[ -n $EMAIL ]] && echo si || echo no)   utente admin: $ADMIN_NAME   LLM: $LLM   demo: $DEMO"

# ------------------------------------------------------------------ pacchetti
install_packages() {
  if [[ $FAMILY == debian ]]; then
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -q
    apt-get install -y -q --no-install-recommends "$@"
  elif [[ $FAMILY == rhel ]]; then
    dnf install -y -q "$@"
  else
    fail "distribuzione non supportata ($ID): installare a mano $* e rilanciare con --salta-pacchetti"
  fi
}

step "Pacchetti di sistema"
if [[ $SKIP_PACKAGES == si ]]; then
  warn "salto l'installazione dei pacchetti (--salta-pacchetti)"
else
  BASE_PACKAGES=(ca-certificates rsync tar gzip git)
  # RHEL 9 ha curl-minimal, in conflitto col pacchetto curl: lo installo solo se manca
  command -v curl >/dev/null || BASE_PACKAGES+=(curl)
  [[ $USE_NGINX == si ]] && BASE_PACKAGES+=(nginx)
  if [[ $FAMILY == debian ]]; then
    install_packages "${BASE_PACKAGES[@]}" python3 python3-venv postgresql
    [[ -n $EMAIL ]] && install_packages certbot python3-certbot-nginx
  else
    install_packages "${BASE_PACKAGES[@]}"
    # Python >= 3.11 dai repository della distribuzione, se c'è
    for v in 3.12 3.11; do
      if dnf list -q "python$v" >/dev/null 2>&1; then install_packages "python$v"; break; fi
    done
    install_packages postgresql-server
    if [[ -n $EMAIL ]]; then
      rpm -q epel-release >/dev/null 2>&1 || install_packages epel-release \
        || warn "EPEL non disponibile: abilitarlo a mano per certbot"
      install_packages certbot python3-certbot-nginx
    fi
  fi
  ok "pacchetti installati"
fi
for c in curl rsync tar sha256sum; do command -v "$c" >/dev/null || fail "comando mancante: $c"; done

# ------------------------------------------------------------------ sorgenti
step "Sorgenti"
SOURCE=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." 2>/dev/null && pwd || true)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
if [[ -z $SOURCE || ! -f $SOURCE/api/quandopassa/main.py ]]; then
  command -v git >/dev/null || fail "serve git per clonare $REPO_URL"
  info "clono $REPO_URL ($REPO_REF)"
  git clone -q --depth 1 --branch "$REPO_REF" "$REPO_URL" "$TMP/src"
  SOURCE=$TMP/src
fi
[[ $SOURCE -ef $PREFIX ]] && fail "lanciare lo script da un clone del repository, non da $PREFIX."
VERSION=$(git -C "$SOURCE" describe --tags --always --dirty 2>/dev/null || echo sconosciuta)
ok "sorgente: $SOURCE (versione $VERSION)"

# ------------------------------------------------------------------ utente e codice
step "Utente di sistema e codice in $PREFIX"
if ! id "$SERVICE_USER" >/dev/null 2>&1; then
  useradd --system --user-group --home-dir "$PREFIX" --no-create-home --shell /usr/sbin/nologin "$SERVICE_USER"
  ok "creato l'utente $SERVICE_USER"
fi
mkdir -p "$PREFIX" "$TOOLS_DIR"
# il codice appartiene a root: il servizio lo legge ma non può modificarlo
rsync -a --delete \
  --exclude .git/ --exclude .github/ --exclude docs/ --exclude site/ --exclude node_modules/ \
  --exclude web/dist/ --exclude .venv/ --exclude .strumenti/ --exclude __pycache__/ --exclude .pytest_cache/ \
  --exclude .env --exclude '*.mp4' --exclude '*.webm' --exclude '*.gif' \
  "$SOURCE"/ "$PREFIX"/
echo "$VERSION" >"$PREFIX/VERSIONE"
chown -R root:root "$PREFIX"
chmod 755 "$PREFIX"
ok "codice copiato"

# ------------------------------------------------------------------ Python
step "Python (>= 3.11)"
python_ok() { "$1" -c 'import sys, venv, ensurepip; sys.exit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1; }
PY=
for c in python3.13 python3.12 python3.11 python3; do
  p=$(command -v "$c" 2>/dev/null) || continue
  if python_ok "$p"; then PY=$p; break; fi
done
if [[ -z $PY ]]; then
  info "nessun Python >= 3.11 di sistema: lo scarico con uv (python-build-standalone)"
  UV_TGZ=uv-$UV_ARCH-unknown-linux-gnu.tar.gz
  curl -fsSL -o "$TMP/$UV_TGZ" "https://github.com/astral-sh/uv/releases/latest/download/$UV_TGZ"
  curl -fsSL -o "$TMP/$UV_TGZ.sha256" "https://github.com/astral-sh/uv/releases/latest/download/$UV_TGZ.sha256"
  (cd "$TMP" && sha256sum -c --quiet "$UV_TGZ.sha256") || fail "checksum di uv non valido"
  tar -xzf "$TMP/$UV_TGZ" -C "$TMP"
  export UV_PYTHON_INSTALL_DIR=$TOOLS_DIR/python
  "$TMP/uv-$UV_ARCH-unknown-linux-gnu/uv" python install --no-bin --quiet 3.12
  PY=$("$TMP/uv-$UV_ARCH-unknown-linux-gnu/uv" python find --managed-python 3.12)
  chmod -R a+rX "$TOOLS_DIR/python"
fi
python_ok "$PY" || fail "Python >= 3.11 con il modulo venv non disponibile (Debian/Ubuntu: apt install python3-venv)"
ok "uso $PY ($("$PY" -V 2>&1))"

# ricrea l'ambiente se manca o se è cambiata la versione di Python
if [[ -x $VENV/bin/python ]] && [[ "$("$VENV/bin/python" -V 2>&1)" != "$("$PY" -V 2>&1)" ]]; then
  rm -rf "$VENV"
fi
[[ -x $VENV/bin/python ]] || "$PY" -m venv "$VENV"
"$VENV/bin/python" -m pip install -q --disable-pip-version-check --upgrade pip
"$VENV/bin/python" -m pip install -q --disable-pip-version-check \
  -r "$PREFIX/api/requirements.txt" -r "$PREFIX/inference/requirements.txt" -r "$PREFIX/mcp_server/requirements.txt"
"$VENV/bin/python" -m compileall -q "$PREFIX/api" "$PREFIX/inference" "$PREFIX/mcp_server" "$PREFIX/deploy" >/dev/null || true
ok "dipendenze Python installate in $VENV"

# ------------------------------------------------------------------ interfaccia web
step "Interfaccia web e backoffice (build con Node.js $NODE_MAJOR)"
node_ok() { command -v node >/dev/null && [[ $(node -p 'process.versions.node.split(".")[0]' 2>/dev/null || echo 0) -ge $NODE_MAJOR ]]; }
NODE_BIN=
if node_ok; then
  NODE_BIN=$(dirname "$(command -v node)")
  info "uso Node.js di sistema $(node -v)"
else
  NODE_BASE=https://nodejs.org/dist/latest-v$NODE_MAJOR.x
  curl -fsSL -o "$TMP/SHASUMS256.txt" "$NODE_BASE/SHASUMS256.txt"
  NODE_TGZ=$(grep -oE "node-v[0-9.]+-linux-$NODE_ARCH\.tar\.gz" "$TMP/SHASUMS256.txt" | head -1)
  [[ -n $NODE_TGZ ]] || fail "Node.js $NODE_MAJOR per linux-$NODE_ARCH non trovato su nodejs.org"
  info "scarico $NODE_TGZ (solo per la build, poi viene rimosso)"
  curl -fsSL -o "$TMP/$NODE_TGZ" "$NODE_BASE/$NODE_TGZ"
  (cd "$TMP" && grep " $NODE_TGZ\$" SHASUMS256.txt | sha256sum -c --quiet -) || fail "checksum di Node.js non valido"
  tar -xzf "$TMP/$NODE_TGZ" -C "$TMP"
  NODE_BIN=$TMP/${NODE_TGZ%.tar.gz}/bin
fi
(
  cd "$PREFIX/web"
  export PATH=$NODE_BIN:$PATH npm_config_update_notifier=false npm_config_fund=false npm_config_audit=false
  npm ci --no-audit --no-fund --loglevel=error
  npm run build --silent
)
rm -rf "$PREFIX/web/node_modules"
[[ -f $PREFIX/web/dist/index.html && -f $PREFIX/web/dist/admin/index.html ]] || fail "build dell'interfaccia non riuscita"
ok "interfaccia e backoffice costruiti in $PREFIX/web/dist"

# ------------------------------------------------------------------ configurazione
step "Configurazione $ENV_FILE"
set_env() {  # set_env KEY VALUE: sostituisce la riga del file .env o la aggiunge
  local key=$1 value=$2 tmp
  tmp=$(mktemp)
  awk -v k="$key" -v v="$value" 'BEGIN{f=0} index($0, k"=")==1 {print k"="v; f=1; next} {print} END{if(!f) print k"="v}' \
    "$ENV_FILE" >"$tmp"
  cat "$tmp" >"$ENV_FILE"; rm -f "$tmp"
}
env_value() { awk -F= -v k="$1" 'index($0, k"=")==1 {sub(/^[^=]*=/, ""); v=$0} END{print v}' "$ENV_FILE"; }
primary_ip() { hostname -I 2>/dev/null | awk '{print $1}' || true; }
random_secret() { "$VENV/bin/python" -c 'import secrets; print(secrets.token_urlsafe(48))'; }

mkdir -p "$CONF_DIR"
NEW_ENV=no
if [[ ! -f $ENV_FILE ]]; then
  NEW_ENV=si
  {
    echo "# QuandoPassa su VM senza Docker. Dopo ogni modifica:  sudo systemctl restart quandopassa.target"
    echo "# (oppure: sudo quandopassa riavvia). I percorsi relativi sono relativi a $PREFIX."
    sed -e '/^#  Dopo ogni modifica:/d' "$PREFIX/.env.example"
  } >"$ENV_FILE"
  # sulla VM Ollama ascolta in locale, non sul nome del container
  set_env LLM_BASE_URL "http://127.0.0.1:11434/v1"
fi
if [[ -n $DOMAIN ]]; then
  set_env BASE_URL "$([[ -n $EMAIL ]] && echo https || echo http)://$DOMAIN"
elif [[ $NEW_ENV == si ]]; then
  IP=$(primary_ip)
  if [[ $USE_NGINX == si ]]; then set_env BASE_URL "http://${IP:-localhost}"; else set_env BASE_URL "http://${IP:-localhost}:$APP_PORT"; fi
fi
if [[ $LLM == si ]]; then set_env INFERENCE_BACKEND openai; else set_env INFERENCE_BACKEND rules; fi
chown root:"$SERVICE_USER" "$ENV_FILE"
chmod 640 "$ENV_FILE"

GTFS_DIR_VALUE=$(env_value GTFS_DIR); GTFS_DIR_VALUE=${GTFS_DIR_VALUE:-data}
[[ $GTFS_DIR_VALUE == /* ]] && GTFS_PATH=$GTFS_DIR_VALUE || GTFS_PATH=$PREFIX/${GTFS_DIR_VALUE#./}
[[ -f $GTFS_PATH/stops.txt ]] || fail "feed GTFS non trovato in $GTFS_PATH (GTFS_DIR in $ENV_FILE)"
[[ $GTFS_PATH == "$PREFIX"/* ]] && [[ $GTFS_DIR_VALUE != data && $GTFS_DIR_VALUE != ./data ]] && \
  warn "il feed in $GTFS_PATH viene sovrascritto a ogni aggiornamento: per un feed proprio usare un percorso assoluto fuori da $PREFIX (es. /srv/quandopassa/gtfs)"
ok "configurazione pronta (BASE_URL=$(env_value BASE_URL), feed $GTFS_PATH)"

# ------------------------------------------------------------------ backoffice: Postgres e credenziali
GENERATED_PASSWORD=
step "Backoffice: database Postgres e accesso"
{
  if [[ $FAMILY == rhel && ! -f /var/lib/pgsql/data/PG_VERSION ]]; then
    postgresql-setup --initdb >/dev/null
  fi
  systemctl enable --now postgresql >/dev/null 2>&1
  for _ in $(seq 30); do runuser -u postgres -- psql -qtAc "SELECT 1" >/dev/null 2>&1 && break; sleep 1; done
  # ruolo con lo stesso nome dell'utente di sistema: accesso dal socket locale, senza password (peer)
  if [[ $(runuser -u postgres -- psql -qtAc "SELECT 1 FROM pg_roles WHERE rolname='$SERVICE_USER'") != 1 ]]; then
    runuser -u postgres -- psql -qc "CREATE ROLE $SERVICE_USER LOGIN" >/dev/null
  fi
  if [[ $(runuser -u postgres -- psql -qtAc "SELECT 1 FROM pg_database WHERE datname='quandopassa'") != 1 ]]; then
    runuser -u postgres -- createdb -O "$SERVICE_USER" quandopassa
  fi
  ok "database «quandopassa» pronto (accesso dal socket locale per l'utente $SERVICE_USER)"

  set_env DATA_DIR "$DATA_DIR"
  set_env DATABASE_URL "postgresql:///quandopassa?host=/var/run/postgresql"
  set_env ADMIN_USER "$ADMIN_NAME"
  current_secret=$(env_value ADMIN_SECRET)
  [[ ${#current_secret} -ge 32 ]] || set_env ADMIN_SECRET "$(random_secret)"
  # password: la chiede (o, senza terminale, la genera) lo stesso script di `make env`
  if [[ -z $(env_value ADMIN_PASSWORD) && -z $(env_value ADMIN_PASSWORD_HASH) ]]; then
    "$VENV/bin/python" "$PREFIX/scripts/backoffice_env.py" "$ENV_FILE" | grep -v "Password del backoffice generata" || true
    [[ -t 0 ]] || GENERATED_PASSWORD=$(env_value ADMIN_PASSWORD)
  fi
  chown root:"$SERVICE_USER" "$ENV_FILE"
  chmod 640 "$ENV_FILE"
  ok "accesso al backoffice per l'utente «$ADMIN_NAME» (password in ADMIN_PASSWORD di $ENV_FILE)"

  # backup giornaliero del database e della cartella dati (ultimi 14)
  mkdir -p /usr/local/lib/quandopassa "$BACKUP_DIR"
  chmod 700 "$BACKUP_DIR"
  cat >/usr/local/lib/quandopassa/backup.sh <<EOF
#!/usr/bin/env bash
# Backup di QuandoPassa (generato da deploy/install.sh): database del backoffice e cartella dati.
set -euo pipefail
day=\$(date +%F)
runuser -u postgres -- pg_dump -Fc quandopassa >"$BACKUP_DIR/quandopassa-\$day.dump"
tar -czf "$BACKUP_DIR/dati-\$day.tar.gz" -C "$(dirname "$DATA_DIR")" "$(basename "$DATA_DIR")"
find "$BACKUP_DIR" -name 'quandopassa-*.dump' -mtime +14 -delete
find "$BACKUP_DIR" -name 'dati-*.tar.gz' -mtime +14 -delete
echo "backup in $BACKUP_DIR (\$day)"
EOF
  chmod 750 /usr/local/lib/quandopassa/backup.sh
  cat >/etc/systemd/system/quandopassa-backup.service <<EOF
[Unit]
Description=QuandoPassa – backup del database e dei dati del backoffice
After=postgresql.service

[Service]
Type=oneshot
ExecStart=/usr/local/lib/quandopassa/backup.sh
EOF
  cat >/etc/systemd/system/quandopassa-backup.timer <<EOF
[Unit]
Description=QuandoPassa – backup giornaliero

[Timer]
OnCalendar=*-*-* 02:30:00
RandomizedDelaySec=30m
Persistent=true

[Install]
WantedBy=timers.target
EOF
  systemctl daemon-reload
  systemctl enable --now quandopassa-backup.timer >/dev/null 2>&1
  ok "backup giornaliero in $BACKUP_DIR (ultimi 14 giorni)"
}

# scelte per i prossimi aggiornamenti
cat >"$CONF_DIR/install.conf" <<EOF
# scelte dell'ultima installazione (lette da deploy/install.sh quando viene rilanciato)
PREFIX=$PREFIX
USE_NGINX=$USE_NGINX
DOMAIN=$DOMAIN
EMAIL=$EMAIL
LLM=$LLM
DEMO=$DEMO
ADMIN_NAME=$ADMIN_NAME
ADMIN_ALLOW="$ADMIN_ALLOW"
EOF

# ------------------------------------------------------------------ Ollama (opzionale)
if [[ $LLM == si ]]; then
  step "LLM locale con Ollama"
  if ! command -v ollama >/dev/null; then
    curl -fsSL -o "$TMP/ollama-install.sh" https://ollama.com/install.sh
    OLLAMA_VERSION=$OLLAMA_PIN sh "$TMP/ollama-install.sh"
  fi
  systemctl enable --now ollama >/dev/null 2>&1 || true
  MODEL=$(env_value LLM_MODEL); MODEL=${MODEL:-qwen2.5:1.5b-instruct}
  for _ in $(seq 30); do curl -fs http://127.0.0.1:11434/api/version >/dev/null && break; sleep 1; done
  info "scarico il modello $MODEL (può richiedere qualche minuto)"
  ollama pull "$MODEL"
  ok "Ollama pronto su 127.0.0.1:11434 con $MODEL"
  warn "INFERENCE_BACKEND=openai: fare la valutazione d'impatto prevista dalle Linee guida AgID prima dell'esercizio"
fi

# ------------------------------------------------------------------ systemd
step "Servizi systemd"
if [[ $USE_NGINX == si ]]; then APP_HOST=127.0.0.1; else APP_HOST=0.0.0.0; fi

hardening() {
  cat <<'EOF'
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true
PrivateDevices=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectKernelLogs=true
ProtectControlGroups=true
ProtectClock=true
ProtectHostname=true
RestrictSUIDSGID=true
RestrictRealtime=true
RestrictNamespaces=true
LockPersonality=true
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX
SystemCallArchitectures=native
CapabilityBoundingSet=
UMask=0077
EOF
}

write_unit() {  # write_unit NAME DESCRIPTION DIR AFTER EXTRA COMMAND
  local name=$1 description=$2 dir=$3 after=$4 extra=$5 command=$6
  cat >"/etc/systemd/system/$name.service" <<EOF
# Generato da deploy/install.sh: le modifiche vengono sovrascritte al prossimo aggiornamento.
# La configurazione è in $ENV_FILE.
[Unit]
Description=$description
After=network-online.target $after
Wants=network-online.target $after
PartOf=quandopassa.target

[Service]
Type=simple
User=$SERVICE_USER
Group=$SERVICE_USER
WorkingDirectory=$PREFIX/$dir
Environment=TZ=Europe/Rome PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
$extra
ExecStart=$VENV/bin/python $PREFIX/deploy/avvia.py $ENV_FILE -- $command
Restart=on-failure
RestartSec=3
TimeoutStopSec=15
$(hardening)

[Install]
WantedBy=quandopassa.target
EOF
}

cat >/etc/systemd/system/quandopassa.target <<EOF
[Unit]
Description=QuandoPassa (app, inferenza, MCP)
Wants=quandopassa-inference.service quandopassa-app.service quandopassa-mcp.service

[Install]
WantedBy=multi-user.target
EOF

write_unit quandopassa-inference "QuandoPassa – server di inferenza (rules/LLM)" inference "" \
  "" \
  "$VENV/bin/uvicorn server:app --host 127.0.0.1 --port $INFERENCE_PORT --no-server-header"

APP_EXTRA="Environment=INFERENCE_URL=http://127.0.0.1:$INFERENCE_PORT WEB_DIST=$PREFIX/web/dist"
# /var/lib/quandopassa scrivibile solo da questo servizio (il resto del sistema resta in sola lettura)
APP_EXTRA+=$'\n'"StateDirectory=$(basename "$DATA_DIR")"$'\n'"StateDirectoryMode=0750"
APP_AFTER="quandopassa-inference.service postgresql.service"
write_unit quandopassa-app "QuandoPassa – app (API, interfaccia e backoffice)" api "$APP_AFTER" "$APP_EXTRA" \
  "$VENV/bin/uvicorn --factory quandopassa.main:create_app --host $APP_HOST --port $APP_PORT --proxy-headers --forwarded-allow-ips 127.0.0.1 --no-server-header"

write_unit quandopassa-mcp "QuandoPassa – server MCP (sola lettura)" mcp_server quandopassa-app.service \
  "Environment=QUANDOPASSA_URL=http://127.0.0.1:$APP_PORT MCP_TRANSPORT=http MCP_HOST=127.0.0.1 MCP_PORT=$MCP_PORT" \
  "$VENV/bin/python server.py"

if [[ $DEMO == si ]]; then
  # la demo non ha backoffice e non scrive nella cartella dati
  write_unit quandopassa-demo "QuandoPassa – istanza demo (orologio fisso)" api quandopassa-inference.service \
    "Environment=INFERENCE_URL=http://127.0.0.1:$INFERENCE_PORT WEB_DIST=$PREFIX/web/dist DEMO_ORA=2026-11-11T09:00:00 DATA_DIR= ADMIN_USER=" \
    "$VENV/bin/uvicorn --factory quandopassa.main:create_app --host $APP_HOST --port $DEMO_PORT --proxy-headers --no-server-header"
  sed -i 's/^Wants=quandopassa-inference.service .*/& quandopassa-demo.service/' /etc/systemd/system/quandopassa.target
else
  systemctl disable --now quandopassa-demo >/dev/null 2>&1 || true
  rm -f /etc/systemd/system/quandopassa-demo.service
fi

systemctl daemon-reload
systemctl enable quandopassa.target "${SERVICES[@]}" >/dev/null 2>&1
[[ $DEMO == si ]] && systemctl enable quandopassa-demo >/dev/null 2>&1
TO_RESTART=("${SERVICES[@]}"); [[ $DEMO == si ]] && TO_RESTART+=(quandopassa-demo)
systemctl restart "${TO_RESTART[@]}"
systemctl start quandopassa.target
ok "servizi abilitati all'avvio e riavviati"

# ------------------------------------------------------------------ comando di servizio
cat >/usr/local/bin/quandopassa <<EOF
#!/usr/bin/env bash
# Comandi rapidi per QuandoPassa installato senza Docker (generato da deploy/install.sh).
set -e
SERVICES="quandopassa-inference quandopassa-app quandopassa-mcp"
if systemctl cat quandopassa-demo >/dev/null 2>&1; then SERVICES="\$SERVICES quandopassa-demo"; fi
case "\${1:-}" in
  stato)    systemctl --no-pager status \$SERVICES ;;
  log)      journalctl -f -n 200 -u "quandopassa-\${2:-app}" ;;
  riavvia)  systemctl restart \$SERVICES && echo "riavviato" ;;
  ferma)    systemctl stop quandopassa.target \$SERVICES ;;
  avvia)    systemctl start quandopassa.target ;;
  config)   \${EDITOR:-vi} $ENV_FILE && systemctl restart \$SERVICES && echo "configurazione applicata" ;;
  password) $VENV/bin/python $PREFIX/scripts/backoffice_env.py $ENV_FILE --password
            chown root:$SERVICE_USER $ENV_FILE && chmod 640 $ENV_FILE
            systemctl restart quandopassa-app && echo "password del backoffice cambiata (ADMIN_PASSWORD in $ENV_FILE)" ;;
  backup)   /usr/local/lib/quandopassa/backup.sh ;;
  salute)   curl -fsS http://127.0.0.1:$APP_PORT/api/v1/health && echo ;;
  versione) cat $PREFIX/VERSIONE ;;
  *) echo "uso: quandopassa stato | log [app|inference|mcp|demo] | riavvia | ferma | avvia | config | password | backup | salute | versione"
     echo "aggiornare: git pull nel clone, poi sudo ./deploy/install.sh" ;;
esac
EOF
chmod 755 /usr/local/bin/quandopassa

# ------------------------------------------------------------------ nginx
if [[ $USE_NGINX == si ]]; then
  step "Reverse proxy nginx"
  if [[ -n $DOMAIN ]]; then
    SERVER_NAMES=$DOMAIN
  else
    # nessun dominio: risponde al nome della macchina e ai suoi indirizzi IPv4
    SERVER_NAMES="localhost $(hostname -f 2>/dev/null || hostname) $(hostname -I 2>/dev/null | tr ' ' '\n' | grep -E '^[0-9.]+$' | tr '\n' ' ' || true)"
  fi
  # IPv6 solo se il kernel lo supporta (altrimenti nginx non parte)
  LISTEN6=''; [[ -f /proc/net/if_inet6 ]] && LISTEN6="listen [::]:80;"
  # /admin e /api/admin solo dalle reti indicate con --admin-da
  ADMIN_ACL=''
  if [[ -n $ADMIN_ALLOW ]]; then
    for net in $ADMIN_ALLOW; do ADMIN_ACL+="    allow $net;"$'\n'; done
    ADMIN_ACL+="    allow 127.0.0.1;"$'\n'"    allow ::1;"$'\n'"    deny all;"
  fi
  PROXY="    proxy_pass http://127.0.0.1:$APP_PORT;
    proxy_set_header Host \$host;
    proxy_set_header X-Forwarded-Proto \$scheme;
    proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;"
  # se certbot ha già configurato HTTPS per questo dominio, non sovrascrivere il suo blocco server
  if [[ -f $NGINX_CONF ]] && grep -q 'managed by Certbot' "$NGINX_CONF" && [[ -n $DOMAIN ]] && grep -q "server_name $DOMAIN;" "$NGINX_CONF"; then
    info "configurazione HTTPS di certbot già presente: la mantengo"
  else
    cat >"$NGINX_CONF" <<EOF
# QuandoPassa – generato da deploy/install.sh
# Log senza query string: le richieste contengono le coordinate delle persone (GDPR art. 5.1.c).
log_format quandopassa '\$remote_addr - [\$time_local] "\$request_method \$uri \$server_protocol" \$status \$body_bytes_sent "\$http_user_agent"';
limit_req_zone \$binary_remote_addr zone=quandopassa_api:10m rate=10r/s;
limit_req_zone \$binary_remote_addr zone=quandopassa_login:1m rate=5r/m;

server {
  listen 80;
  $LISTEN6
  server_name $SERVER_NAMES;

  access_log /var/log/nginx/quandopassa.access.log quandopassa;
  client_max_body_size 64k;
  server_tokens off;

  add_header X-Content-Type-Options nosniff always;
  add_header Referrer-Policy strict-origin-when-cross-origin always;
  add_header Strict-Transport-Security "max-age=31536000" always;

  gzip on;
  gzip_types text/css application/javascript application/json image/svg+xml;

  # backoffice: pochi tentativi di accesso, logo e tracciati fino a 2 MB, reti ammesse
  location = /api/admin/login {
$ADMIN_ACL
    limit_req zone=quandopassa_login burst=5 nodelay;
    limit_req_status 429;
$PROXY
  }

  location /api/admin/ {
$ADMIN_ACL
    client_max_body_size 2m;
$PROXY
    proxy_read_timeout 60s;
  }

  location /admin/ {
$ADMIN_ACL
$PROXY
  }

  location /api/ {
    limit_req zone=quandopassa_api burst=40 nodelay;
    limit_req_status 429;
$PROXY
    proxy_read_timeout 60s;
  }

  location /assets/ {
    proxy_pass http://127.0.0.1:$APP_PORT;
    proxy_set_header Host \$host;
    expires 30d;
    add_header Cache-Control "public, immutable";
    add_header X-Content-Type-Options nosniff always;
  }

  location / {
$PROXY
  }
}
EOF
  fi
  # Debian/Ubuntu: il sito "default" risponderebbe al posto di QuandoPassa
  if [[ -z $DOMAIN && -L /etc/nginx/sites-enabled/default ]]; then
    rm -f /etc/nginx/sites-enabled/default
    info "disattivato il sito nginx predefinito di Debian/Ubuntu"
  fi
  # SELinux (RHEL & co.): nginx deve poter collegarsi all'app su 127.0.0.1
  if command -v getenforce >/dev/null && [[ $(getenforce) == Enforcing ]]; then
    setsebool -P httpd_can_network_connect 1 && info "SELinux: httpd_can_network_connect attivato"
  fi
  nginx -t -q || fail "configurazione nginx non valida ($NGINX_CONF)"
  systemctl enable nginx >/dev/null 2>&1
  systemctl reload nginx 2>/dev/null || systemctl restart nginx
  ok "nginx pubblica l'app sulla porta 80 ($NGINX_CONF)"

  if [[ -n $EMAIL ]]; then
    step "Certificato HTTPS (Let's Encrypt)"
    certbot --nginx -n --agree-tos -m "$EMAIL" -d "$DOMAIN" --redirect --keep-until-expiring \
      || fail "certbot non riuscito: il DNS di $DOMAIN punta a questa macchina e la porta 80 è raggiungibile?"
    ok "HTTPS attivo su https://$DOMAIN (rinnovo automatico con il timer di certbot)"
  fi
else
  if [[ -f $NGINX_CONF ]]; then rm -f "$NGINX_CONF"; systemctl reload nginx 2>/dev/null || true; fi
fi

# ------------------------------------------------------------------ firewall
step "Firewall"
PORTS=()
if [[ $USE_NGINX == si ]]; then PORTS=(80); [[ -n $EMAIL ]] && PORTS+=(443); else PORTS=("$APP_PORT"); fi
[[ $DEMO == si && $USE_NGINX == no ]] && PORTS+=("$DEMO_PORT")
if command -v ufw >/dev/null && ufw status 2>/dev/null | grep -q 'Status: active'; then
  for p in "${PORTS[@]}"; do ufw allow "$p/tcp" >/dev/null; done
  ok "ufw: aperte le porte ${PORTS[*]}"
elif command -v firewall-cmd >/dev/null && firewall-cmd --state >/dev/null 2>&1; then
  for p in "${PORTS[@]}"; do firewall-cmd -q --permanent --add-port="$p/tcp"; done
  firewall-cmd -q --reload
  ok "firewalld: aperte le porte ${PORTS[*]}"
else
  info "nessun firewall attivo rilevato: aprire a mano le porte ${PORTS[*]}/tcp se serve"
fi

# ------------------------------------------------------------------ verifica
step "Verifica"
wait_for() {  # wait_for URL NAME UNIT
  for _ in $(seq 60); do
    if curl -fs -o /dev/null "$1"; then ok "$2 risponde"; return 0; fi
    sleep 1
  done
  journalctl -u "$3" -n 30 --no-pager || true
  fail "$2 non risponde su $1 (log sopra; vedi anche: journalctl -u $3)"
}
wait_for "http://127.0.0.1:$INFERENCE_PORT/health" "server di inferenza" quandopassa-inference
wait_for "http://127.0.0.1:$APP_PORT/api/v1/health" "app" quandopassa-app
wait_for "http://127.0.0.1:$APP_PORT/" "interfaccia web" quandopassa-app
for _ in $(seq 30); do
  code=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$MCP_PORT/mcp" || true)
  [[ $code != 000 ]] && break; sleep 1
done
[[ ${code:-000} != 000 ]] && ok "server MCP risponde" || warn "il server MCP non risponde: journalctl -u quandopassa-mcp"
[[ $DEMO == si ]] && wait_for "http://127.0.0.1:$DEMO_PORT/api/v1/health" "istanza demo" quandopassa-demo
{
  # 401 = backoffice attivo e in attesa di accesso; 404 = non attivo; 503 = database non raggiungibile
  code=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$APP_PORT/api/admin/session" || true)
  [[ $code == 401 ]] && ok "backoffice attivo" || warn "il backoffice non risponde come previsto (HTTP $code): journalctl -u quandopassa-app"
  curl -fs -o /dev/null "http://127.0.0.1:$APP_PORT/admin/" && ok "pagina del backoffice raggiungibile" || true
}
if [[ $USE_NGINX == si ]]; then
  curl -fs -o /dev/null -H "Host: ${DOMAIN:-localhost}" http://127.0.0.1/api/v1/health \
    && ok "nginx inoltra all'app" || warn "nginx non inoltra all'app: controllare $NGINX_CONF"
fi

# ------------------------------------------------------------------ riepilogo
BASE_URL=$(env_value BASE_URL)
step "${GREEN}QuandoPassa è installato${N} (versione $VERSION)"
cat <<EOF

    App                 $BASE_URL
    Documentazione API  $BASE_URL/api/docs
    Backoffice          $BASE_URL/admin/   (utente: $ADMIN_NAME$([[ -n $ADMIN_ALLOW ]] && echo ", solo da $ADMIN_ALLOW"))
    Server MCP          http://127.0.0.1:$MCP_PORT/mcp   (solo dalla VM; da fuori: ssh -L $MCP_PORT:127.0.0.1:$MCP_PORT)
$([[ $DEMO == si ]] && echo "    Istanza demo        http://127.0.0.1:$DEMO_PORT   $([[ $USE_NGINX == si ]] && echo "(da fuori: ssh -L $DEMO_PORT:127.0.0.1:$DEMO_PORT)")")
    Configurazione      $ENV_FILE    →  sudo quandopassa config
    Stato e log         sudo quandopassa stato   |   sudo quandopassa log app
    Backup              ogni notte in $BACKUP_DIR   |   subito: sudo quandopassa backup
    Aggiornare          git pull nel clone, poi  sudo ./deploy/install.sh
    Disinstallare       sudo ./deploy/install.sh --disinstalla

EOF
if [[ -n $GENERATED_PASSWORD ]]; then
  warn "password generata per «$ADMIN_NAME»: $GENERATED_PASSWORD"
  warn "è salvata in ADMIN_PASSWORD di $ENV_FILE; per cambiarla: sudo quandopassa password"
fi
if [[ $NEW_ENV == si ]]; then
  warn "rivedere $ENV_FILE (o le Impostazioni del backoffice): COMUNE_NOME, INFO_BIGLIETTI, LINK_BIGLIETTI, MAPPA_TILES e LUOGHI_GEOCODER per l'esercizio"
fi
if [[ -n $DOMAIN && -z $EMAIL ]]; then
  warn "senza --email il servizio è solo HTTP: per l'esercizio serve HTTPS (rilanciare con --email)"
fi
if [[ -z $EMAIL ]]; then
  warn "il backoffice ha una password: in esercizio pubblicarlo solo in HTTPS (--dominio e --email)"
fi
exit 0
