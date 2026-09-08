export type RelationshipFamilyKey = 'supply' | 'control' | 'people' | 'affiliation' | 'location' | 'evidence' | 'classification'

export interface RelationshipFamily {
  key: RelationshipFamilyKey
  label: string
  description: string
  color: string
  darkColor: string
  lineStyle: 'solid' | 'dashed' | 'dotted'
  types: readonly string[]
}

export const RELATIONSHIP_FAMILIES: readonly RelationshipFamily[] = [
  {
    key: 'supply',
    label: 'Supply',
    description: 'Program and supplier flow',
    color: '#2563eb',
    darkColor: '#60a5fa',
    lineStyle: 'solid',
    types: ['SUPPLIES'],
  },
  {
    key: 'control',
    label: 'Ownership & control',
    description: 'Direct, beneficial, and ultimate control',
    color: '#c2410c',
    darkColor: '#fb923c',
    lineStyle: 'solid',
    types: ['OWNS', 'ULTIMATE_PARENT_OF', 'BENEFICIAL_OWNER_OF'],
  },
  {
    key: 'people',
    label: 'People',
    description: 'Leadership and held roles',
    color: '#0f766e',
    darkColor: '#5eead4',
    lineStyle: 'dashed',
    types: ['HELD_ROLE'],
  },
  {
    key: 'affiliation',
    label: 'Affiliations',
    description: 'Memberships, business relationships, lobbying and giving',
    color: '#0e7490',
    darkColor: '#22d3ee',
    lineStyle: 'dashed',
    types: ['MEMBER_OF', 'TRANSACTS_WITH', 'LOBBIES', 'DONATED_TO'],
  },
  {
    key: 'location',
    label: 'Location',
    description: 'Seat, operations, and manufacturing',
    color: '#a16207',
    darkColor: '#facc15',
    lineStyle: 'dashed',
    types: ['INCORPORATED_IN', 'OPERATES_IN', 'MANUFACTURES_IN', 'PARENT_SEATED_IN'],
  },
  {
    key: 'evidence',
    label: 'Evidence',
    description: 'Artifacts, claims, and subjects',
    color: '#7e22ce',
    darkColor: '#c084fc',
    lineStyle: 'dotted',
    types: ['EVIDENCES', 'ASSERTS', 'TARGETS', 'ABOUT'],
  },
  {
    key: 'classification',
    label: 'Classification',
    description: 'Products and category structure',
    color: '#475569',
    darkColor: '#94a3b8',
    lineStyle: 'dotted',
    types: ['PROVIDES', 'SUBCATEGORY_OF'],
  },
]

const FAMILY_BY_TYPE = new Map(
  RELATIONSHIP_FAMILIES.flatMap(family => family.types.map(type => [type, family] as const)),
)

export function relationshipFamily(type: string): RelationshipFamily {
  return FAMILY_BY_TYPE.get(type) || {
    key: 'classification',
    label: 'Other',
    description: 'Other relationship',
    color: '#64748b',
    darkColor: '#94a3b8',
    lineStyle: 'solid',
    types: [],
  }
}