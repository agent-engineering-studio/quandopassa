import {
  ActionIcon,
  Alert,
  Badge,
  Box,
  Button,
  Chip,
  Divider,
  Drawer,
  Group,
  Loader,
  Paper,
  Popover,
  ScrollArea,
  Select,
  Stack,
  Tabs,
  Text,
  TextInput,
  Title,
  Tooltip,
} from "@mantine/core";
import { useMediaQuery } from "@mantine/hooks";
import { notifications } from "@mantine/notifications";
import {
  IconBus,
  IconClock,
  IconCurrentLocation,
  IconInfoCircle,
  IconMapPin,
  IconMessageChatbot,
  IconStar,
  IconX,
} from "@tabler/icons-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Fermata, FermataVicina, Info, LineaDettaglio, OrarioGiorno, Partenza } from "./api";
import { api, hhmm } from "./api";
import Assistente from "./components/Assistente";
import Mappa from "./components/Mappa";
import Partenze from "./components/Partenze";
import Recensioni from "./components/Recensioni";
import { hhmmDaSecondi, secondiDelGiorno, veicoliAl } from "./motore";
import { daLocale, giornoLocale, isoLocale, oraLocale, useOrologio } from "./orologio";

type Pannello = "vicino" | "fermata" | "assistente" | "servizio";
interface Posizione {
  lat: number;
  lon: number;
  accuratezza: number;
}

