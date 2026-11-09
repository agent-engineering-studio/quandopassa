import { ActionIcon, Badge, Group, Paper, ScrollArea, Stack, Text, TextInput } from "@mantine/core";
import { IconRobot, IconSend } from "@tabler/icons-react";
import { useEffect, useRef, useState } from "react";
import type { RispostaAssistente } from "../api";
import { api } from "../api";

interface Messaggio {
  da: "utente" | "assistente";
  testo: string;
  meta?: RispostaAssistente;
}

interface Props {
  esempi: string[];
  posizione: { lat: number; lon: number } | null;
  ora?: string;
  onFermata?: (id: string) => void;
}

export default function Assistente({ esempi, posizione, ora, onFermata }: Props) {
  const [messaggi, setMessaggi] = useState<Messaggio[]>([
    {
      da: "assistente",
      testo:
        "Ciao! Sono l'assistente del bus urbano. Chiedimi quando passa il bus, come arrivare in un posto o dove si trova una linea.",
    },
  ]);
  const [testo, setTesto] = useState("");
  const [attesa, setAttesa] = useState(false);
  const fondo = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fondo.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [messaggi]);

  const chiedi = async (domanda: string) => {
    if (!domanda.trim() || attesa) return;
    setMessaggi((m) => [...m, { da: "utente", testo: domanda }]);
    setTesto("");
    setAttesa(true);
    try {
      const r = await api.assistente(domanda, posizione?.lat, posizione?.lon, ora);
      setMessaggi((m) => [...m, { da: "assistente", testo: r.risposta, meta: r }]);
      const f = (r.dati as { fermata?: { id: string } }).fermata;
      if (f?.id) onFermata?.(f.id);
    } catch (e) {
      setMessaggi((m) => [...m, { da: "assistente", testo: (e as Error).message }]);
    } finally {
      setAttesa(false);
    }
  };

  return (
    <Stack gap="xs" h="100%">
      <ScrollArea.Autosize mah={380} type="auto">
        <Stack gap="xs">
          {messaggi.map((m, i) => (
            <Group key={i} justify={m.da === "utente" ? "flex-end" : "flex-start"} align="flex-start" wrap="nowrap" gap={6}>
              {m.da === "assistente" && <IconRobot size={18} style={{ flexShrink: 0, marginTop: 6 }} />}
              <Paper
                p="xs"
                radius="lg"
                maw="85%"
                bg={m.da === "utente" ? "var(--mantine-color-blue-filled)" : "var(--mantine-color-default-hover)"}
                c={m.da === "utente" ? "white" : undefined}
              >
                <Text size="sm">{m.testo}</Text>
                {m.meta && (
                  <Text size="10px" c="dimmed" mt={4}>
                    {m.meta.generato_da_ia ? "Risposta generata con IA" : "Risposta automatica"} · {m.meta.fonti.join(", ") || "base di conoscenza"}
                  </Text>
                )}
              </Paper>
            </Group>
          ))}
          {attesa && (
            <Text size="xs" c="dimmed">
              Sto controllando l'orario…
            </Text>
          )}
          <div ref={fondo} />
        </Stack>
      </ScrollArea.Autosize>
      <Group gap={6}>
        {esempi.slice(0, 4).map((e) => (
          <Badge key={e} variant="light" radius="sm" tt="none" style={{ cursor: "pointer" }} onClick={() => chiedi(e)}>
            {e}
          </Badge>
        ))}
      </Group>
      <TextInput
        placeholder="Scrivi una domanda…"
        value={testo}
        maxLength={500}
        onChange={(e) => setTesto(e.currentTarget.value)}
        onKeyDown={(e) => e.key === "Enter" && chiedi(testo)}
        rightSection={
          <ActionIcon variant="filled" onClick={() => chiedi(testo)} loading={attesa} aria-label="Invia">
            <IconSend size={16} />
          </ActionIcon>
        }
      />
      <Text size="10px" c="dimmed">
        Assistente automatico (IA): le risposte si basano sull'orario programmato, verifica sempre alla fermata. La
        posizione, se attiva, serve solo a questa domanda e non viene salvata.
      </Text>
    </Stack>
  );
}
