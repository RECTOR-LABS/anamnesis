import type { GraphData, GraphNode } from '../types'
import { Tooltip } from './Tooltip'

interface ClusterGraphProps {
  graph: GraphData
}

/** Every non-deployer role a node can render as. `deployer` is handled separately (it is always
 * the centered hub, styled with the halo + larger ring, never looked up in `NODE_STYLE`). */
type PeripheralRole = 'rugged' | 'watchlisted' | 'funder' | 'other'

interface Point {
  x: number
  y: number
}

interface NodeStyle {
  r: number
  fill: string
  stroke: string
  strokeWidth: number
  labelColor: string
}

/** Per-role circle + label styling — verbatim from mockup v4 lines 268-274. */
const NODE_STYLE: Record<PeripheralRole, NodeStyle> = {
  rugged: { r: 8, fill: '#160e11', stroke: 'var(--high)', strokeWidth: 1.5, labelColor: '#8b93a4' },
  watchlisted: { r: 9, fill: '#1a1408', stroke: 'var(--med)', strokeWidth: 1.7, labelColor: '#c9b27a' },
  funder: { r: 8, fill: '#101418', stroke: 'rgba(150,170,200,.6)', strokeWidth: 1.4, labelColor: '#8b93a4' },
  other: { r: 8, fill: '#101418', stroke: 'rgba(150,170,200,.4)', strokeWidth: 1.4, labelColor: '#8b93a4' },
}

/** Edge stroke color, keyed by the role of the edge's non-center endpoint. */
const EDGE_COLOR: Record<PeripheralRole, string> = {
  rugged: 'rgba(255,91,110,.5)',
  watchlisted: 'rgba(244,183,64,.55)',
  funder: 'rgba(150,170,200,.4)',
  other: 'rgba(150,170,200,.4)',
}

/** Role precedence for a peripheral (non-center) node — first match wins: rugged beats
 * watchlisted beats funding-typed beats everything else. */
function peripheralRoleOf(node: GraphNode): PeripheralRole {
  if (node.flags.includes('rugged')) return 'rugged'
  if (node.flags.includes('watchlisted')) return 'watchlisted'
  if (node.type === 'funding') return 'funder'
  return 'other'
}

/** The deployer's relationship web from mockup v4 (`.card` > `<svg>` + `.legend`, lines 256-278)
 * — a pure presentational component driven entirely by the `graph` prop. Ported verbatim (class
 * names, halo gradient, per-role colors, legend) with the geometry computed instead of hardcoded:
 * the flagged `deployer` node (or `nodes[0]` for the degraded single-node shape) sits at the fixed
 * hub position (190,120) and every other node is distributed on an ellipse around it. Not wrapped
 * in the `<Card>` primitive — the mockup's `<svg>`/`.legend` are direct children of `.card` (no
 * `.card-b` inset), so the legend stays full-bleed. */
export function ClusterGraph({ graph }: ClusterGraphProps) {
  const { nodes, edges } = graph
  const center = nodes.find((n) => n.flags.includes('deployer')) ?? nodes[0]
  const peripheral: GraphNode[] = center ? nodes.filter((n) => n !== center) : []
  const count = peripheral.length

  // id -> screen position (center + every peripheral node) so edges can look up endpoints, and
  // id -> role so edge color can be derived from the role of the endpoint it points away from.
  const positions = new Map<string, Point>()
  const roles = new Map<string, PeripheralRole | 'deployer'>()
  if (center) {
    positions.set(center.id, { x: 190, y: 120 })
    roles.set(center.id, 'deployer')
  }

  const placedPeripheral = peripheral.map((node, i) => {
    const theta = -Math.PI / 2 + (2 * Math.PI * i) / count
    const x = 190 + 120 * Math.cos(theta)
    const y = 120 + 82 * Math.sin(theta)
    positions.set(node.id, { x, y })
    const role = peripheralRoleOf(node)
    roles.set(node.id, role)
    return { node, x, y, role }
  })

  const ariaLabel = `Relationship graph: deployer linked to ${peripheral.length} related wallets and tokens`

  return (
    <div className="card anim">
      <div className="card-h">
        <span className="ht">
          <h3>Cluster graph</h3>
          <Tooltip>
            The deployer&apos;s <b>relationship web</b> — rugged tokens, funders, and this new
            token, connected. Click a node to pivot the investigation.
          </Tooltip>
        </span>
        <span className="meta">deployer web</span>
      </div>
      <svg viewBox="0 0 380 240" width="100%" role="img" aria-label={ariaLabel}>
        <defs>
          <radialGradient id="halo" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="rgba(255,91,110,.5)" />
            <stop offset="100%" stopColor="rgba(255,91,110,0)" />
          </radialGradient>
        </defs>
        <g fill="none" strokeWidth={1.4}>
          {edges.map((edge, i) => {
            const a = positions.get(edge.src)
            const b = positions.get(edge.dst)
            if (!a || !b) return null

            const nonCenterId = edge.dst === center?.id ? edge.src : edge.dst
            const role = roles.get(nonCenterId)
            const stroke = role && role !== 'deployer' ? EDGE_COLOR[role] : 'rgba(150,170,200,.4)'

            return (
              <line
                key={`${edge.src}-${edge.dst}-${i}`}
                className="edge"
                x1={a.x}
                y1={a.y}
                x2={b.x}
                y2={b.y}
                stroke={stroke}
                style={{ animationDelay: `${(0.4 + i * 0.12).toFixed(2)}s` }}
              />
            )
          })}
        </g>
        <g fontFamily="ui-monospace,monospace" fontSize={9}>
          {center && (
            <g className="gnode" data-node-id={center.id} data-role="deployer">
              <circle cx={190} cy={120} r={32} fill="url(#halo)" />
              <circle cx={190} cy={120} r={15} fill="#12151c" stroke="var(--high)" strokeWidth={2} />
              <text x={190} y={123} fill="#ff8a96" textAnchor="middle" fontWeight={700}>
                {center.id.slice(0, 5)}
              </text>
              <text x={190} y={152} fill="#d7dce7" textAnchor="middle">
                deployer
              </text>
            </g>
          )}
          {placedPeripheral.map(({ node, x, y, role }) => {
            const style = NODE_STYLE[role]
            const labelY = y <= 120 ? y - 14 : y + 20

            return (
              <g key={node.id} className="gnode" data-node-id={node.id} data-role={role}>
                <circle
                  cx={x}
                  cy={y}
                  r={style.r}
                  fill={style.fill}
                  stroke={style.stroke}
                  strokeWidth={style.strokeWidth}
                />
                <text x={x} y={labelY} fill={style.labelColor} textAnchor="middle">
                  {node.id.slice(0, 5)}…
                </text>
              </g>
            )
          })}
        </g>
      </svg>
      <div className="legend">
        <span>
          <i className="lgc" style={{ background: 'var(--high)' }} />
          rugged
        </span>
        <span>
          <i className="lgc" style={{ background: 'var(--med)' }} />
          this token
        </span>
        <span>
          <i className="lgc" style={{ background: '#101418', border: '1px solid rgba(150,170,200,.6)' }} />
          funder
        </span>
      </div>
    </div>
  )
}
