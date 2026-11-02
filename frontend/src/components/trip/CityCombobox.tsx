import { useEffect, useRef, useState } from 'react'
import type { InputHTMLAttributes } from 'react'
import { resolveSupportedCity, searchSupportedCities } from '../../data/supportedCities'

type Props = Omit<InputHTMLAttributes<HTMLInputElement>, 'onChange' | 'value'> & {
  id: string; value: string; onValueChange: (value: string) => void
}
/** Editable combobox: DOM focus stays on the input while active-descendant moves. */
export default function CityCombobox({ id, value, onValueChange, ...props }: Props) {
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(-1)
  const list = useRef<HTMLUListElement>(null)
  const matches = searchSupportedCities(value)
  const current = active >= 0 && active < matches.length ? active : -1
  useEffect(() => {
    if (open && current >= 0) list.current?.children[current]?.scrollIntoView({ block: 'nearest' })
  }, [open, current])
  function select(name: string) { onValueChange(name); setOpen(false); setActive(-1) }
  return <div className="tp-city-control">
    <input {...props} id={id} value={value} role="combobox" type="text" autoComplete="off" spellCheck={false}
      aria-autocomplete="list" aria-expanded={open} aria-controls={`${id}-options`}
      aria-activedescendant={open && current >= 0 ? `${id}-option-${current}` : undefined}
      placeholder="Search supported cities"
      onFocus={() => { setOpen(true); setActive(-1) }}
      onChange={event => { onValueChange(event.target.value); setOpen(true); setActive(-1) }}
      onBlur={() => {
        setOpen(false); setActive(-1)
        const canonical = resolveSupportedCity(value)
        if (canonical && [...value.trim()].length <= 200) onValueChange(canonical)
      }}
      onKeyDown={event => {
        if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
          event.preventDefault(); setOpen(true)
          setActive(matches.length ? event.key === 'ArrowDown' ? (current + 1) % matches.length : current <= 0 ? matches.length - 1 : current - 1 : -1)
        } else if (event.key === 'Escape') {
          event.preventDefault(); setOpen(false); setActive(-1)
        } else if (event.key === 'Enter' && open) {
          event.preventDefault()
          if (current >= 0) select(matches[current].name)
          else {
            const canonical = resolveSupportedCity(value)
            if (canonical && [...value.trim()].length <= 200) select(canonical)
          }
        }
      }} />
    <ul ref={list} id={`${id}-options`} role="listbox" aria-label="Supported cities" className="tp-city-options" hidden={!open}>
      {matches.map((city, index) => <li key={city.name} id={`${id}-option-${index}`} role="option"
        aria-selected={index === current} onMouseDown={event => event.preventDefault()}
        onClick={() => select(city.name)}>
        <span>{city.name}</span><small>{city.country_code.toUpperCase()}</small>
      </li>)}
    </ul>
    {open && <span className="tp-city-status" role="status">{matches.length ? `${matches.length} supported cities. Use arrow keys and Enter to select.` : 'No supported cities match. Try another name.'}</span>}
  </div>
}
