/** Truncates a mint/pubkey to the mockup's `3qFSo…KY3pump` form — first 5 + last 6 chars around an
 * ellipsis — leaving anything already ≤13 chars intact. Shared by App and the cards that render an
 * address so the abbreviation stays byte-identical everywhere (change the form here, not in N copies). */
export const shortAddr = (addr: string): string =>
  addr.length > 13 ? `${addr.slice(0, 5)}…${addr.slice(-6)}` : addr
