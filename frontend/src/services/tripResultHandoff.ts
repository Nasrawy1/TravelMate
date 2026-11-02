import type { TripResult } from '../types/results'

/** One online-route session only. No browser storage, JWTs or SDK session objects. */
export class TripResultHandoff {
  private owner: string | null = null
  private response: TripResult | null = null
  setOwner(owner: string | null) {
    if (owner !== this.owner) this.response = null
    this.owner = owner
  }
  retain(owner: string | null, response: TripResult): boolean {
    if (!owner || owner !== this.owner) return false
    this.response = structuredClone(response)
    return true
  }
  read(owner: string | null): TripResult | null {
    return owner && owner === this.owner ? this.response : null
  }
  clear() { this.response = null }
}

/** Navigation occurs only after an API success has been retained for its verified owner. */
export function handoffGeneratedTrip(
  state: import('./generation').GenerationState<TripResult>,
  requestOwner: string | null,
  currentOwner: string | null,
  retain: (owner: string | null, response: TripResult) => boolean,
  navigate: (path: string) => void,
): boolean {
  if (state.status !== 'success' || state.context.data_mode !== 'api' || !currentOwner || requestOwner !== currentOwner) return false
  if (!retain(requestOwner, state.response)) return false
  navigate('/results')
  return true
}
