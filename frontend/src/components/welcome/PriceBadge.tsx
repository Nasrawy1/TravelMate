const labels = { live: 'Live', estimate: 'Estimate', unavailable: 'Unavailable', sample: 'Sample' }

interface VerifiedProvider {
  verified: true
  dataMode: 'online'
  source: string
  retrievedAt: string
}

type PriceBadgeProps =
  | { kind: 'live'; provider: VerifiedProvider }
  | { kind: Exclude<keyof typeof labels, 'live'>; provider?: never }

export default function PriceBadge(props: PriceBadgeProps) {
  // A future API adapter must derive verification from trusted FastAPI output,
  // never from fixtures or AI-generated prices. Metadata alone is not proof.
  const provider = props.provider
  const verified = provider?.verified === true && provider.dataMode === 'online'
    && provider.source.trim().length > 0 && Number.isFinite(Date.parse(provider.retrievedAt))
  const kind = props.kind === 'live' && !verified ? 'unavailable' : props.kind
  return <span className={`welcome-badge welcome-badge-${kind}`}>{labels[kind]}</span>
}
