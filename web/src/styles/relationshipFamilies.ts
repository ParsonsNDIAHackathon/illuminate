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

// Muted on purpose, like the node fills in nodeTypes.ts: each family takes the tint of the node type
// it leads to, so highlighted paths, selection and search matches are the only saturated colour.
export const RELATIONSHIP_FAMILIES: readonly RelationshipFamily[] = [
  {
    key: 'supply',
    label: 'Supply',
    description: 'Program and supplier flow',
    color: '#5b7fb0',
    darkColor: '#7f9fc6',
    lineStyle: 'solid',
    types: ['SUPPLIES'],
  },
  {
    key: 'control',
    label: 'Ownership & control',
    description: 'Direct, beneficial, and ultimate control',
    color: '#b48660',
    darkColor: '#c4936a',
    lineStyle: 'solid',
    types: ['OWNS', 'ULTIMATE_PARENT_OF', 'BENEFICIAL_OWNER_OF'],
  },
  {
    key: 'people',
    label: 'People',
    description: 'Leadership and held roles',
    color: '#5f948b',
    darkColor: '#7fb0a7',
    lineStyle: 'dashed',
    types: ['HELD_ROLE'],
  },
  {
    key: 'affiliation',
    label: 'Affiliations',
    description: 'Memberships, business relationships, lobbying and giving',
    color: '#5f8fa0',
    darkColor: '#7fb0c0',
    lineStyle: 'dashed',
    types: ['MEMBER_OF', 'TRANSACTS_WITH', 'LOBBIES', 'DONATED_TO'],
  },
  {
    key: 'location',
    label: 'Location',
    description: 'Seat, operations, and manufacturing',
    color: '#9d8d65',
    darkColor: '#b3a680',
    lineStyle: 'dashed',
    types: ['INCORPORATED_IN', 'OPERATES_IN', 'MANUFACTURES_IN', 'PARENT_SEATED_IN'],
  },
  {
    key: 'evidence',
    label: 'Evidence',
    description: 'Artifacts, claims, and subjects',
    color: '#b07e97',
    darkColor: '#c69bb2',
    lineStyle: 'dotted',
    types: ['EVIDENCES', 'ASSERTS', 'TARGETS', 'ABOUT'],
  },
  {
    key: 'classification',
    label: 'Classification',
    description: 'Products and category structure',
    color: '#8c7eb0',
    darkColor: '#a89bcb',
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