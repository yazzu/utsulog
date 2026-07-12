export type RangeBoundary = 'from' | 'to';

/**
 * 日付inputと任意の時刻inputを結合し、完全なISO日時文字列を返す。
 * 秒は境界の種類によらず常に固定する(from=:00, to=:59)。
 * 同じ分をFrom/Toに明示入力した場合でもゼロ幅の範囲にならないようにするため。
 */
export function combineDateTime(date: string, time: string, boundary: RangeBoundary): string | undefined {
  if (!date) return undefined;

  const seconds = boundary === 'from' ? '00' : '59';
  const hhmm = time || (boundary === 'from' ? '00:00' : '23:59');

  return `${date}T${hhmm}:${seconds}`;
}
