import { useState } from 'react'
import type { Ref } from 'react'

interface PasswordInputProps {
  id: string
  value: string
  onChange: (value: string) => void
  disabled: boolean
  invalid: boolean
  describedBy?: string
  inputRef?: Ref<HTMLInputElement>
  autoComplete?: 'current-password' | 'new-password'
  visible?: boolean
  onVisibilityChange?: (visible: boolean) => void
  controls?: string
}

export default function PasswordInput({ id, value, onChange, disabled, invalid, describedBy, inputRef, autoComplete = 'current-password', visible: controlledVisible, onVisibilityChange, controls = id }: PasswordInputProps) {
  const [localVisible, setLocalVisible] = useState(false)
  const visible = controlledVisible ?? localVisible

  function toggleVisibility() {
    setLocalVisible(!visible)
    onVisibilityChange?.(!visible)
  }

  return (
    <div className="login-password-input">
      <input ref={inputRef} id={id} name="password" type={visible ? 'text' : 'password'} autoComplete={autoComplete} required value={value} onChange={(event) => onChange(event.target.value)} disabled={disabled} aria-invalid={invalid} aria-describedby={describedBy} />
      <button type="button" onClick={toggleVisibility} disabled={disabled} aria-label={visible ? 'Hide password' : 'Show password'} aria-pressed={visible} aria-controls={controls}>
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
          {visible ? <><path d="M3 3l18 18M10.6 6.1A9.7 9.7 0 0 1 12 6c5.5 0 9 6 9 6a15 15 0 0 1-2.6 3.3M6.3 7.6C4.2 9.1 3 12 3 12s3.5 6 9 6c1.4 0 2.7-.4 3.8-1" /><path d="M9.9 9.9a3 3 0 0 0 4.2 4.2" /></> : <><path d="M3 12s3.5-6 9-6 9 6 9 6-3.5 6-9 6-9-6-9-6z" /><circle cx="12" cy="12" r="3" /></>}
        </svg>
      </button>
    </div>
  )
}
