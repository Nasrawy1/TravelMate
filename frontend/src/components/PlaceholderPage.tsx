import type { ReactNode } from 'react'

interface PlaceholderPageProps {
  title: string
  children: ReactNode
}

export default function PlaceholderPage({ title, children }: PlaceholderPageProps) {
  return (
    <section className="page">
      <p className="page-label">Frontend placeholder</p>
      <h1>{title}</h1>
      <p>{children}</p>
    </section>
  )
}
