import type { Alert, Watchlisted } from '../types'
import { Tooltip } from './Tooltip'

interface AutopilotActionsProps {
  watchlisted: Watchlisted | null
  alert: Alert | null
}

/** The Autopilot actions block — pro-only, from mockup v4 (lines 289-296). NOT wrapped in
 * `<Card>`: the mockup renders it as a headerless `.anim.pro-only` block with an `.acts-h`
 * eyebrow + `.acts` row, showing what the agent did autonomously at HIGH — watchlist the wallet
 * and draft an alert (never auto-sent). Pure presentational, driven entirely by
 * `watchlisted`/`alert`; App wires both in T18 from `Verdict.watchlisted`/`Verdict.alert`. */
export function AutopilotActions({ watchlisted, alert }: AutopilotActionsProps) {
  return (
    <div className="anim pro-only">
      <div className="acts-h">
        ⚙ autopilot — acts on what it remembers{' '}
        <Tooltip>
          At HIGH, the agent <b>acts on its own</b>: it watchlists the wallet so every future
          launch is flagged, and drafts an alert for a human to review (never auto-sent).
        </Tooltip>
      </div>
      <div className="acts">
        {watchlisted && (
          <div className="act">
            <div className="ic">✓</div>
            <div>
              <div className="t">Deployer watchlisted</div>
              <div className="s">future launches auto-flagged</div>
            </div>
          </div>
        )}
        {alert && (
          <div className="act">
            <div className="ic amber">!</div>
            <div>
              <div className="t">Alert drafted</div>
              <div className="s">pending human review</div>
            </div>
          </div>
        )}
        {!watchlisted && !alert && (
          <div className="s" style={{ padding: '4px 2px' }}>
            No autopilot actions — the verdict is below the action threshold.
          </div>
        )}
      </div>
    </div>
  )
}
