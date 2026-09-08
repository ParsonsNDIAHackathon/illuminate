import type { EntitySummary } from '../api/client'

export type VendorCandidate = EntitySummary & {
  ambiguous: boolean
  matchContext: string
  identityLine: string
}

const value = (label: string, input: unknown) => input == null || input === '' ? '' : `${label} ${input}`

export function identityLine(entity: Pick<EntitySummary, 'uei' | 'cage' | 'lei' | 'tier' | 'simulated'> & { id?: string }): string {
  const identifiers = [
    value('UEI', entity.uei),
    value('CAGE', entity.cage),
    value('LEI', entity.lei),
  ].filter(Boolean)
  return [
    ...identifiers,
    !identifiers.length && entity.id ? value('Record', entity.id) : '',
    value('Tier', entity.tier),
  ].filter(Boolean).join(' · ')
}

export function vendorCandidates(entities: EntitySummary[]): VendorCandidate[] {
  const nameCounts = new Map<string, number>()
  for (const entity of entities) {
    const key = entity.name.trim().toLocaleLowerCase()
    nameCounts.set(key, (nameCounts.get(key) || 0) + 1)
  }
  return entities.map(entity => {
    const ambiguous = (nameCounts.get(entity.name.trim().toLocaleLowerCase()) || 0) > 1
    const identifiers = [entity.uei && 'UEI', entity.cage && 'CAGE', entity.lei && 'LEI'].filter(Boolean)
    return {
      ...entity,
      ambiguous,
      identityLine: identityLine(entity),
      matchContext: ambiguous
        ? `Same-name record — verify ${identifiers.join(', ') || 'internal record ID'}`
        : `Matched by vendor name${entity.source ? ` · ${entity.source}` : ''}`,
    }
  })
}