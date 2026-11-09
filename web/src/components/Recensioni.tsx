import {
  Alert,
  Badge,
  Button,
  Chip,
  Group,
  Loader,
  Paper,
  Progress,
  Rating,
  Stack,
  Text,
  TextInput,
  Textarea,
  Title,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { IconSparkles, IconStarFilled } from "@tabler/icons-react";
import { useCallback, useEffect, useState } from "react";
import type { Recensione, RiepilogoConSintesi, TipoRecensione } from "../api";
import { api } from "../api";

interface Props {
  tipo: TipoRecensione;
  id: string;
  etichette: string[];
  titolo?: string;
  onCambio?: () => void;
}

const data = (iso: string) =>
  new Date(iso).toLocaleDateString("it-IT", { day: "numeric", month: "short", year: "numeric" });

export default function Recensioni({ tipo, id, etichette, titolo, onCambio }: Props) {
  const [riepilogo, setRiepilogo] = useState<RiepilogoConSintesi | null>(null);
  const [elenco, setElenco] = useState<Recensione[]>([]);
  const [caricamento, setCaricamento] = useState(true);
  const [scrivi, setScrivi] = useState(false);
  const [voto, setVoto] = useState(0);
  const [tag, setTag] = useState<string[]>([]);
  const [testo, setTesto] = useState("");
  const [autore, setAutore] = useState("");
  const [invio, setInvio] = useState(false);

  const carica = useCallback(async () => {
    setCaricamento(true);
    try {
      const [r, l] = await Promise.all([api.riepilogo(tipo, id), api.recensioni(tipo, id)]);
      setRiepilogo(r);
      setElenco(l.recensioni);
    } finally {
      setCaricamento(false);
    }
  }, [tipo, id]);

  useEffect(() => {
    carica();
    setScrivi(false);
  }, [carica]);

  const invia = async () => {
    setInvio(true);
    try {
      await api.recensisci({ tipo, id, voto, testo, tag, autore });
      notifications.show({ color: "teal", title: "Grazie!", message: "La tua recensione è pubblicata." });
      setScrivi(false);
      setVoto(0);
      setTag([]);
      setTesto("");
      await carica();
      onCambio?.();
    } catch (e) {
      notifications.show({ color: "red", title: "Recensione non inviata", message: (e as Error).message });
    } finally {
      setInvio(false);
    }
  };

  if (caricamento && !riepilogo) return <Loader size="sm" />;
  const n = riepilogo?.conteggio ?? 0;

  return (
    <Stack gap="sm">
      <Group justify="space-between" align="center">
        <Title order={5}>{titolo ?? "Recensioni"}</Title>
        {!scrivi && (
          <Button size="xs" variant="light" onClick={() => setScrivi(true)}>
            Scrivi una recensione
          </Button>
        )}
      </Group>

      {n > 0 && riepilogo && (
        <Group align="flex-start" gap="lg" wrap="nowrap">
          <Stack gap={0} align="center" miw={70}>
            <Text fz={36} fw={700} lh={1}>
              {riepilogo.media?.toFixed(1).replace(".", ",")}
            </Text>
            <Rating value={riepilogo.media ?? 0} fractions={2} readOnly size="xs" />
            <Text size="xs" c="dimmed">
              {n} {n === 1 ? "recensione" : "recensioni"}
            </Text>
          </Stack>
          <Stack gap={2} style={{ flex: 1 }}>
            {[5, 4, 3, 2, 1].map((s) => (
              <Group key={s} gap={6} wrap="nowrap">
                <Text size="xs" w={8}>
                  {s}
                </Text>
                <Progress value={(100 * (riepilogo.distribuzione[String(s)] ?? 0)) / n} color="yellow" size="sm" style={{ flex: 1 }} />
              </Group>
            ))}
          </Stack>
        </Group>
      )}

      {riepilogo && riepilogo.tag.length > 0 && (
        <Group gap={6}>
          {riepilogo.tag.map((t) => (
            <Badge key={t.tag} variant="outline" color="gray" radius="sm" tt="none">
              {t.tag} · {t.conteggio}
            </Badge>
          ))}
        </Group>
      )}

      {riepilogo?.sintesi && (
        <Paper withBorder p="xs" radius="md" bg="var(--mantine-color-blue-light)">
          <Group gap={6} mb={4}>
            <IconSparkles size={14} />
            <Text size="xs" fw={600}>
              {riepilogo.sintesi.generato_da_ia ? "Sintesi generata dall'IA" : "Sintesi automatica"}
            </Text>
          </Group>
          <Text size="sm">{riepilogo.sintesi.sintesi}</Text>
        </Paper>
      )}

      {scrivi && (
        <Paper withBorder p="sm" radius="md">
          <Stack gap="xs">
            <Group gap="xs">
              <Text size="sm" fw={500}>
                Il tuo voto
              </Text>
              <Rating value={voto} onChange={setVoto} size="lg" />
            </Group>
            <Chip.Group multiple value={tag} onChange={setTag}>
              <Group gap={6}>
                {etichette.map((e) => (
                  <Chip key={e} value={e} size="xs" variant="outline">
                    {e}
                  </Chip>
                ))}
              </Group>
            </Chip.Group>
            <Textarea
              placeholder="Racconta la tua esperienza (facoltativo)"
              autosize
              minRows={2}
              maxLength={1000}
              value={testo}
              onChange={(e) => setTesto(e.currentTarget.value)}
            />
            <TextInput
              placeholder="Nome da mostrare (facoltativo)"
              maxLength={40}
              value={autore}
              onChange={(e) => setAutore(e.currentTarget.value)}
            />
            <Text size="xs" c="dimmed">
              Pubblica e anonima: non scrivere dati personali (email e telefoni vengono rimossi).
            </Text>
            <Group justify="flex-end" gap="xs">
              <Button variant="subtle" size="xs" onClick={() => setScrivi(false)}>
                Annulla
              </Button>
              <Button size="xs" disabled={voto < 1} loading={invio} onClick={invia}>
                Pubblica
              </Button>
            </Group>
          </Stack>
        </Paper>
      )}

      {n === 0 && !scrivi && (
        <Alert variant="light" color="gray" p="xs">
          Ancora nessuna recensione: lascia la prima!
        </Alert>
      )}

      <Stack gap="xs">
        {elenco.map((r) => (
          <Paper key={r.id} p="xs" radius="md" withBorder>
            <Group justify="space-between" gap={4}>
              <Group gap={6}>
                <Text size="sm" fw={600}>
                  {r.autore || "Utente anonimo"}
                </Text>
                <Group gap={1}>
                  {Array.from({ length: r.voto }).map((_, i) => (
                    <IconStarFilled key={i} size={11} color="var(--mantine-color-yellow-6)" />
                  ))}
                </Group>
              </Group>
              <Text size="xs" c="dimmed">
                {data(r.creata_il)}
              </Text>
            </Group>
            {r.tag.length > 0 && (
              <Text size="xs" c="dimmed">
                {r.tag.join(" · ")}
              </Text>
            )}
            {r.testo && <Text size="sm">{r.testo}</Text>}
          </Paper>
        ))}
      </Stack>
    </Stack>
  );
}