export default function App() {
  const mobile = useMediaQuery("(max-width: 48em)");
  const { adesso, simulato, simula } = useOrologio(1000);
  const oggi = giornoLocale(adesso);

  const [info, setInfo] = useState<Info | null>(null);
  const [errore, setErrore] = useState<string | null>(null);
  const [fermate, setFermate] = useState<Fermata[]>([]);
  const [linee, setLinee] = useState<LineaDettaglio[]>([]);
  const [orario, setOrario] = useState<OrarioGiorno | null>(null);
  const [lineeVisibili, setLineeVisibili] = useState<string[]>([]);
  const [pannello, setPannello] = useState<Pannello>("vicino");
  const [aperto, setAperto] = useState(true);
  const [selezionata, setSelezionata] = useState<string | null>(null);
  const [partenze, setPartenze] = useState<Partenza[]>([]);
  const [posizione, setPosizione] = useState<Posizione | null>(null);
  const [vicine, setVicine] = useState<FermataVicina[] | null>(null);
  const [cercoPosizione, setCercoPosizione] = useState(false);
  const [centraSu, setCentraSu] = useState<[number, number] | null>(null);
  const [corsaEvidenziata, setCorsaEvidenziata] = useState<string | null>(null);
  const [valutazione, setValutazione] = useState("generale");
  const watchId = useRef<number | null>(null);
  const ultimaPosVicine = useRef<string>("");

  // ------------------------------------------------------------ dati statici
  const caricaFermate = useCallback(() => api.fermate().then(setFermate), []);
  useEffect(() => {
    Promise.all([api.info(), api.fermate(), api.linee()])
      .then(([i, f, l]) => {
        setInfo(i);
        setFermate(f);
        setLinee(l);
        setLineeVisibili(l.map((x) => x.id));
      })
      .catch((e) => setErrore((e as Error).message));
  }, []);

  // orario del giorno (cambia a mezzanotte o con la simulazione)
  useEffect(() => {
    let valido = true; // ignora risposte arrivate dopo un cambio di giorno (sincronizzazione orologio, simulazione)
    api
      .orario(oggi)
      .then((o) => valido && setOrario(o))
      .catch(() => valido && setOrario(null));
    return () => {
      valido = false;
    };
  }, [oggi]);

  const oraApi = simulato ? isoLocale(adesso).slice(0, 16) : undefined;
  const veicoli = useMemo(() => (orario ? veicoliAl(orario, secondiDelGiorno(adesso, orario)) : []), [orario, adesso]);

  // ------------------------------------------------------------ fermata selezionata
  const minutoCorrente = isoLocale(adesso).slice(0, 16);
  useEffect(() => {
    if (!selezionata) return;
    api.partenze(selezionata, minutoCorrente).then(setPartenze).catch(() => setPartenze([]));
  }, [selezionata, minutoCorrente]);

  const apriFermata = useCallback(
    (id: string) => {
      setSelezionata(id);
      setPannello("fermata");
      setAperto(true);
      const f = fermate.find((x) => x.id === id);
      if (f) setCentraSu([f.lat, f.lon]);
    },
    [fermate],
  );

  // ------------------------------------------------------------ geolocalizzazione
  const localizza = () => {
    if (!("geolocation" in navigator)) {
      notifications.show({ color: "red", message: "Il browser non supporta la geolocalizzazione." });
      return;
    }
    setCercoPosizione(true);
    if (watchId.current !== null) navigator.geolocation.clearWatch(watchId.current);
    watchId.current = navigator.geolocation.watchPosition(
      (p) => {
        const nuova = { lat: p.coords.latitude, lon: p.coords.longitude, accuratezza: p.coords.accuracy };
        setPosizione((prima) => {
          if (!prima) setCentraSu([nuova.lat, nuova.lon]);
          return nuova;
        });
        setCercoPosizione(false);
        setPannello((x) => (x === "fermata" ? x : "vicino"));
      },
      (e) => {
        setCercoPosizione(false);
        notifications.show({
          color: "red",
          title: "Posizione non disponibile",
          message: e.code === 1 ? "Permesso negato: abilitalo nelle impostazioni del browser." : e.message,
        });
      },
      { enableHighAccuracy: true, maximumAge: 10000, timeout: 20000 },
    );
  };
  useEffect(() => () => {
    if (watchId.current !== null) navigator.geolocation.clearWatch(watchId.current);
  }, []);

  // fermate vicine: aggiornate quando ci si sposta di ~25 m o cambia il minuto
  useEffect(() => {
    if (!posizione) return;
    const chiave = `${posizione.lat.toFixed(4)},${posizione.lon.toFixed(4)},${minutoCorrente}`;
    if (chiave === ultimaPosVicine.current) return;
    ultimaPosVicine.current = chiave;
    api.vicine(posizione.lat, posizione.lon, minutoCorrente).then(setVicine).catch(() => setVicine(null));
  }, [posizione, minutoCorrente]);

  const fermataSel = fermate.find((f) => f.id === selezionata) ?? null;
  const vicinaSel = vicine?.find((v) => v.id === selezionata);

  // ------------------------------------------------------------ render
  if (errore)
    return (
      <Alert color="red" m="md" title="Servizio non raggiungibile">
        {errore}
      </Alert>
    );
  if (!info)
    return (
      <Group justify="center" h="100vh">
        <Loader />
      </Group>
    );

  const nessunBus = veicoli.length === 0;
  const prossimaCorsa = orario?.corse
    .map((c) => c.partenze[0])
    .filter((s) => s > secondiDelGiorno(adesso, orario))
    .sort((a, b) => a - b)[0];

  const contenutoPannello = (
    <Tabs value={pannello} onChange={(v) => setPannello((v as Pannello) ?? "vicino")} keepMounted={false}>
      <Tabs.List grow>
        <Tabs.Tab value="vicino" leftSection={<IconCurrentLocation size={14} />}>
          Vicino
        </Tabs.Tab>
        <Tabs.Tab value="fermata" leftSection={<IconMapPin size={14} />} disabled={!selezionata}>
          Fermata
        </Tabs.Tab>
        {info.assistente && (
          <Tabs.Tab value="assistente" leftSection={<IconMessageChatbot size={14} />}>
            Chiedi
          </Tabs.Tab>
        )}
        <Tabs.Tab value="servizio" leftSection={<IconStar size={14} />}>
          Servizio
        </Tabs.Tab>
      </Tabs.List>

      <Tabs.Panel value="vicino" pt="sm">
        {!posizione ? (
          <Stack gap="sm">
            <Text size="sm">
              Attiva la posizione: troviamo la fermata più vicina e ti diciamo se fai in tempo a prendere il prossimo
              bus, confrontando l'ora attuale con l'orario ufficiale.
            </Text>
            <Button leftSection={<IconCurrentLocation size={16} />} onClick={localizza} loading={cercoPosizione}>
              Usa la mia posizione
            </Button>
            <Text size="xs" c="dimmed">
              La posizione resta sul tuo dispositivo e serve solo a questo calcolo.
            </Text>
          </Stack>
        ) : !vicine ? (
          <Loader size="sm" />
        ) : (
          <Stack gap="md">
            {vicine.map((v, i) => (
              <Paper key={v.id} withBorder p="sm" radius="md" className="card-fermata" onClick={() => apriFermata(v.id)}>
                <Group justify="space-between" wrap="nowrap" mb={6}>
                  <div>
                    <Text size="xs" c="dimmed">
                      {i === 0 ? "Fermata più vicina" : "Alternativa"}
                    </Text>
                    <Text fw={600}>{v.nome}</Text>
                  </div>
                  <Stack gap={0} align="flex-end">
                    <Text size="sm" fw={600}>
                      {v.distanza_m < 1000 ? `${v.distanza_m} m` : `${(v.distanza_m / 1000).toFixed(1)} km`}
                    </Text>
                    <Text size="xs" c="dimmed">
                      {v.a_piedi_min} min a piedi
                    </Text>
                  </Stack>
                </Group>
                <Partenze partenze={v.partenze} oggi={oggi} aPiediMin={v.a_piedi_min} onCorsa={setCorsaEvidenziata} />
              </Paper>
            ))}
          </Stack>
        )}
      </Tabs.Panel>

      <Tabs.Panel value="fermata" pt="sm">
        {fermataSel && (
          <Stack gap="sm">
            <Group justify="space-between" wrap="nowrap" align="flex-start">
              <div>
                <Group gap={6}>
                  {(fermataSel.linee ?? []).map((l) => {
                    const linea = linee.find((x) => x.id === l);
                    return (
                      <Badge key={l} color={linea?.colore} radius="sm">
                        {l}
                      </Badge>
                    );
                  })}
                  <Text size="xs" c="dimmed">
                    Area n. {fermataSel.codice}
                  </Text>
                </Group>
                <Title order={4} mt={4}>
                  {fermataSel.nome}
                </Title>
                <Text size="xs" c="dimmed">
                  {fermataSel.descrizione}
                </Text>
              </div>
            </Group>
            {fermataSel.provvisoria && (
              <Alert variant="light" color="yellow" p="xs" icon={<IconInfoCircle size={16} />}>
                Posizione sulla mappa provvisoria, in attesa di geocoding o sopralluogo.
              </Alert>
            )}
            {vicinaSel && (
              <Text size="sm">
                Sei a <b>{vicinaSel.distanza_m} m</b>, circa <b>{vicinaSel.a_piedi_min} min</b> a piedi.
              </Text>
            )}
            <Title order={5}>Prossimi passaggi</Title>
            <Partenze partenze={partenze} oggi={oggi} aPiediMin={vicinaSel?.a_piedi_min} onCorsa={setCorsaEvidenziata} />
            <Divider />
            <Recensioni
              tipo="fermata"
              id={fermataSel.id}
              etichette={info.etichette.fermata}
              titolo="Recensioni della fermata"
              onCambio={caricaFermate}
            />
          </Stack>
        )}
      </Tabs.Panel>

      {info.assistente && (
        <Tabs.Panel value="assistente" pt="sm">
          <Assistente esempi={info.esempi_assistente} posizione={posizione} ora={oraApi} onFermata={(id) => setSelezionata(id)} />
        </Tabs.Panel>
      )}

      <Tabs.Panel value="servizio" pt="sm">
        <Stack gap="md">
          <Paper withBorder p="sm" radius="md">
            <Text fw={600}>{info.agenzia}</Text>
            <Text size="sm" c="dimmed">
              Tel. {info.telefono} · orario {info.versione_feed}
            </Text>
          </Paper>
          <Select
            label="Valuta"
            data={[
              { value: "generale", label: "Il servizio in generale" },
              ...linee.map((l) => ({ value: `linea:${l.id}`, label: `${l.nome_esteso}` })),
            ]}
            onChange={(v) => setValutazione(v ?? "generale")}
            value={valutazione}
            allowDeselect={false}
          />
          {valutazione === "generale" ? (
            <Recensioni tipo="servizio" id="generale" etichette={info.etichette.servizio} titolo="Recensioni del servizio" />
          ) : (
            <Recensioni
              tipo="linea"
              id={valutazione.split(":")[1]}
              etichette={info.etichette.linea}
              titolo={`Recensioni · ${linee.find((l) => l.id === valutazione.split(":")[1])?.nome_esteso}`}
            />
          )}
        </Stack>
      </Tabs.Panel>
    </Tabs>
  );

  return (
    <Box className="app">
      <Mappa
        info={info}
        linee={linee}
        fermate={fermate}
        veicoli={veicoli}
        lineeVisibili={lineeVisibili}
        posizione={posizione}
        selezionata={selezionata}
        corsaEvidenziata={corsaEvidenziata}
        onFermata={apriFermata}
        centraSu={centraSu}
      />

      {/* intestazione */}
      <Paper className="testata" shadow="md" radius="lg" p="xs">
        <Group justify="space-between" wrap="nowrap" gap="xs">
          <Group gap={8} wrap="nowrap">
            <IconBus size={24} color="var(--mantine-color-blue-6)" />
            <div>
              <Text fw={700} lh={1.1} size="sm">
                QuandoPassa <Text span size="xs" c="dimmed" fw={500} className="solo-desktop">· {info.servizio}</Text>
              </Text>
              <Text size="xs" c="dimmed" lh={1.1}>
                {veicoli.length} bus in servizio · stima da orario
              </Text>
            </div>
          </Group>
          <Group gap={6} wrap="nowrap">
            <Orologio adesso={adesso} simulato={simulato} simula={simula} />
          </Group>
        </Group>
        <Group gap={6} mt={6} wrap="nowrap">
          <Chip.Group multiple value={lineeVisibili} onChange={setLineeVisibili}>
            <Group gap={6} wrap="nowrap">
              {linee.map((l) => (
                <Chip key={l.id} value={l.id} size="xs" color={l.colore} variant="filled">
                  {l.nome_esteso}
                </Chip>
              ))}
            </Group>
          </Chip.Group>
          <CercaFermata fermate={fermate} onScelta={apriFermata} />
        </Group>
      </Paper>

      {nessunBus && (
        <Paper className="avviso-servizio" shadow="sm" radius="md" p="xs">
          <Group gap="xs" wrap="nowrap">
            <IconClock size={16} />
            <Text size="xs" style={{ flex: 1 }}>
              Nessun bus in servizio ora.
              {prossimaCorsa !== undefined
                ? ` Prima corsa alle ${hhmmDaSecondi(prossimaCorsa)}.`
                : info.prossima_corsa
                  ? ` Prossima: ${info.prossima_corsa.partenza.slice(0, 10) === oggi ? "" : "il " + info.prossima_corsa.partenza.slice(8, 10) + "/" + info.prossima_corsa.partenza.slice(5, 7) + " "}alle ${hhmm(info.prossima_corsa.partenza)}.`
                  : ""}
            </Text>
            <Button
              size="compact-xs"
              variant="light"
              onClick={() => {
                const giorno = info.prossima_corsa?.partenza.slice(0, 10) ?? oggi;
                const ora = prossimaCorsa !== undefined ? hhmmDaSecondi(prossimaCorsa + 600) : "09:00";
                simula(daLocale(`${prossimaCorsa !== undefined ? oggi : giorno}T${ora}`));
              }}
            >
              Simula
            </Button>
          </Group>
        </Paper>
      )}

      {/* pulsanti mappa */}
      <Stack className="pulsanti-mappa" gap={8}>
        <Tooltip label="La mia posizione" position="left">
          <ActionIcon size="xl" radius="xl" variant="white" style={{ boxShadow: "var(--mantine-shadow-md)" }} onClick={localizza} loading={cercoPosizione} aria-label="La mia posizione">
            <IconCurrentLocation size={22} color={posizione ? "var(--mantine-color-blue-6)" : undefined} />
          </ActionIcon>
        </Tooltip>
        {mobile && !aperto && (
          <ActionIcon size="xl" radius="xl" onClick={() => setAperto(true)} aria-label="Apri pannello">
            <IconMessageChatbot size={22} />
          </ActionIcon>
        )}
      </Stack>

      {mobile ? (
        <Drawer
          opened={aperto}
          onClose={() => setAperto(false)}
          position="bottom"
          size="62%"
          withOverlay={false}
          lockScroll={false}
          trapFocus={false}
          radius="lg"
          title={<Text fw={600} size="sm">{titoloPannello(pannello)}</Text>}
        >
          {contenutoPannello}
        </Drawer>
      ) : (
        <Paper className="pannello" shadow="lg" radius="lg" p="sm">
          <ScrollArea h="100%" type="auto" offsetScrollbars>
            {contenutoPannello}
            <Stack gap={4} mt="md">
              {info.avvisi.map((a) => (
                <Text key={a} size="10px" c="dimmed">
                  ⓘ {a}
                </Text>
              ))}
            </Stack>
          </ScrollArea>
        </Paper>
      )}
    </Box>
  );
}

