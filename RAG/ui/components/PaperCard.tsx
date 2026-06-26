"use client";

export interface SearchHit {
  arxiv_id: string;
  title: string;
  authors?: string;
  abstract?: string;
  published_date?: string;
  pdf_url?: string;
  score: number;
  section_name?: string;
  chunk_text?: string;
  // Nuke docs fields
  url?: string;
  nuke_node_name?: string;
  section?: string;
}

export function PaperCard({ hit }: { hit: SearchHit }) {
  return (
    <div className="paper-card">
      <h4>{hit.title}</h4>
      <div className="meta">
        {hit.authors && (
          <span>
            {hit.authors.split(",").slice(0, 2).join(", ")}
            {hit.authors.split(",").length > 2 ? " et al." : ""}
          </span>
        )}
        {hit.published_date && <span>{hit.published_date.slice(0, 10)}</span>}
        {hit.section_name && <span>{hit.section_name}</span>}
        <span>score: {hit.score.toFixed(3)}</span>
      </div>
      {hit.abstract && <p className="abstract">{hit.abstract}</p>}
      {hit.chunk_text && !hit.abstract && <p className="abstract">{hit.chunk_text}</p>}
      {hit.pdf_url && (
        <a href={hit.pdf_url} target="_blank" rel="noopener noreferrer">
          View PDF →
        </a>
      )}
    </div>
  );
}

export function PaperResults({ hits }: { hits: SearchHit[] }) {
  if (!hits || hits.length === 0) {
    return <p style={{ fontSize: "0.85rem", color: "#64748b" }}>No papers found.</p>;
  }
  return (
    <div>
      <p style={{ fontSize: "0.78rem", color: "#64748b", marginBottom: "0.5rem" }}>
        Found {hits.length} paper{hits.length !== 1 ? "s" : ""}
      </p>
      {hits.slice(0, 5).map((hit) => (
        <PaperCard key={`${hit.arxiv_id}-${hit.chunk_text?.slice(0, 10)}`} hit={hit} />
      ))}
    </div>
  );
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
          View in Nuke Docs →
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
