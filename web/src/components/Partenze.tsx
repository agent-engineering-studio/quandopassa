import { Badge, Group, Stack, Text } from "@mantine/core";
import type { Partenza } from "../api";
import { giornoRelativo, hhmm, traMinuti } from "../api";

interface Props {
  partenze: Partenza[];
  oggi: string;
  aPiediMin?: number;
  onCorsa?: (id: string) => void;
}

/** Elenco dei prossimi passaggi, con l'indicazione "fai in tempo" se si conosce il tempo a piedi. */
export default function Partenze({ partenze, oggi, aPiediMin, onCorsa }: Props) {
  if (!partenze.length) return <Text size="sm" c="dimmed">Nessun passaggio nei prossimi giorni.</Text>;
  return (
    <Stack gap={6}>
      {partenze.map((p) => {
        const margine = aPiediMin !== undefined ? p.tra_minuti - aPiediMin : null;
        return (
          <Group
            key={p.corsa_id + p.orario}
            justify="space-between"
            wrap="nowrap"
            className="riga-partenza"
            onClick={() => onCorsa?.(p.corsa_id)}
          >
            <Group gap="xs" wrap="nowrap">
              <Badge color={p.colore} radius="sm" size="lg" w={36} p={0}>
                {p.linea}
              </Badge>
              <div>
                <Text size="sm" fw={600}>
                  {giornoRelativo(p.orario, oggi)}
                  {hhmm(p.orario)}
                </Text>
                <Text size="xs" c="dimmed">
                  {p.destinazione}
                  {p.in_corsa ? " · bus già in viaggio" : ""}
                </Text>
              </div>
            </Group>
            <Stack gap={2} align="flex-end">
              <Text size="sm" fw={700} c={p.tra_minuti <= 5 ? "orange" : undefined}>
                {p.tra_minuti <= 0 ? "in partenza" : `tra ${traMinuti(p.tra_minuti)}`}
              </Text>
              {margine !== null && p.tra_minuti < 120 && (
                <Badge size="xs" variant="light" color={margine >= 2 ? "teal" : margine >= 0 ? "orange" : "red"}>
                  {margine >= 2 ? `fai in tempo (+${margine} min)` : margine >= 0 ? "affrettati" : "non fai in tempo"}
                </Badge>
              )}
            </Stack>
          </Group>
        );
      })}
    </Stack>
  );
}
