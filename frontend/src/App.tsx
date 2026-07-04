// Minimal shell — renders the mockup's outer container so mockup.css applies.
// Real dashboard components (CommandBar, VerdictCard, EvidenceCard, ...) land in later tasks.
export default function App() {
  return (
    <div className="wrap mode-lite">
      <div className="foot">Anamnesis — dashboard shell</div>
    </div>
  );
}
