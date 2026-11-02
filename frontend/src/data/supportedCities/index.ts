import snapshot from './cities.json' with { type: 'json' }

export const SUPPORTED_CITIES = snapshot.cities
// Python str.strip/re \s whitespace (not JavaScript's additional BOM whitespace).
const whitespace = /[\u0009-\u000d\u001c-\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]+/gu
export function normalizeCityText(value: string): string {
  return value.replace(whitespace, ' ').replace(/^ | $/g, '').toLowerCase()
}
export function resolveSupportedCity(value: string): string | null {
  const normalized = normalizeCityText(value)
  return SUPPORTED_CITIES.find(c => c.name.toLowerCase() === normalized || c.aliases.includes(normalized))?.name ?? null
}
export function searchSupportedCities(value: string) {
  const query = normalizeCityText(value)
  return SUPPORTED_CITIES.filter(c => [c.name.toLowerCase(), ...c.aliases].some(name => name.includes(query)))
}
export function cityInputError(value: string): string | undefined {
  if (!normalizeCityText(value)) return 'Choose a supported city.'
  if ([...value.trim()].length > 200) return 'Use no more than 200 characters for a city.'
  if (!resolveSupportedCity(value)) return 'Choose a city from the supported list. Other cities are not supported yet.'
}
