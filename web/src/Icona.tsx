import sprite from "bootstrap-italia/dist/svg/sprites.svg?url";

interface Props {
  nome: string;
  classe?: string;
  titolo?: string;
}

/** Icona dello sprite di Bootstrap Italia (es. "it-map-marker"), decorativa se senza titolo. */
export default function Icona({ nome, classe = "", titolo }: Props) {
  return (
    <svg className={`icon ${classe}`} aria-hidden={titolo ? undefined : true} role={titolo ? "img" : undefined}>
      {titolo && <title>{titolo}</title>}
      <use href={`${sprite}#${nome}`} />
    </svg>
  );
}

/** Pittogramma del bus (lo sprite di Bootstrap Italia non ne ha uno). */
export function IconaBus({ dim = 24 }: { dim?: number }) {
  return (
    <svg viewBox="0 0 24 24" width={dim} height={dim} aria-hidden="true">
      <path
        fill="currentColor"
        d="M6 2h12a3 3 0 0 1 3 3v11a2 2 0 0 1-1 1.7V20a1 1 0 0 1-1 1h-1a1 1 0 0 1-1-1v-1H7v1a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1v-2.3A2 2 0 0 1 3 16V5a3 3 0 0 1 3-3Zm0 3v6h12V5H6Zm1.5 8.5a1.5 1.5 0 1 0 0 3 1.5 1.5 0 0 0 0-3Zm9 0a1.5 1.5 0 1 0 0 3 1.5 1.5 0 0 0 0-3Z"
      />
    </svg>
  );
}

/** Pittogramma della persona a piedi. */
export function IconaPiedi({ dim = 18 }: { dim?: number }) {
  return (
    <svg viewBox="0 0 24 24" width={dim} height={dim} aria-hidden="true">
      <path
        fill="currentColor"
        d="M13.5 5.5a2 2 0 1 0 0-4 2 2 0 0 0 0 4ZM9.8 8.9 7 23h2.1l1.8-8 2.1 2v6h2v-7.5l-2.1-2 .6-3A7.3 7.3 0 0 0 19 13v-2a5 5 0 0 1-4.3-2.4l-1-1.6a2 2 0 0 0-1.7-1c-.3 0-.5 0-.8.1L6 8.3V13h2V9.6l1.8-.7"
      />
    </svg>
  );
}
