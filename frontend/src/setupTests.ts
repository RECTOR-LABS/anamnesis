// Registers jest-dom matchers (toBeInTheDocument, etc.) on Vitest's `expect`.
// Uses the `/vitest` subpath (not the bare package) because that's the entry point
// that both extends Vitest's real `expect` at runtime AND augments Vitest's
// `Assertion` type — the bare `@testing-library/jest-dom` import only augments
// Jest's global types, which `tsc -b` (run by `npm run build`) would reject the
// moment a test uses a jest-dom matcher.
import '@testing-library/jest-dom/vitest'
