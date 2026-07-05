import { describe, expect, it } from 'vitest'
import { render } from '@testing-library/react'
import { ClusterGraph } from './ClusterGraph'
import type { GraphData } from '../types'

const DEPLOYER = 'sF2wwqcTGvNPfBFvBw6P6c1PYuDG3S3M2sV4iF6r1qz'
const RUG_1 = '3qFSoWZ5w8n3B7pNn9BVi93BjEmFAKerVwoV3z6Fzuad'
const RUG_2 = '7wZk9cRt2LpXqYh1MnBv8sDfGjKl4oPqRstUvWxYzAbC'
const RUG_3 = 'HqNzYtR5vKmXpLd3FgWs9BnJc2VoTe6UiAy8ZrMkPqSx'
const FUNDER = '7dGbTr2CvXqPz9LmNfWs4BnJc2VoTe6UiAy8ZrMkCrar'

/** Builds a 5-node cluster graph fixture — the `sF2ww…` deployer hub (same address as the
 * VerdictCard fixture) linked to three rugged tokens and one funding source. Each test overrides
 * only the field(s) it cares about. */
function makeGraph(overrides: Partial<GraphData> = {}): GraphData {
  return {
    nodes: [
      { id: DEPLOYER, type: 'wallet', flags: ['deployer'] },
      { id: RUG_1, type: 'token', flags: ['rugged'] },
      { id: RUG_2, type: 'token', flags: ['rugged'] },
      { id: RUG_3, type: 'token', flags: ['rugged'] },
      { id: FUNDER, type: 'funding', flags: [] },
    ],
    edges: [
      { src: DEPLOYER, dst: RUG_1, type: 'DEPLOYED' },
      { src: DEPLOYER, dst: RUG_2, type: 'DEPLOYED' },
      { src: DEPLOYER, dst: RUG_3, type: 'DEPLOYED' },
      { src: DEPLOYER, dst: FUNDER, type: 'FUNDED_BY' },
    ],
    ...overrides,
  }
}

describe('ClusterGraph', () => {
  it('renders one .gnode per node', () => {
    const graph = makeGraph()
    const { container } = render(<ClusterGraph graph={graph} />)

    expect(container.querySelectorAll('.gnode')).toHaveLength(5)
  })

  it('renders one .edge per edge', () => {
    const graph = makeGraph()
    const { container } = render(<ClusterGraph graph={graph} />)

    expect(container.querySelectorAll('.edge')).toHaveLength(graph.edges.length)
  })

  it('centers the deployer-flagged node', () => {
    const graph = makeGraph()
    const { container, getByText } = render(<ClusterGraph graph={graph} />)

    expect(container.querySelectorAll('[data-role="deployer"]')).toHaveLength(1)
    expect(getByText('deployer')).toBeInTheDocument()
  })

  it('applies role-based coloring for a rugged node and a funding node', () => {
    const graph = makeGraph()
    const { container } = render(<ClusterGraph graph={graph} />)

    const rugged = container.querySelector(`[data-node-id="${RUG_1}"]`)
    expect(rugged).toHaveAttribute('data-role', 'rugged')
    expect(rugged?.querySelector('circle')).toHaveAttribute('stroke', 'var(--high)')

    const funder = container.querySelector(`[data-node-id="${FUNDER}"]`)
    expect(funder).toHaveAttribute('data-role', 'funder')
  })

  it('renders the degraded single flag-less node without crashing', () => {
    const graph: GraphData = { nodes: [{ id: 'X', type: 'wallet', flags: [] }], edges: [] }
    const { container } = render(<ClusterGraph graph={graph} />)

    expect(container.querySelectorAll('.gnode')).toHaveLength(1)
    expect(container.querySelectorAll('.edge')).toHaveLength(0)
  })
})
