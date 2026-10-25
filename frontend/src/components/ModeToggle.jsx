const MODES = [
  { value: 'auto', label: 'Auto', hint: 'The assistant decides per question: your documents or general knowledge' },
  { value: 'documents', label: 'Documents', hint: 'Answers only from your PDFs, with sources' },
  { value: 'general', label: 'General', hint: "Gemini's general knowledge, no documents" },
]

function ModeToggle({ mode, onChange, disabled }) {
  return (
    <div className="mode-toggle" role="group" aria-label="Answer mode">
      {MODES.map((m) => (
        <button
          key={m.value}
          type="button"
          title={m.hint}
          aria-pressed={mode === m.value}
          className={mode === m.value ? 'active' : ''}
          onClick={() => onChange(m.value)}
          disabled={disabled}
        >
          {m.label}
        </button>
      ))}
    </div>
  )
}

export default ModeToggle
