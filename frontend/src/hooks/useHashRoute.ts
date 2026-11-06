import { useEffect, useState } from 'react'

export function parseHash(hash: string): string[] {
  return hash.replace(/^#\/?/, '').split('/').filter(Boolean)
}

export function useHashRoute(): string[] {
  const [parts, setParts] = useState(() => parseHash(location.hash))
  useEffect(() => {
    const on = () => setParts(parseHash(location.hash))
    window.addEventListener('hashchange', on)
    return () => window.removeEventListener('hashchange', on)
  }, [])
  return parts
}
