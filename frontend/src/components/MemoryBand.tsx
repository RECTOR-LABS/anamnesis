/** The compounding-memory stat band from mockup v4 (`.band > .stat` × 3) — static narrative
 * content, no props. Ports the mockup's 3 tiles verbatim: the memory-vs-cold-analysis ratio,
 * the MED→HIGH verdict sharpening across sessions, and the "6 edges" compounding count,
 * including their sparkline/session-dot decorations. The mockup's `&nbsp;` separators become
 * `{' '}` expression containers (regular spaces) since JSX text can't hold a literal `&nbsp;`
 * unambiguously across every line-wrap here. */
export function MemoryBand() {
  return (
    <div className="band">
      <div className="stat">
        <div className="sl">memory vs cold analysis</div>
        <div className="sv tnum">99,313×</div>
        <div className="ss">
          recall in <b style={{ color: 'var(--text)' }}>2.7{' '}ms</b> vs <b style={{ color: 'var(--text)' }}>268{' '}s</b> re-deriving on-chain
        </div>
        <div className="spark">
          <i style={{ height: '20%' }} />
          <i style={{ height: '35%' }} />
          <i style={{ height: '30%' }} />
          <i style={{ height: '55%' }} />
          <i style={{ height: '70%' }} />
          <i style={{ height: '100%', opacity: 1 }} />
        </div>
      </div>

      <div className="stat">
        <div className="sl">sharpened across sessions</div>
        <div className="sv">
          MED → <span style={{ color: 'var(--high)' }}>HIGH</span>
        </div>
        <div className="ss">verdict rose as 3 rugs compounded over 3 sessions</div>
        <div className="dots">
          <span className="d m" />
          <span className="d m" />
          <span className="d h" />
          <span className="a">{' '}s1 · s2 · s3</span>
        </div>
      </div>

      <div className="stat">
        <div className="sl">compounds every scan</div>
        <div className="sv tnum">6 edges</div>
        <div className="ss">each investigation is remembered — never re-run cold</div>
        <div className="spark">
          <i style={{ height: '25%' }} />
          <i style={{ height: '40%' }} />
          <i style={{ height: '60%' }} />
          <i style={{ height: '75%' }} />
          <i style={{ height: '90%' }} />
          <i style={{ height: '100%', opacity: 1 }} />
        </div>
      </div>
    </div>
  )
}
