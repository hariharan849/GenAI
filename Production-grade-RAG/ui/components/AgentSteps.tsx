"use client";

interface AgentStepsProps {
  steps: string[];
  answer: string;
  sources?: string[];
}

export function AgentSteps({ steps, answer, sources = [] }: AgentStepsProps) {
  return (
    <div className="agent-steps">
      {steps.length > 0 && (
        <>
          <h4>Reasoning steps</h4>
          {steps.map((step, i) => (
            <div key={i} className="step-item">{step}</div>
          ))}
        </>
      )}
      {answer && (
        <div className="answer-block">
          {answer}
        </div>
      )}
      {sources.length > 0 && (
        <div className="sources-list">
          <p style={{ fontSize: "0.75rem", color: "#64748b", marginTop: "0.5rem" }}>Sources:</p>
          {sources.slice(0, 3).map((src, i) => (
            <a key={i} href={src} target="_blank" rel="noopener noreferrer">
              {src.split("/").at(-1) ?? src}
            </a>
          ))}
        </div>
      )}
    </div>
  );
}
