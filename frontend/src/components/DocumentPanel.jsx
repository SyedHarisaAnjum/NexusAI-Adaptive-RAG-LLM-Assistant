import { useRef, useState } from 'react'
import { deleteDocument, uploadDocument } from '../api.js'

const MAX_UPLOAD_MB = 10

function DocumentPanel({ documents, selectedDocId, onSelect, onUploaded, onDeleted }) {
  const [isUploading, setIsUploading] = useState(false)
  const [status, setStatus] = useState(null) // { type: 'info' | 'error', text }
  const inputRef = useRef(null)

  const handleFile = async (event) => {
    const file = event.target.files?.[0]
    event.target.value = '' // allow picking the same file again
    if (!file) return

    // Quick checks in the browser; the server validates again.
    if (!file.name.toLowerCase().endsWith('.pdf')) {
      setStatus({ type: 'error', text: 'Please choose a PDF file.' })
      return
    }
    if (file.size > MAX_UPLOAD_MB * 1024 * 1024) {
      setStatus({ type: 'error', text: `File is larger than ${MAX_UPLOAD_MB} MB.` })
      return
    }

    setIsUploading(true)
    setStatus({ type: 'info', text: `Uploading and indexing ${file.name}…` })
    try {
      const doc = await uploadDocument(file)
      onUploaded(doc)
      setStatus({ type: 'info', text: `Ready: ${doc.filename} (${doc.page_count} pages)` })
    } catch (error) {
      setStatus({ type: 'error', text: error.message })
    } finally {
      setIsUploading(false)
    }
  }

  const handleDelete = async (doc) => {
    if (!window.confirm(`Delete "${doc.filename}"?`)) return
    try {
      await deleteDocument(doc.document_id)
      onDeleted(doc.document_id)
      setStatus(null)
    } catch (error) {
      setStatus({ type: 'error', text: error.message })
    }
  }

  return (
    <aside className="doc-panel">
      <h2>Documents</h2>

      <button
        type="button"
        className="upload-button"
        onClick={() => inputRef.current?.click()}
        disabled={isUploading}
      >
        {isUploading ? 'Uploading…' : 'Upload PDF'}
      </button>
      <input
        ref={inputRef}
        type="file"
        accept="application/pdf,.pdf"
        onChange={handleFile}
        hidden
      />

      {status && <p className={`doc-status doc-status-${status.type}`}>{status.text}</p>}

      {documents.length === 0 ? (
        <p className="doc-empty">No documents yet. Upload a PDF to ask questions about it.</p>
      ) : (
        <ul className="doc-list">
          <li>
            <label className="doc-item">
              <input
                type="radio"
                name="doc-scope"
                checked={selectedDocId === ''}
                onChange={() => onSelect('')}
              />
              <span className="doc-name">All documents</span>
            </label>
          </li>
          {documents.map((doc) => (
            <li key={doc.document_id}>
              <label className="doc-item">
                <input
                  type="radio"
                  name="doc-scope"
                  checked={selectedDocId === doc.document_id}
                  onChange={() => onSelect(doc.document_id)}
                />
                <span className="doc-name" title={doc.filename}>
                  {doc.filename}
                  <small>
                    {doc.page_count} pages
                    {doc.chunk_count === 0 && ' · not indexed'}
                  </small>
                </span>
                <button
                  type="button"
                  className="doc-delete"
                  aria-label={`Delete ${doc.filename}`}
                  onClick={(e) => {
                    e.preventDefault()
                    handleDelete(doc)
                  }}
                >
                  ×
                </button>
              </label>
            </li>
          ))}
        </ul>
      )}
    </aside>
  )
}

export default DocumentPanel
