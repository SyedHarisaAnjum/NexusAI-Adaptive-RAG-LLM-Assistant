function SourceList({ sources }) {
  return (
    <div className="sources">
      <p className="sources-title">Sources</p>
      <ul>
        {sources.map((source) => (
          <li key={source.ref}>
            <details>
              <summary>
                <span className="source-ref">[{source.ref}]</span>
                <span className="source-name">
                  {source.filename}, page {source.page_number}
                </span>
                <span className="source-score">
                  {Math.round(source.score * 100)}% match
                </span>
              </summary>
              <blockquote>
                {source.excerpt}
                {source.excerpt.length >= 300 && '…'}
              </blockquote>
            </details>
          </li>
        ))}
      </ul>
    </div>
  )
}

export default SourceList
