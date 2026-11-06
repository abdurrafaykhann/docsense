import { useEffect, useState } from 'react'

export function parseHash(hash: string): string[] {
  return hash.replace(/^#\/?/, '').split('?')[0].split('/').filter(Boolean)
}

export function parseHashQuery(hash: string): URLSearchParams {
  const i = hash.indexOf('?')
  return new URLSearchParams(i >= 0 ? hash.slice(i + 1) : '')
}

/** Hash location: path parts plus query (e.g. #/documents/4?page=2&hl=0.1,0.2,0.5,0.3). */
export function useHashLocation(): { parts: string[]; query: URLSearchParams } {
  const [hash, setHash] = useState(() => location.hash)
  useEffect(() => {
    const on = () => setHash(location.hash)
    window.addEventListener('hashchange', on)
    return () => window.removeEventListener('hashchange', on)
  }, [])
  return { parts: parseHash(hash), query: parseHashQuery(hash) }
}

export function useHashRoute(): string[] {
  return useHashLocation().parts
}
