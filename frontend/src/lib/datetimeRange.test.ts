import { describe, expect, it } from 'vitest';
import { combineDateTime } from './datetimeRange';

describe('combineDateTime', () => {
  it('returns undefined when date is empty', () => {
    expect(combineDateTime('', '', 'from')).toBeUndefined();
    expect(combineDateTime('', '10:00', 'to')).toBeUndefined();
  });

  it('defaults the from-boundary time to 00:00:00 when time is empty', () => {
    expect(combineDateTime('2026-07-10', '', 'from')).toBe('2026-07-10T00:00:00');
  });

  it('defaults the to-boundary time to 23:59:59 when time is empty', () => {
    expect(combineDateTime('2026-07-10', '', 'to')).toBe('2026-07-10T23:59:59');
  });

  it('fixes seconds to :00 for the from-boundary when time is provided', () => {
    expect(combineDateTime('2026-07-10', '22:00', 'from')).toBe('2026-07-10T22:00:00');
  });

  it('fixes seconds to :59 for the to-boundary when time is provided, avoiding a zero-width range when from/to share the same minute', () => {
    expect(combineDateTime('2026-07-10', '22:00', 'to')).toBe('2026-07-10T22:00:59');
  });
});