function titoloPannello(p: Pannello) {
  return { vicino: "Vicino a te", fermata: "Fermata", assistente: "Assistente", servizio: "Servizio" }[p];
}

function Orologio({ adesso, simulato, simula }: { adesso: Date; simulato: boolean; simula: (d: Date | null) => void }) {
  const [valore, setValore] = useState("");
  return (
    <Popover position="bottom-end" withArrow shadow="md">
      <Popover.Target>
        <Badge
          size="lg"
          variant={simulato ? "filled" : "light"}
          color={simulato ? "orange" : "blue"}
          leftSection={<IconClock size={14} />}
          style={{ cursor: "pointer", flexShrink: 0, overflow: "visible" }}
          miw={simulato ? 96 : 76}
        >
          {oraLocale(adesso)}
          {simulato ? " sim." : ""}
        </Badge>
      </Popover.Target>
      <Popover.Dropdown>
        <Stack gap="xs" w={220}>
          <Text size="xs">
            Le posizioni dei bus sono calcolate dall'orario. Puoi simulare un altro momento per vedere il servizio.
          </Text>
          <TextInput
            type="datetime-local"
            size="xs"
            value={valore || isoLocale(adesso).slice(0, 16)}
            onChange={(e) => setValore(e.currentTarget.value)}
          />
          <Group gap="xs" grow>
            <Button size="xs" onClick={() => valore && simula(daLocale(valore))}>
              Simula
            </Button>
            <Button size="xs" variant="light" leftSection={<IconX size={12} />} onClick={() => simula(null)} disabled={!simulato}>
              Ora reale
            </Button>
          </Group>
        </Stack>
      </Popover.Dropdown>
    </Popover>
  );
}

function CercaFermata({ fermate, onScelta }: { fermate: Fermata[]; onScelta: (id: string) => void }) {
  return (
    <Select
      size="xs"
      placeholder="Cerca fermata"
      searchable
      clearable
      leftSection={<IconMapPin size={14} />}
      data={fermate.map((f) => ({ value: f.id, label: `${f.codice} · ${f.nome}` }))}
      onChange={(v) => v && onScelta(v)}
      value={null}
      style={{ flex: 1, minWidth: 140 }}
      nothingFoundMessage="Nessuna fermata"
      comboboxProps={{ withinPortal: true }}
    />
  );
}
