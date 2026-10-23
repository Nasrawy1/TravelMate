// Local JSON only: importing or selecting a demo never initializes online services.
import rome from './rome.json' with { type: 'json' }
import paris from './paris.json' with { type: 'json' }
import barcelona from './barcelona.json' with { type: 'json' }
import type { TripResult } from '../../types/results'
import type { TripGenerateRequest } from '../../types/trip'

export const OFFLINE_DEMO_IDS = ['rome', 'paris', 'barcelona'] as const
export type OfflineDemoId = typeof OFFLINE_DEMO_IDS[number]

export interface OfflineDemoTrip {
  id: OfflineDemoId
  label: string
  provenance: {
    label: 'DEMO'
    data_mode: 'offline_demo'
    live_evidence: false
    contract_version: '0.4'
    validation_today_utc: string
    source_archive: string
    source_entry: string
    notice: string
  }
  request: TripGenerateRequest
  response: TripResult
}

// JSON widens enum strings. Tests validate these checked-in files against the
// actual schema and semantic rules; this is not a validator for HTTP responses.
const samples = { rome, paris, barcelona } as Record<OfflineDemoId, OfflineDemoTrip>

/** Return a fresh copy so one consumer cannot mutate another demo selection. */
export function getOfflineDemoTrip(id: string): OfflineDemoTrip | null {
  if (!Object.hasOwn(samples, id)) return null
  return structuredClone(samples[id as OfflineDemoId])
}
