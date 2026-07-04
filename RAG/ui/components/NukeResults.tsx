"use client";

export interface SearchHit {
  title?: string;
  score: number;
  section_name?: string;
  chunk_text?: string;
  url?: string;
  nuke_node_name?: string;
  section?: string;
}

export function NukeResultCard({ hit }: { hit: SearchHit }) {
  const label = hit.nuke_node_name ?? hit.url?.split("/").at(-1)?.replace(".html", "") ?? "Node";
  const sectionLabel = hit.section ?? hit.section_name;

  return (
    <div className="nuke-card">
      <div className="nuke-card-header">
        <span className="nuke-badge">Nuke</span>
        <h4>{label}</h4>
      </div>
      <div className="meta">
        {sectionLabel && <span>{sectionLabel}</span>}
        <span>score: {hit.score.toFixed(3)}</span>
      </div>
      {hit.chunk_text && <p className="abstract">{hit.chunk_text}</p>}
      {hit.url && (
        <a href={hit.url} target="_blank" rel="noopener noreferrer">
          View in Nuke Docs -&gt;
        </a>
      )}
    </div>
  );
}

export function NukeResults({ hits }: { hits: SearchHit[] }) {
  if (!hits || hits.length === 0) {
    return (
      <p style={{ fontSize: "0.85rem", color: "#64748b" }}>
        No Nuke docs found. Run the <code>nuke_docs_ingestion</code> DAG first.
      </p>
    );
  }
  return (
    <div>
      <p style={{ fontSize: "0.78rem", color: "#64748b", marginBottom: "0.5rem" }}>
        Found {hits.length} Nuke doc{hits.length !== 1 ? "s" : ""}
      </p>
      {hits.slice(0, 5).map((hit, i) => (
        <NukeResultCard key={`${hit.url ?? i}-${hit.chunk_text?.slice(0, 10)}`} hit={hit} />
      ))}
    </div>
  );
}
